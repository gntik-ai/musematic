from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.status_page.schemas import OverallState
from platform.status_page.service import (
    CURRENT_SNAPSHOT_KEY,
    LAST_GOOD_SNAPSHOT_KEY,
    StatusPageService,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest


class _RedisStub:
    def __init__(self) -> None:
        self.values: dict[str, tuple[bytes, int | None]] = {}

    async def get(self, key: str) -> bytes | None:
        item = self.values.get(key)
        return None if item is None else item[0]

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self.values[key] = (value, ttl)


class _RepoStub:
    def __init__(self, *, active_maintenance: bool = False) -> None:
        self.rows: list[SimpleNamespace] = []
        self.active_maintenance = active_maintenance

    async def list_active_incidents(self) -> list[SimpleNamespace]:
        return []

    async def list_recent_resolved_incidents(self, *, days: int = 7) -> list[SimpleNamespace]:
        assert days == 7
        return []

    async def list_scheduled_maintenance(self, *, days: int = 30) -> list[SimpleNamespace]:
        assert days == 30
        return []

    async def list_active_maintenance(self) -> list[SimpleNamespace]:
        if not self.active_maintenance:
            return []
        now = datetime.now(UTC)
        return [
            SimpleNamespace(
                id=uuid4(),
                announcement_text="Maintenance window",
                reason="Planned maintenance",
                starts_at=now - timedelta(minutes=5),
                ends_at=now + timedelta(minutes=55),
                blocks_writes=True,
            )
        ]

    async def get_uptime_30d(self) -> dict[str, dict[str, int | float]]:
        return {}

    async def insert_snapshot(
        self,
        *,
        generated_at: datetime,
        overall_state: str,
        payload: dict,
        source_kind: str,
        created_by=None,
    ) -> SimpleNamespace:
        row = SimpleNamespace(
            id=uuid4(),
            generated_at=generated_at,
            overall_state=overall_state,
            payload=payload,
            source_kind=source_kind,
            created_by=created_by,
        )
        self.rows.append(row)
        return row

    async def get_current_snapshot(self) -> SimpleNamespace | None:
        return self.rows[-1] if self.rows else None

    async def get_component_history(self, component_id: str, *, days: int = 30) -> list[dict]:
        return []


class _DispatchRepoStub:
    def __init__(self) -> None:
        self.subscriptions = [
            SimpleNamespace(
                id=uuid4(),
                channel="email",
                target="all@example.com",
                scope_components=[],
            ),
            SimpleNamespace(
                id=uuid4(),
                channel="email",
                target="api@example.com",
                scope_components=["control-plane-api"],
            ),
            SimpleNamespace(
                id=uuid4(),
                channel="email",
                target="web@example.com",
                scope_components=["web-app"],
            ),
        ]
        self.dispatches: list[dict] = []

    async def list_confirmed_subscriptions_for_event(
        self,
        *,
        affected_components: list[str],
    ) -> list[SimpleNamespace]:
        affected = set(affected_components)
        return [
            subscription
            for subscription in self.subscriptions
            if not subscription.scope_components
            or affected.intersection(subscription.scope_components)
        ]

    async def insert_dispatch(self, **kwargs) -> SimpleNamespace:
        self.dispatches.append(kwargs)
        return SimpleNamespace(id=uuid4(), **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("component_states", "active_maintenance", "expected"),
    [
        (["operational", "operational"], False, OverallState.operational),
        (["operational", "degraded"], False, OverallState.degraded),
        (["operational", "partial_outage"], False, OverallState.partial_outage),
        (["partial_outage", "partial_outage"], False, OverallState.full_outage),
        (["operational", "operational"], True, OverallState.maintenance),
    ],
)
async def test_compose_snapshot_overall_state_aggregation(
    component_states: list[str],
    active_maintenance: bool,
    expected: OverallState,
) -> None:
    repo = _RepoStub(active_maintenance=active_maintenance)
    redis = _RedisStub()
    service = StatusPageService(repository=repo, redis_client=redis)
    now = datetime.now(UTC)
    components = [
        {
            "id": f"component-{index}",
            "name": f"Component {index}",
            "state": state,
            "last_check_at": now,
            "uptime_30d_pct": 99.9,
        }
        for index, state in enumerate(component_states)
    ]

    snapshot = await service.compose_current_snapshot(component_health=components)

    assert snapshot.overall_state is expected
    assert repo.rows[-1].overall_state == expected.value
    assert repo.rows[-1].payload["overall_state"] == expected.value
    assert redis.values[CURRENT_SNAPSHOT_KEY][1] == 90
    assert redis.values[LAST_GOOD_SNAPSHOT_KEY][1] == 24 * 60 * 60


@pytest.mark.asyncio
async def test_dispatch_fanout() -> None:
    repo = _DispatchRepoStub()
    service = StatusPageService(repository=repo)
    incident_id = uuid4()

    sent = await service.dispatch_event(
        "incident.created",
        {
            "incident_id": str(incident_id),
            "title": "Control-plane incident",
            "components_affected": ["control-plane-api"],
        },
    )

    assert sent == 2
    assert [item["subscription_id"] for item in repo.dispatches] == [
        repo.subscriptions[0].id,
        repo.subscriptions[1].id,
    ]
    assert all(item["event_id"] == incident_id for item in repo.dispatches)
