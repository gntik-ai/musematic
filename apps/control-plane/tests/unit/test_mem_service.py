from __future__ import annotations

from datetime import UTC, datetime
from platform.memory.exceptions import GraphUnavailableError, ScopeIsolationError
from platform.memory.models import MemoryScope, PatternStatus
from platform.memory.retrieval_coordinator import RetrievalCoordinator
from platform.memory.schemas import (
    ConflictResolution,
    CrossScopeTransferRequest,
    GraphTraversalQuery,
    KnowledgeEdgeCreate,
    KnowledgeNodeCreate,
    PatternNomination,
    PatternReview,
    RetrievalQuery,
    TrajectoryRecordCreate,
)
from platform.memory.service import MemoryService
from platform.memory.write_gate import MemoryWriteGate
from platform.workspaces.models import WorkspaceRole
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.memory_support import (
    MemoryRepoStub,
    Neo4jPathStub,
    Neo4jStub,
    QdrantStub,
    RedisRateLimitStub,
    RegistryServiceStub,
    WorkspacesServiceStub,
    build_conflict,
    build_knowledge_node,
    build_memory_entry,
    build_pattern_asset,
    build_settings,
    install_qdrant_models_stub,
)


def _build_service(
    *,
    repo: MemoryRepoStub | None = None,
    neo4j: Neo4jStub | None = None,
    qdrant: QdrantStub | None = None,
    workspaces_service: WorkspacesServiceStub | None = None,
    registry_service: RegistryServiceStub | None = None,
    producer: RecordingProducer | None = None,
) -> MemoryService:
    memory_repo = repo or MemoryRepoStub()
    qdrant_client = qdrant or QdrantStub()
    settings = build_settings()
    resolved_registry = registry_service or RegistryServiceStub(
        role_types=["executor", "orchestrator"]
    )
    resolved_workspaces = workspaces_service or WorkspacesServiceStub(
        membership_role=WorkspaceRole.owner
    )
    resolved_neo4j = neo4j or Neo4jStub()
    write_gate = MemoryWriteGate(
        repository=memory_repo,
        qdrant=qdrant_client,
        redis_client=RedisRateLimitStub(),
        settings=settings,
        registry_service=resolved_registry,
        workspaces_service=resolved_workspaces,
        producer=producer or RecordingProducer(),
    )
    retrieval = RetrievalCoordinator(
        repository=memory_repo,
        qdrant=qdrant_client,
        neo4j=resolved_neo4j,
        settings=settings,
        registry_service=resolved_registry,
    )
    return MemoryService(
        repository=memory_repo,
        write_gate=write_gate,
        retrieval_coordinator=retrieval,
        neo4j=resolved_neo4j,
        qdrant=qdrant_client,
        settings=settings,
        producer=producer or RecordingProducer(),
        workspaces_service=resolved_workspaces,
        registry_service=resolved_registry,
    )


@pytest.mark.asyncio
async def test_memory_service_enforces_scope_on_get_delete_and_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    install_qdrant_models_stub(monkeypatch)
    repo = MemoryRepoStub()
    entry = build_memory_entry(workspace_id=workspace_id, agent_fqn="finance:writer")
    repo.memory_entries[entry.id] = entry
    service = _build_service(repo=repo)

    fetched = await service.get_memory_entry_for_requester(entry.id, workspace_id, "finance:writer")
    assert fetched.id == entry.id

    with pytest.raises(ScopeIsolationError):
        await service.get_memory_entry_for_requester(entry.id, workspace_id, "finance:other")

    await service.delete_memory_entry(entry.id, workspace_id, "finance:writer")
    assert repo.memory_entries[entry.id].deleted_at is not None

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fake_embedding)
    repo.memory_entries[entry.id].deleted_at = None
    transferred = await service.transfer_memory_scope(
        CrossScopeTransferRequest(
            memory_entry_id=entry.id,
            target_scope=MemoryScope.per_workspace,
            target_namespace="finance",
        ),
        "finance:writer",
        workspace_id,
    )
    assert transferred.memory_entry_id != entry.id


