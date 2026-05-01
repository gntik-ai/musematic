from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.status_page.repository import StatusPageRepository
from types import SimpleNamespace
from uuid import uuid4

import pytest


class _ScalarResult:
    def __init__(self, rows: list[object] | None = None, one: object | None = None) -> None:
        self._rows = rows or []
        self._one = one

    def all(self) -> list[object]:
        return self._rows

    def scalar_one_or_none(self) -> object | None:
        return self._one


class _ExecuteResult:
    def __init__(self, rows: list[object] | None = None, one: object | None = None) -> None:
        self._scalar = _ScalarResult(rows, one)

    def scalars(self) -> _ScalarResult:
        return self._scalar

    def scalar_one_or_none(self) -> object | None:
        return self._scalar.scalar_one_or_none()


class _SessionStub:
    def __init__(self, *results: _ExecuteResult) -> None:
        self.results = list(results)
        self.added: list[object] = []
        self.flushes = 0
        self.statements: list[object] = []

    async def execute(self, statement: object) -> _ExecuteResult:
        self.statements.append(statement)
        return self.results.pop(0) if self.results else _ExecuteResult()

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushes += 1


def _snapshot_row(payload: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        generated_at=datetime.now(UTC),
        payload=payload if payload is not None else {},
        source_kind="poll",
    )


def _subscription(**overrides: object) -> SimpleNamespace:
    values = {
        "id": uuid4(),
        "user_id": uuid4(),
        "workspace_id": None,
        "channel": "email",
        "target": "dev@example.test",
        "scope_components": [],
        "health": "healthy",
        "confirmed_at": datetime.now(UTC),
        "unsubscribe_token_hash": b"old",
        "confirmation_token_hash": b"confirm",
        "webhook_id": None,
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_repository_snapshot_component_and_uptime_paths() -> None:
    component = {"id": "api", "state": "operational"}
    snapshot = _snapshot_row({"components": [component], "uptime_30d": {"api": {"pct": 99}}})
    history_rows = [
        _snapshot_row({"components": "bad"}),
        _snapshot_row({"components": [{"id": "other"}, component]}),
    ]
    session = _SessionStub(
        _ExecuteResult(one=snapshot),
        _ExecuteResult(one=snapshot),
        _ExecuteResult(rows=history_rows),
        _ExecuteResult(one=snapshot),
        _ExecuteResult(one=None),
    )
    repository = StatusPageRepository(session)  # type: ignore[arg-type]

    assert await repository.get_current_snapshot() is snapshot
    inserted = await repository.insert_snapshot(
        generated_at=datetime.now(UTC),
        overall_state="operational",
        payload={},
        source_kind="poll",
    )
    assert inserted in session.added
    assert await repository.list_components() == [component]
    assert await repository.get_component_history("api") == [
        {"at": history_rows[1].generated_at, "state": "operational"}
    ]
    assert await repository.get_uptime_30d() == {"api": {"pct": 99}}
    assert await repository.list_components() == []


@pytest.mark.asyncio
async def test_repository_query_and_mutation_paths() -> None:
    now = datetime.now(UTC)
    subscription = _subscription()
    matching = _subscription(scope_components=["control-plane-api"])
    skipped = _subscription(scope_components=["web-app"])
    session = _SessionStub(
        _ExecuteResult(rows=[SimpleNamespace(triggered_at=now)]),
        _ExecuteResult(rows=[SimpleNamespace(resolved_at=now)]),
        _ExecuteResult(rows=[SimpleNamespace(starts_at=now)]),
        _ExecuteResult(rows=[SimpleNamespace(starts_at=now + timedelta(hours=1))]),
        _ExecuteResult(rows=[subscription, matching, skipped]),
        _ExecuteResult(one=subscription),
        _ExecuteResult(one=subscription),
        _ExecuteResult(one=subscription),
        _ExecuteResult(rows=[subscription]),
        _ExecuteResult(one=subscription),
        _ExecuteResult(one=subscription),
        _ExecuteResult(one=subscription),
        _ExecuteResult(one=subscription),
    )
    repository = StatusPageRepository(session)  # type: ignore[arg-type]

    assert len(await repository.list_active_incidents()) == 1
    assert len(await repository.list_recent_resolved_incidents(days=3)) == 1
    assert len(await repository.list_active_maintenance()) == 1
    assert len(await repository.list_scheduled_maintenance(days=10)) == 1
    assert await repository.list_confirmed_subscriptions_for_event(
        affected_components=["control-plane-api"]
    ) == [subscription, matching]

    created = await repository.create_subscription(
        channel="email",
        target="dev@example.test",
        scope_components=[],
    )
    assert created in session.added
    assert await repository.get_subscription_by_confirmation_hash(b"confirm") is subscription
    assert await repository.get_subscription_by_unsubscribe_hash(b"old") is subscription
    assert await repository.get_subscription(subscription.id) is subscription
    assert await repository.confirm_subscription(subscription) is subscription
    assert subscription.health == "healthy"
    assert subscription.confirmation_token_hash is None
    assert await repository.mark_unsubscribed(subscription) is subscription
    assert subscription.health == "unsubscribed"
    assert await repository.rotate_unsubscribe_token(subscription, b"new") is subscription
    assert subscription.unsubscribe_token_hash == b"new"
    assert await repository.list_user_subscriptions(user_id=subscription.user_id) == [subscription]
    assert await repository.get_user_subscription(
        subscription_id=subscription.id,
        user_id=subscription.user_id,
    ) is subscription
    assert await repository.update_user_subscription(
        subscription_id=subscription.id,
        user_id=subscription.user_id,
        values={},
    ) is subscription
    assert await repository.update_user_subscription(
        subscription_id=subscription.id,
        user_id=subscription.user_id,
        values={"target": "new@example.test"},
    ) is subscription
    dispatch = await repository.insert_dispatch(
        subscription_id=subscription.id,
        event_kind="incident.created",
        event_id=uuid4(),
        outcome="sent",
    )
    assert dispatch in session.added
