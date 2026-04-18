from __future__ import annotations

from platform.registry.models import LifecycleStatus
from platform.registry.service import RegistryService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.registry_support import (
    AsyncOpenSearchStub,
    AsyncQdrantStub,
    ObjectStorageStub,
    RegistryRepoStub,
    build_namespace,
    build_profile,
    build_recording_producer,
    build_registry_settings,
)


class WorkspaceServiceStub:
    def __init__(self, workspace_id: UUID, actor_id: UUID, *, role: str = "owner") -> None:
        self.workspace_id = workspace_id
        self.actor_id = actor_id
        self.role = role

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        if user_id == self.actor_id:
            return [self.workspace_id]
        return []

    async def get_membership(self, workspace_id: UUID, actor_id: UUID):
        if workspace_id == self.workspace_id and actor_id == self.actor_id:
            return SimpleNamespace(role=self.role)
        return None


class RuntimeControllerStub:
    def __init__(self, instances: list[str]) -> None:
        self.instances = list(instances)
        self.stopped: list[str] = []

    async def list_active_instances(self, agent_fqn: str) -> list[str]:
        del agent_fqn
        return list(self.instances)

    async def stop_runtime(self, execution_id: str) -> None:
        self.stopped.append(execution_id)


def _build_service(*, workspace_id: UUID, actor_id: UUID, role: str = "owner"):
    repo = RegistryRepoStub()
    service = RegistryService(
        repository=repo,
        object_storage=ObjectStorageStub(),
        opensearch=AsyncOpenSearchStub(),
        qdrant=AsyncQdrantStub(),
        workspaces_service=WorkspaceServiceStub(workspace_id, actor_id, role=role),
        event_producer=build_recording_producer(),
        settings=build_registry_settings(),
    )
    return service, repo


@pytest.mark.asyncio
async def test_decommission_stops_instances_is_idempotent_and_publishes_event(monkeypatch) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id, name="finance")
    profile = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="tax-reconciler",
        status=LifecycleStatus.published,
    )
    service, repo = _build_service(workspace_id=workspace_id, actor_id=actor_id)
    repo.profiles_by_id[profile.id] = profile
    repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    runtime_controller = RuntimeControllerStub(["inst-1", "inst-2"])

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_index_or_flag", _noop)

    first = await service.decommission_agent(
        workspace_id,
        profile.id,
        "Regulatory retirement Q2 2026",
        actor_id,
        runtime_controller,
        actor_is_platform_admin=True,
    )
    second = await service.decommission_agent(
        workspace_id,
        profile.id,
        "A different reason that must not overwrite the original.",
        actor_id,
        runtime_controller,
        actor_is_platform_admin=True,
    )

    stored = repo.profiles_by_id[profile.id]
    assert runtime_controller.stopped == ["inst-1", "inst-2"]
    assert first.active_instances_stopped == 2
    assert second.active_instances_stopped == 0
    assert first.decommissioned_at == second.decommissioned_at
    assert (
        first.decommission_reason == second.decommission_reason == "Regulatory retirement Q2 2026"
    )
    assert stored.status is LifecycleStatus.decommissioned
    assert stored.decommissioned_by == actor_id
    assert service.event_producer.events[-1]["event_type"] == "registry.agent.decommissioned"
    assert (
        service.event_producer.events[-1]["payload"]["active_instance_count_at_decommission"] == 2
    )
