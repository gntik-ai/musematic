from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.simulation.exceptions import SimulationNotFoundError
from platform.simulation.models import DigitalTwin
from platform.simulation.twins.snapshot import TwinSnapshotService
from types import SimpleNamespace
from uuid import uuid4

import pytest


class FakeRepository:
    def __init__(self) -> None:
        self.twins: dict[object, DigitalTwin] = {}
        self.deactivated: list[object] = []

    async def create_twin(self, twin: DigitalTwin) -> DigitalTwin:
        twin.id = uuid4()
        twin.created_at = datetime.now(UTC)
        twin.updated_at = twin.created_at
        self.twins[twin.id] = twin
        return twin

    async def get_twin(self, twin_id: object, workspace_id: object) -> DigitalTwin | None:
        twin = self.twins.get(twin_id)
        if twin is None or twin.workspace_id != workspace_id:
            return None
        return twin

    async def update_twin_active(
        self,
        twin_id: object,
        workspace_id: object,
        is_active: bool,
    ) -> None:
        twin = await self.get_twin(twin_id, workspace_id)
        assert twin is not None
        twin.is_active = is_active
        self.deactivated.append(twin_id)


class FakeRegistry:
    def __init__(self, profile: object | None = None) -> None:
        self.revision_id = uuid4()
        self.profile = profile or SimpleNamespace(
            fqn="namespace.agent",
            latest_revision_id=self.revision_id,
            status="active",
        )

    async def get_agent_profile(self, agent_fqn, workspace_id):
        return self.profile if agent_fqn == "namespace.agent" else None

    async def get_agent_revision(self, revision_id):
        assert revision_id == self.revision_id
        return {
            "model_config": {"name": "claude"},
            "tool_selections": [{"name": "search"}],
            "policies": ["p1"],
            "context_profile_id": "ctx",
            "connector_suggestions": [{"type": "email"}],
        }


class FakeClickHouse:
    async def execute_query(self, sql, params):
        assert params["agent_fqn"] == "namespace.agent"
        return [
            {
                "date": f"2026-01-{day:02d}",
                "avg_quality_score": 0.8 + day / 100,
                "avg_response_time_ms": 100 - day,
                "avg_error_rate": 0.05,
                "execution_count": 10,
            }
            for day in range(1, 31)
        ]


class FakePublisher:
    def __init__(self) -> None:
        self.created: list[object] = []
        self.modified: list[object] = []

    async def twin_created(self, twin_id, workspace_id, agent_fqn):
        self.created.append((twin_id, workspace_id, agent_fqn))

    async def twin_modified(self, twin_id, workspace_id, parent_twin_id, version):
        self.modified.append((twin_id, workspace_id, parent_twin_id, version))


@pytest.mark.asyncio
async def test_create_twin_snapshots_registry_config_and_behavioral_history() -> None:
    workspace_id = uuid4()
    repository = FakeRepository()
    publisher = FakePublisher()
    service = TwinSnapshotService(
        repository=repository,
        registry_service=FakeRegistry(),
        clickhouse_client=FakeClickHouse(),
        publisher=publisher,
        settings=PlatformSettings(),
    )

    twin = await service.create_twin(agent_fqn="namespace.agent", workspace_id=workspace_id)

    assert twin.version == 1
    assert twin.config_snapshot["model"] == {"name": "claude"}
    assert twin.config_snapshot["tools"] == [{"name": "search"}]
    assert twin.behavioral_history_summary["history_days_used"] == 30
    assert twin.behavioral_history_summary["quality_trend"] == "improving"
    assert twin.behavioral_history_summary["response_trend"] == "improving"
    assert publisher.created == [(twin.id, workspace_id, "namespace.agent")]


@pytest.mark.asyncio
async def test_modify_twin_creates_new_version_and_preserves_parent() -> None:
    workspace_id = uuid4()
    repository = FakeRepository()
    current = await repository.create_twin(
        DigitalTwin(
            workspace_id=workspace_id,
            source_agent_fqn="namespace.agent",
            source_revision_id=uuid4(),
            version=1,
            config_snapshot={"model": {"name": "old"}},
            behavioral_history_summary={},
            modifications=[],
            is_active=True,
        )
    )
    publisher = FakePublisher()
    service = TwinSnapshotService(
        repository=repository,
        registry_service=FakeRegistry(),
        clickhouse_client=FakeClickHouse(),
        publisher=publisher,
        settings=PlatformSettings(),
    )

    new_twin = await service.modify_twin(
        twin_id=current.id,
        workspace_id=workspace_id,
        modifications=[{"field": "model.name", "value": "new", "description": "upgrade"}],
    )

    assert current.is_active is False
    assert new_twin.version == 2
    assert new_twin.parent_twin_id == current.id
    assert new_twin.config_snapshot["model"]["name"] == "new"
    assert publisher.modified == [(new_twin.id, workspace_id, current.id, 2)]


@pytest.mark.asyncio
async def test_create_twin_reports_archived_agents_and_missing_agents() -> None:
    workspace_id = uuid4()
    service = TwinSnapshotService(
        repository=FakeRepository(),
        registry_service=FakeRegistry(
            profile=SimpleNamespace(latest_revision_id=None, status="archived")
        ),
        clickhouse_client=None,
        publisher=FakePublisher(),
        settings=PlatformSettings(),
    )

    twin = await service.create_twin(agent_fqn="namespace.agent", workspace_id=workspace_id)
    assert "agent_archived" in twin.behavioral_history_summary["warning_flags"]

    with pytest.raises(SimulationNotFoundError):
        await service.create_twin(agent_fqn="missing.agent", workspace_id=workspace_id)