@pytest.mark.asyncio
async def test_memory_service_handles_retrieval_conflicts_and_context_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    repo = MemoryRepoStub()
    entry = build_memory_entry(workspace_id=workspace_id, scope=MemoryScope.per_workspace)
    repo.memory_entries[entry.id] = entry
    conflict = build_conflict(
        workspace_id=workspace_id,
        memory_entry_id_a=entry.id,
        memory_entry_id_b=entry.id,
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
    service = _build_service(repo=repo, qdrant=qdrant)

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("platform.memory.retrieval_coordinator.request_embedding", _fake_embedding)

    response = await service.retrieve(
        RetrievalQuery(query_text="ACME", top_k=5, include_contradictions=True),
        "finance:writer",
        workspace_id,
    )
    degraded = await service.retrieve_for_context(
        query_text="ACME",
        agent_fqn="finance:writer",
        workspace_id=workspace_id,
        goal_id=None,
        top_k=5,
    )

    assert response.results[0].contradiction_flag is True
    assert degraded


@pytest.mark.asyncio
async def test_memory_service_manages_conflicts_trajectories_and_patterns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    install_qdrant_models_stub(monkeypatch)
    repo = MemoryRepoStub()
    conflict = build_conflict(workspace_id=workspace_id)
    pattern = build_pattern_asset(workspace_id=workspace_id)
    repo.conflicts[conflict.id] = conflict
    repo.patterns[pattern.id] = pattern
    service = _build_service(repo=repo, producer=RecordingProducer())

    record = await service.record_trajectory(
        TrajectoryRecordCreate(
            execution_id=uuid4(),
            agent_fqn="finance:writer",
            actions=[],
            tool_invocations=[],
            reasoning_snapshots=[],
            verdicts=[],
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        ),
        workspace_id,
    )
    listed_conflicts, _ = await service.list_conflicts(workspace_id, None, 1, 20)
    resolved = await service.resolve_conflict(
        conflict.id,
        ConflictResolution(action="resolve", resolution_notes="confirmed"),
        str(uuid4()),
        workspace_id,
    )

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fake_embedding)

    nominated = await service.nominate_pattern(
        PatternNomination(
            trajectory_record_id=record.id,
            content=pattern.content,
            description=pattern.description,
            tags=pattern.tags,
        ),
        "finance:writer",
        workspace_id,
    )
    reviewed = await service.review_pattern(
        pattern.id,
        PatternReview(approved=True),
        str(uuid4()),
        workspace_id,
    )
    listed_patterns, _ = await service.list_patterns(workspace_id, None, 1, 20)

    assert record.workspace_id == workspace_id
    assert listed_conflicts[0].id == conflict.id
    assert resolved.status.value == "resolved"
    assert nominated.status is PatternStatus.pending
    assert reviewed.status is PatternStatus.approved
    assert listed_patterns


@pytest.mark.asyncio
async def test_memory_service_graph_operations_and_provenance() -> None:
    workspace_id = uuid4()
    repo = MemoryRepoStub()
    neo4j = Neo4jStub(
        traverse_results=[
            Neo4jPathStub(
                nodes=[{"id": "n1"}, {"id": "n2"}],
                relationships=[{"id": "e1"}],
            )
        ]
    )
    service = _build_service(repo=repo, neo4j=neo4j)

    created_node = await service.create_knowledge_node(
        KnowledgeNodeCreate(
            node_type="Organization",
            external_name="ACME Corp",
            attributes={"industry": "manufacturing"},
        ),
        "finance:writer",
        workspace_id,
    )
    source_node = next(iter(repo.nodes.values()))
    target_node = build_knowledge_node(workspace_id=workspace_id, external_name="Invoice Rule")
    repo.nodes[target_node.id] = target_node
    created_edge = await service.create_knowledge_edge(
        KnowledgeEdgeCreate(
            source_node_id=source_node.id,
            target_node_id=target_node.id,
            relationship_type="defines",
            metadata={"source": "playbook"},
        ),
        workspace_id,
    )
    traversed = await service.traverse_graph(
        GraphTraversalQuery(start_node_id=source_node.id, max_hops=2),
        workspace_id,
    )
    provenance = await service.get_provenance_chain(target_node.id, workspace_id)

    assert created_node.external_name == "ACME Corp"
    assert created_edge.metadata["source"] == "playbook"
    assert traversed.paths
    assert provenance.paths


@pytest.mark.asyncio
async def test_memory_service_graph_degrades_gracefully() -> None:
    workspace_id = uuid4()
    repo = MemoryRepoStub()
    node = build_knowledge_node(workspace_id=workspace_id)
    repo.nodes[node.id] = node
    service = _build_service(repo=repo, neo4j=Neo4jStub(fail_traverse=RuntimeError("down")))

    degraded = await service.traverse_graph(
        GraphTraversalQuery(start_node_id=node.id, max_hops=2),
        workspace_id,
    )

    assert degraded.partial_sources == ["graph"]

    failing_service = _build_service(
        repo=repo,
        neo4j=Neo4jStub(fail_create_node=RuntimeError("down")),
    )
    with pytest.raises(GraphUnavailableError):
        await failing_service.create_knowledge_node(
            KnowledgeNodeCreate(node_type="Organization", external_name="ACME", attributes={}),
            "finance:writer",
            workspace_id,
        )
