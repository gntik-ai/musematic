from __future__ import annotations

from platform.registry.exceptions import AgentNotFoundError
from platform.registry.models import LifecycleStatus
from platform.registry.schemas import AgentDiscoveryParams
from platform.registry.service import RegistryService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.auth_support import RecordingProducer
from tests.registry_support import (
    AsyncOpenSearchStub,
    AsyncQdrantStub,
    ObjectStorageStub,
    RegistryRepoStub,
    WorkspacesServiceStub,
    build_namespace,
    build_profile,
    build_registry_settings,
)


def _build_service(
    *,
    zero_trust_enabled: bool,
    repo: RegistryRepoStub,
    workspaces_service: WorkspacesServiceStub | None = None,
    producer: RecordingProducer | None = None,
) -> tuple[RegistryService, RecordingProducer]:
    resolved_producer = producer or RecordingProducer()
    service = RegistryService(
        repository=repo,
        object_storage=ObjectStorageStub(),
        opensearch=AsyncOpenSearchStub(),
        qdrant=AsyncQdrantStub(),
        workspaces_service=workspaces_service,
        event_producer=resolved_producer,
        settings=build_registry_settings(
            VISIBILITY_ZERO_TRUST_ENABLED=zero_trust_enabled,
        ),
    )
    return service, resolved_producer


def _seed_profiles(
    requester_visibility: list[str],
) -> tuple[RegistryRepoStub, UUID, UUID, UUID, UUID]:
    workspace_id = uuid4()
    finance_namespace = build_namespace(workspace_id=workspace_id, name="finance-ops")
    hr_namespace = build_namespace(workspace_id=workspace_id, name="hr-ops")
    secret_namespace = build_namespace(workspace_id=workspace_id, name="secret-ops")

    visible = build_profile(
        workspace_id=workspace_id,
        namespace=finance_namespace,
        local_name="visible",
        status=LifecycleStatus.published,
    )
    hr_visible = build_profile(
        workspace_id=workspace_id,
        namespace=hr_namespace,
        local_name="hr-visible",
        status=LifecycleStatus.published,
    )
    hidden = build_profile(
        workspace_id=workspace_id,
        namespace=secret_namespace,
        local_name="hidden",
        status=LifecycleStatus.published,
    )
    requester_id = uuid4()
    requester = build_profile(
        profile_id=requester_id,
        workspace_id=workspace_id,
        namespace=hr_namespace,
        local_name="requester",
        visibility_agents=requester_visibility,
        status=LifecycleStatus.published,
    )

    repo = RegistryRepoStub()
    for profile in (visible, hr_visible, hidden, requester):
        repo.profiles_by_id[profile.id] = profile
        repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
        repo.revisions_by_profile[profile.id] = []
    return repo, workspace_id, requester_id, visible.id, hidden.id


@pytest.mark.asyncio
async def test_visibility_flag_default_deny_and_audit_event() -> None:
    repo, workspace_id, requester_id, _visible_id, hidden_id = _seed_profiles([])
    service, producer = _build_service(zero_trust_enabled=True, repo=repo)

    listed = await service.list_agents(
        AgentDiscoveryParams(workspace_id=workspace_id, limit=10, offset=0),
        requesting_agent_id=requester_id,
    )

    assert listed.items == []
    assert listed.total == 0

    with pytest.raises(AgentNotFoundError):
        await service.get_agent(
            workspace_id,
            hidden_id,
            actor_id=None,
            requesting_agent_id=requester_id,
        )

    assert producer.events[-1]["event_type"] == "registry.agent.visibility_denied"
    assert producer.events[-1]["payload"]["block_reason"] == "visibility_denied"


@pytest.mark.asyncio
async def test_visibility_flag_off_preserves_existing_registry_behavior() -> None:
    repo, workspace_id, requester_id, visible_id, hidden_id = _seed_profiles([])
    service, _producer = _build_service(zero_trust_enabled=False, repo=repo)

    listed = await service.list_agents(
        AgentDiscoveryParams(workspace_id=workspace_id, limit=10, offset=0),
        requesting_agent_id=requester_id,
    )

    assert listed.total == len(listed.items) == 4
    assert {requester_id, visible_id, hidden_id}.issubset({item.id for item in listed.items})
    fetched = await service.get_agent(
        workspace_id,
        hidden_id,
        actor_id=None,
        requesting_agent_id=requester_id,
    )
    assert fetched.id == hidden_id


@pytest.mark.asyncio
async def test_visibility_patterns_union_agent_and_workspace_grants() -> None:
    repo, workspace_id, requester_id, visible_id, _hidden_id = _seed_profiles(["hr-ops:*"])
    workspaces = WorkspacesServiceStub(
        visibility_by_workspace={
            workspace_id: SimpleNamespace(
                visibility_agents=["finance-ops:*"],
                visibility_tools=[],
            )
        }
    )
    service, _producer = _build_service(
        zero_trust_enabled=True,
        repo=repo,
        workspaces_service=workspaces,
    )

    listed = await service.list_agents(
        AgentDiscoveryParams(workspace_id=workspace_id, limit=10, offset=0),
        requesting_agent_id=requester_id,
    )

    assert listed.total == len(listed.items) == 3
    assert {item.fqn for item in listed.items} == {
        "finance-ops:visible",
        "hr-ops:hr-visible",
        "hr-ops:requester",
    }
    assert visible_id in {item.id for item in listed.items}


@pytest.mark.asyncio
async def test_visibility_uses_workspace_grant_when_agent_patterns_are_empty() -> None:
    repo, workspace_id, requester_id, visible_id, _hidden_id = _seed_profiles([])
    workspaces = WorkspacesServiceStub(
        visibility_by_workspace={
            workspace_id: SimpleNamespace(
                visibility_agents=["finance-ops:*"],
                visibility_tools=[],
            )
        }
    )
    service, _producer = _build_service(
        zero_trust_enabled=True,
        repo=repo,
        workspaces_service=workspaces,
    )

    listed = await service.list_agents(
        AgentDiscoveryParams(workspace_id=workspace_id, limit=10, offset=0),
        requesting_agent_id=requester_id,
    )

    assert listed.total == len(listed.items) == 1
    assert listed.items[0].id == visible_id
