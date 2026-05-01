from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.billing.subscriptions import period_scheduler
from platform.billing.subscriptions.models import Subscription
from types import SimpleNamespace
from typing import Any, ClassVar
from uuid import uuid4

import pytest


def _subscription(*, cancel_at_period_end: bool = False) -> Subscription:
    now = datetime.now(UTC)
    return Subscription(
        id=uuid4(),
        tenant_id=uuid4(),
        scope_type="workspace",
        scope_id=uuid4(),
        plan_id=uuid4(),
        plan_version=1,
        status="active",
        current_period_start=now - timedelta(days=31),
        current_period_end=now - timedelta(seconds=1),
        cancel_at_period_end=cancel_at_period_end,
    )


class _Session:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class _Repository:
    subscriptions: ClassVar[list[Subscription]] = []

    def __init__(self, session: _Session) -> None:
        self.session = session

    async def list_due_for_period_rollover(self, now: datetime) -> list[Subscription]:
        return [
            subscription
            for subscription in self.subscriptions
            if subscription.current_period_end <= now
            and subscription.status not in {"canceled", "suspended"}
        ]

    async def advance_period(
        self,
        subscription: Subscription,
        *,
        new_period_start: datetime,
        new_period_end: datetime,
        status: str | None = None,
    ) -> Subscription:
        subscription.current_period_start = new_period_start
        subscription.current_period_end = new_period_end
        if status is not None:
            subscription.status = status
        if status == "canceled":
            subscription.cancel_at_period_end = False
        return subscription


class _Producer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, *args: Any) -> None:
        self.events.append(
            {
                "topic": args[0],
                "key": args[1],
                "event_type": args[2],
                "payload": args[3],
                "context": args[4],
                "source": args[5],
            }
        )


@pytest.fixture(autouse=True)
def _patch_scheduler_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    _Repository.subscriptions = []
    monkeypatch.setattr(period_scheduler.database, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(period_scheduler, "SubscriptionsRepository", _Repository)


@pytest.mark.asyncio
async def test_period_rollover_advances_once_per_boundary() -> None:
    subscription = _subscription()
    previous_end = subscription.current_period_end
    _Repository.subscriptions = [subscription]
    producer = _Producer()
    app = SimpleNamespace(state=SimpleNamespace(clients={"kafka": producer}))

    await period_scheduler.run_period_rollover(app)
    await period_scheduler.run_period_rollover(app)

    assert subscription.current_period_start == previous_end
    assert subscription.current_period_end == previous_end + timedelta(days=30)
    assert subscription.status == "active"
    assert [event["event_type"] for event in producer.events] == [
        "billing.subscription.period_renewed"
    ]


@pytest.mark.asyncio
async def test_period_rollover_cancels_scheduled_downgrade_and_emits_event() -> None:
    subscription = _subscription(cancel_at_period_end=True)
    _Repository.subscriptions = [subscription]
    producer = _Producer()
    app = SimpleNamespace(state=SimpleNamespace(clients={"kafka": producer}))

    await period_scheduler.run_period_rollover(app)

    assert subscription.status == "canceled"
    assert subscription.cancel_at_period_end is False
    assert producer.events[0]["event_type"] == "billing.subscription.downgrade_effective"
