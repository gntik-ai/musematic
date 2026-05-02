from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.billing.plans.repository import PlansRepository
from platform.billing.subscriptions.period_scheduler import _rollover_subscription
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.service import SubscriptionService

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription, set_subscription_period

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    async def append(self, *args: object, **kwargs: object) -> None:
        self.entries.append(dict(kwargs))


class _Producer:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    async def publish(self, *args: object) -> None:
        self.events.append(args)


async def test_downgrade_effective_period_boundary_advances_subscription(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session, plan_slug="pro")
        service = SubscriptionService(
            session=session,
            subscriptions=SubscriptionsRepository(session),
            plans=PlansRepository(session),
        )
        due_start = datetime.now(UTC) - timedelta(days=30)
        due_end = datetime.now(UTC) - timedelta(seconds=1)
        await set_subscription_period(
            session,
            subscription_id=fixture.subscription_id,
            period_start=due_start,
            period_end=due_end,
        )
        updated = await service.downgrade_at_period_end(fixture.subscription_id, "free")
        assert updated.cancel_at_period_end is True

        repository = SubscriptionsRepository(session)
        due = await repository.list_due_for_period_rollover(datetime.now(UTC))
        assert len(due) == 1
        due_subscription = due[0]
        previous_end = due_subscription.current_period_end
        audit = _Audit()
        producer = _Producer()
        await _rollover_subscription(
            session,
            repository,
            due_subscription,
            producer,  # type: ignore[arg-type]
            audit,  # type: ignore[arg-type]
        )

        assert due_subscription.status == "active"
        assert due_subscription.cancel_at_period_end is False
        assert due_subscription.current_period_start == previous_end
        assert due_subscription.current_period_end == previous_end + timedelta(days=30)
        assert producer.events[0][2] == "billing.subscription.downgrade_effective"
        assert audit.entries[0]["event_type"] == "billing.subscription.downgrade_effective"
        assert producer.events[0][3]["to_plan_slug"] == "free"
        assert producer.events[0][3]["data_exceeding_free_limits"] == {
            "workspaces": 0,
            "agents": 0,
            "users": 0,
        }

        await session.rollback()
