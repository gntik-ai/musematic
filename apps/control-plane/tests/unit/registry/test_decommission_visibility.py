from __future__ import annotations

from platform.marketplace.schemas import MarketplaceSearchRequest
from platform.registry.models import LifecycleStatus
from platform.registry.schemas import AgentDiscoveryParams
from platform.registry.service import RegistryService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.marketplace_support import (
    build_agent_document,
    build_marketplace_app,
    build_marketplace_settings,
    build_search_service,
)
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


class RegistryResolveStub:
    def __init__(self, profile) -> None:
        self.profile = profile

    async def resolve_fqn(
        self, fqn: str, *, workspace_id: UUID, actor_id=None, requesting_agent_id=None
    ):
        del actor_id, requesting_agent_id
        if fqn != self.profile.fqn or workspace_id != self.profile.workspace_id:
            raise LookupError(fqn)
        return self.profile


@pytest.mark.asyncio
async def test_marketplace_search_excludes_decommissioned_agents() -> None:
    workspace_id = uuid4()
    active_id = uuid4()
    active_doc = build_agent_document(agent_id=active_id, fqn="finance:active", status="published")
    retired_doc = build_agent_document(
        agent_id=uuid4(), fqn="finance:retired", status="decommissioned"
    )
    service, repository, _opensearch, _qdrant, _workspaces = build_search_service(
        documents=[active_doc, retired_doc],
        settings=build_marketplace_settings(),
    )
    await repository.get_or_create_quality_aggregate(active_id)

    response = await service.search(
        MarketplaceSearchRequest(query="", page=1, page_size=20),
        workspace_id,
        uuid4(),
    )

    assert [item.fqn for item in response.results] == ["finance:active"]


@pytest.mark.asyncio
async def test_direct_fqn_lookup_returns_decommissioned_non_invocable_listing() -> None:
    workspace_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance")
    profile = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="tax-reconciler",
        status=LifecycleStatus.decommissioned,
    )
    search_service = build_search_service(
        documents=[],
        registry_service=RegistryResolveStub(profile),
        settings=build_marketplace_settings(),
    )[0]
    app = build_marketplace_app(
        current_user={"sub": str(uuid4()), "workspace_id": str(workspace_id)},
        search_service=search_service,
    )

    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/marketplace/agents/finance/tax-reconciler",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "decommissioned"
    assert body["invocable"] is False


@pytest.mark.asyncio
async def test_registry_list_agents_excludes_decommissioned_for_picker_surfaces() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance", created_by=actor_id)
    active = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="active",
        status=LifecycleStatus.published,
    )
    retired = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="retired",
        status=LifecycleStatus.decommissioned,
    )
    repo = RegistryRepoStub()
    for profile in (active, retired):
        repo.profiles_by_id[profile.id] = profile
        repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    service = RegistryService(
        repository=repo,
        object_storage=ObjectStorageStub(),
        opensearch=AsyncOpenSearchStub(),
        qdrant=AsyncQdrantStub(),
        workspaces_service=WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]}),
        event_producer=None,
        settings=build_registry_settings(),
    )

    response = await service.list_agents(
        AgentDiscoveryParams(
            workspace_id=workspace_id, status=LifecycleStatus.published, maturity_min=0
        ),
        actor_id=actor_id,
    )

    assert [item.fqn for item in response.items] == ["finance:active"]


@pytest.mark.asyncio
async def test_decommission_preserves_identity_for_audit_and_analytics_queries() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance", created_by=actor_id)
    profile = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="historic",
        status=LifecycleStatus.published,
    )
    repo = RegistryRepoStub()
    repo.profiles_by_id[profile.id] = profile
    repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    history = {profile.id: SimpleNamespace(total_executions=4)}

    await repo.persist_decommission(
        profile, reason="Regulatory retirement Q2 2026", actor_id=actor_id
    )

    assert (await repo.get_agent_by_id_any(profile.id)) is profile
    assert history[profile.id].total_executions == 4
    assert profile.status is LifecycleStatus.decommissioned
