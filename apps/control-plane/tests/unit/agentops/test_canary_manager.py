from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.agentops.canary.manager import CanaryManager
from platform.agentops.exceptions import CanaryConflictError, CanaryStateError
from platform.agentops.models import CanaryDeployment, CanaryDeploymentStatus
from platform.agentops.schemas import CanaryDeploymentCreateRequest
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest


class _RedisStub:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, bytes, int | None]] = []
        self.delete_calls: list[str] = []

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self.set_calls.append((key, value, ttl))

    async def delete(self, key: str) -> None:
        self.delete_calls.append(key)


class _GovernanceStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def record(
        self,
        event_type: str,
        agent_fqn: str,
        workspace_id: UUID,
        **kwargs: Any,
    ) -> None:
        self.events.append(
            (
                event_type,
                {
                    "agent_fqn": agent_fqn,
                    "workspace_id": workspace_id,
                    **kwargs,
                },
            )
        )


class _RepositoryStub:
    def __init__(self, *, active_canary: CanaryDeployment | None = None) -> None:
        self.active_canary = active_canary
        self.created: list[CanaryDeployment] = []
        self.updated: list[CanaryDeployment] = []
        self.alerts: list[SimpleNamespace] = []

    async def get_active_canary(
        self, agent_fqn: str, workspace_id: UUID
    ) -> CanaryDeployment | None:
        del agent_fqn, workspace_id
        return self.active_canary

    async def create_canary(self, canary: CanaryDeployment) -> CanaryDeployment:
        now = datetime.now(UTC)
        if getattr(canary, "id", None) is None:
            canary.id = uuid4()
        canary.created_at = now
        canary.updated_at = now
        self.active_canary = canary
        self.created.append(canary)
        return canary

    async def get_canary(self, canary_id: UUID) -> CanaryDeployment | None:
        if self.active_canary is not None and self.active_canary.id == canary_id:
            return self.active_canary
        for item in self.updated:
            if item.id == canary_id:
                return item
        return None

    async def update_canary(self, canary: CanaryDeployment) -> CanaryDeployment:
        canary.updated_at = datetime.now(UTC)
        if canary.status != CanaryDeploymentStatus.active.value:
            self.active_canary = None
        self.updated.append(canary)
        return canary

    async def list_regression_alerts(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
        new_revision_id: UUID | None = None,
    ) -> tuple[list[SimpleNamespace], str | None]:
        del agent_fqn, workspace_id, cursor, limit, status, new_revision_id
        return self.alerts, None

    async def update_regression_alert(self, alert: SimpleNamespace) -> SimpleNamespace:
        return alert


def _request(workspace_id: UUID) -> CanaryDeploymentCreateRequest:
    return CanaryDeploymentCreateRequest(
        workspace_id=workspace_id,
        production_revision_id=uuid4(),
        canary_revision_id=uuid4(),
        traffic_percentage=10,
        observation_window_hours=2.0,
        quality_tolerance_pct=5.0,
        latency_tolerance_pct=5.0,
        error_rate_tolerance_pct=5.0,
        cost_tolerance_pct=5.0,
    )


@pytest.mark.asyncio
async def test_start_writes_redis_key() -> None:
    workspace_id = uuid4()
    now = datetime(2026, 4, 14, 9, 0, tzinfo=UTC)
    repository = _RepositoryStub()
    redis = _RedisStub()
    manager = CanaryManager(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=_GovernanceStub(),  # type: ignore[arg-type]
        redis_client=redis,
        now_factory=lambda: now,
    )

    deployment = await manager.start(
        "finance:agent",
        _request(workspace_id),
        initiated_by=uuid4(),
    )

    assert deployment.status == "active"
    assert len(redis.set_calls) == 1
    key, value, ttl = redis.set_calls[0]
    assert key == f"canary:{workspace_id}:finance:agent"
    assert ttl == 10800
    payload = json.loads(value.decode())
    assert payload["traffic_percentage"] == 10
    assert payload["canary_revision_id"] == str(deployment.canary_revision_id)


@pytest.mark.asyncio
async def test_start_raises_conflict_when_active_canary_exists() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(active_canary=SimpleNamespace())
    manager = CanaryManager(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=None,
        redis_client=_RedisStub(),
    )

    with pytest.raises(CanaryConflictError):
        await manager.start("finance:agent", _request(workspace_id), initiated_by=uuid4())


@pytest.mark.asyncio
async def test_promote_clears_redis_key_and_sets_auto_promoted_status() -> None:
    workspace_id = uuid4()
    redis = _RedisStub()
    repository = _RepositoryStub()
    manager = CanaryManager(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=None,
        redis_client=redis,
    )
    deployment = await manager.start("finance:agent", _request(workspace_id), initiated_by=uuid4())

    promoted = await manager.promote(deployment.id, manual=False)

    assert promoted.status == "auto_promoted"
    assert redis.delete_calls == [f"canary:{workspace_id}:finance:agent"]
    assert promoted.promoted_at is not None


@pytest.mark.asyncio
async def test_rollback_clears_redis_key_and_marks_related_regression_alerts() -> None:
    workspace_id = uuid4()
    redis = _RedisStub()
    repository = _RepositoryStub()
    repository.alerts = [SimpleNamespace(triggered_rollback=False)]
    manager = CanaryManager(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=None,
        redis_client=redis,
    )
    deployment = await manager.start("finance:agent", _request(workspace_id), initiated_by=uuid4())

    rolled_back = await manager.rollback(
        deployment.id,
        reason="auto:quality_score",
        manual=False,
    )

    assert rolled_back.status == "auto_rolled_back"
    assert redis.delete_calls == [f"canary:{workspace_id}:finance:agent"]
    assert repository.alerts[0].triggered_rollback is True


@pytest.mark.asyncio
async def test_canary_manager_manual_override_and_error_paths() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub()
    manager = CanaryManager(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=None,
        redis_client=None,
        now_factory=lambda: datetime(2026, 4, 14, 9, 0, tzinfo=UTC),
    )

    deployment = await manager.start("finance:agent", _request(workspace_id), initiated_by=uuid4())
    promoted = await manager.promote(
        deployment.id,
        manual=True,
        reason="manual promote",
        actor=uuid4(),
    )

    deployment = await manager.start("finance:agent", _request(workspace_id), initiated_by=uuid4())
    rolled_back = await manager.rollback(
        deployment.id,
        reason="manual rollback",
        manual=True,
        actor=uuid4(),
    )

    with pytest.raises(CanaryStateError):
        await manager._get_active_canary(uuid4())

    inactive = SimpleNamespace(id=uuid4(), status="auto_promoted")
    repository.active_canary = inactive
    repository.updated.append(inactive)
    with pytest.raises(CanaryStateError):
        await manager._get_active_canary(inactive.id)

    assert promoted.manual_override_by is not None
    assert promoted.manual_override_reason == "manual promote"
    assert rolled_back.manual_override_by is not None
    assert rolled_back.manual_override_reason == "manual rollback"
    assert manager._ttl_seconds(datetime(2026, 4, 14, 9, 30, tzinfo=UTC)) > 0
