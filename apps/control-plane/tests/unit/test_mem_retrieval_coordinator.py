from __future__ import annotations

from platform.memory.models import MemoryScope
from platform.memory.retrieval_coordinator import RetrievalCoordinator
from platform.memory.schemas import RetrievalQuery
from uuid import uuid4

import pytest

from tests.memory_support import (
    MemoryRepoStub,
    Neo4jPathStub,
    Neo4jStub,
    QdrantStub,
    RegistryServiceStub,
    build_conflict,
    build_knowledge_node,
    build_memory_entry,
    build_settings,
    install_qdrant_models_stub,
)


@pytest.mark.asyncio
async def test_memory_retrieval_coordinator_fuses_sources_and_flags_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    install_qdrant_models_stub(monkeypatch)
    repo = MemoryRepoStub()
    entry = build_memory_entry(
        workspace_id=workspace_id,
        content="Customer ACME prefers invoice terms NET-30.",
        scope=MemoryScope.per_workspace,
    )
    agent_entry = build_memory_entry(
        workspace_id=workspace_id,
        agent_fqn="finance:writer",
        content="ACME approves invoice automation.",
    )
    node = build_knowledge_node(workspace_id=workspace_id, external_name="ACME")
    repo.memory_entries[entry.id] = entry
    repo.memory_entries[agent_entry.id] = agent_entry
    repo.nodes[node.id] = node
    conflict = build_conflict(
        workspace_id=workspace_id,
        memory_entry_id_a=entry.id,
        memory_entry_id_b=agent_entry.id,
    )
    repo.conflicts[conflict.id] = conflict
    qdrant = QdrantStub(
        search_results=[
            {
                "id": str(entry.id),
                "score": 0.9,
                "payload": {"memory_entry_id": str(entry.id)},
            }
        ]
    )
    coordinator = RetrievalCoordinator(
        repository=repo,
        qdrant=qdrant,
        neo4j=Neo4jStub(),
        settings=build_settings(),
        registry_service=RegistryServiceStub(role_types=["executor", "orchestrator"]),
    )

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("platform.memory.retrieval_coordinator.request_embedding", _fake_embedding)

    response = await coordinator.retrieve(
        query=RetrievalQuery(query_text="invoice terms", top_k=5),
        agent_fqn="finance:writer",
        workspace_id=workspace_id,
    )

    assert response.results
    assert {"vector", "keyword"}.issubset(set(response.results[0].sources_contributed))
    assert response.results[0].contradiction_flag is True


@pytest.mark.asyncio
async def test_memory_retrieval_coordinator_reports_partial_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    install_qdrant_models_stub(monkeypatch)
    repo = MemoryRepoStub()
    repo.nodes[uuid4()] = build_knowledge_node(workspace_id=workspace_id, external_name="ACME")
    coordinator = RetrievalCoordinator(
        repository=repo,
        qdrant=QdrantStub(fail_search=RuntimeError("vector down")),
        neo4j=Neo4jStub(fail_traverse=RuntimeError("graph down")),
        settings=build_settings(),
        registry_service=RegistryServiceStub(),
    )

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.3, 0.2, 0.1]

    monkeypatch.setattr("platform.memory.retrieval_coordinator.request_embedding", _fake_embedding)

    async def _graph_down(*, workspace_id: object, query_text: str, limit: int) -> list[object]:
        del workspace_id, query_text, limit
        raise RuntimeError("graph down")

    monkeypatch.setattr(repo, "list_knowledge_nodes_by_query", _graph_down)

    response = await coordinator.retrieve(
        query=RetrievalQuery(query_text="ACME", top_k=5, include_contradictions=False),
        agent_fqn="finance:writer",
        workspace_id=workspace_id,
    )

    assert set(response.partial_sources) == {"vector", "graph"}


@pytest.mark.asyncio
async def test_memory_retrieval_coordinator_scope_visibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    install_qdrant_models_stub(monkeypatch)
    repo = MemoryRepoStub()
    own_entry = build_memory_entry(workspace_id=workspace_id, agent_fqn="finance:writer")
    other_entry = build_memory_entry(workspace_id=workspace_id, agent_fqn="finance:other")
    shared_entry = build_memory_entry(
        workspace_id=workspace_id,
        agent_fqn="finance:orchestrator",
        scope=MemoryScope.shared_orchestrator,
    )
    repo.memory_entries[own_entry.id] = own_entry
    repo.memory_entries[other_entry.id] = other_entry
    repo.memory_entries[shared_entry.id] = shared_entry
    qdrant = QdrantStub(
        search_results=[
            {
                "id": str(own_entry.id),
                "score": 0.9,
                "payload": {"memory_entry_id": str(own_entry.id)},
            },
            {
                "id": str(other_entry.id),
                "score": 0.8,
                "payload": {"memory_entry_id": str(other_entry.id)},
            },
            {
                "id": str(shared_entry.id),
                "score": 0.7,
                "payload": {"memory_entry_id": str(shared_entry.id)},
            },
        ]
    )
    coordinator = RetrievalCoordinator(
        repository=repo,
        qdrant=qdrant,
        neo4j=Neo4jStub(traverse_results=[Neo4jPathStub(nodes=[], relationships=[])]),
        settings=build_settings(),
        registry_service=RegistryServiceStub(role_types=["executor"]),
    )

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.1, 0.1, 0.1]

    monkeypatch.setattr("platform.memory.retrieval_coordinator.request_embedding", _fake_embedding)

    response = await coordinator.retrieve(
        query=RetrievalQuery(query_text="ACME", top_k=10, include_contradictions=False),
        agent_fqn="finance:writer",
        workspace_id=workspace_id,
    )

    result_ids = {item.memory_entry_id for item in response.results}
    assert own_entry.id in result_ids
    assert other_entry.id not in result_ids
    assert shared_entry.id not in result_ids
