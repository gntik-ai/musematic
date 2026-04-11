from __future__ import annotations

from platform.memory.models import MemoryScope
from platform.memory.retrieval_coordinator import RetrievalCoordinator
from platform.memory.schemas import RetrievalQuery
from platform.memory.service import MemoryService
from platform.memory.write_gate import MemoryWriteGate
from platform.workspaces.models import WorkspaceRole
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.memory_support import (
    MemoryRepoStub,
    Neo4jStub,
    QdrantStub,
    RedisRateLimitStub,
    RegistryServiceStub,
    WorkspacesServiceStub,
    build_memory_entry,
    build_settings,
    install_qdrant_models_stub,
)


def _build_service(
    *,
    repo: MemoryRepoStub,
    qdrant: QdrantStub | None = None,
    registry_service: RegistryServiceStub | None = None,
) -> MemoryService:
    settings = build_settings()
    resolved_qdrant = qdrant or QdrantStub()
    resolved_registry = registry_service or RegistryServiceStub(role_types=["executor"])
    workspaces_service = WorkspacesServiceStub(membership_role=WorkspaceRole.owner)
    return MemoryService(
        repository=repo,
        write_gate=MemoryWriteGate(
            repository=repo,
            qdrant=resolved_qdrant,
            redis_client=RedisRateLimitStub(),
            settings=settings,
            registry_service=resolved_registry,
            workspaces_service=workspaces_service,
            producer=RecordingProducer(),
        ),
        retrieval_coordinator=RetrievalCoordinator(
            repository=repo,
            qdrant=resolved_qdrant,
            neo4j=Neo4jStub(),
            settings=settings,
            registry_service=resolved_registry,
        ),
        neo4j=Neo4jStub(),
        qdrant=resolved_qdrant,
        settings=settings,
        producer=RecordingProducer(),
        workspaces_service=workspaces_service,
        registry_service=resolved_registry,
    )


@pytest.mark.asyncio
async def test_memory_scope_isolation_filters_list_results_for_requester() -> None:
    workspace_id = uuid4()
    repo = MemoryRepoStub()
    own_entry = build_memory_entry(workspace_id=workspace_id, agent_fqn="finance:writer")
    peer_entry = build_memory_entry(workspace_id=workspace_id, agent_fqn="finance:other")
    workspace_entry = build_memory_entry(
        workspace_id=workspace_id,
        scope=MemoryScope.per_workspace,
    )
    shared_entry = build_memory_entry(
        workspace_id=workspace_id,
        agent_fqn="finance:orchestrator",
        scope=MemoryScope.shared_orchestrator,
    )
    foreign_entry = build_memory_entry(workspace_id=uuid4(), scope=MemoryScope.per_workspace)
    for entry in (own_entry, peer_entry, workspace_entry, shared_entry, foreign_entry):
        repo.memory_entries[entry.id] = entry

    service = _build_service(repo=repo)

    visible, total = await service.list_memory_entries(
        workspace_id,
        "finance:writer",
        None,
        1,
        20,
    )

    result_ids = {item.id for item in visible}
    assert own_entry.id in result_ids
    assert workspace_entry.id in result_ids
    assert peer_entry.id not in result_ids
    assert shared_entry.id not in result_ids
    assert foreign_entry.id not in result_ids
    assert total == 2


@pytest.mark.asyncio
async def test_memory_scope_isolation_allows_orchestrator_shared_visibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    install_qdrant_models_stub(monkeypatch)
    repo = MemoryRepoStub()
    shared_entry = build_memory_entry(
        workspace_id=workspace_id,
        agent_fqn="finance:orchestrator",
        scope=MemoryScope.shared_orchestrator,
    )
    repo.memory_entries[shared_entry.id] = shared_entry
    qdrant = QdrantStub(
        search_results=[
            {
                "id": str(shared_entry.id),
                "score": 0.9,
                "payload": {"memory_entry_id": str(shared_entry.id)},
            }
        ]
    )
    service = _build_service(
        repo=repo,
        qdrant=qdrant,
        registry_service=RegistryServiceStub(role_types=["orchestrator"]),
    )

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("platform.memory.retrieval_coordinator.request_embedding", _fake_embedding)

    response = await service.retrieve(
        RetrievalQuery(query_text="shared", include_contradictions=False),
        "finance:orchestrator",
        workspace_id,
    )

    assert [item.memory_entry_id for item in response.results] == [shared_entry.id]
