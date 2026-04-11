from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import ValidationError as PlatformValidationError
from platform.memory.consolidation_worker import ConsolidationWorker, SessionMemoryCleaner
from platform.memory.embedding_worker import EmbeddingWorker
from platform.memory.exceptions import (
    EvidenceConflictNotFoundError,
    GraphUnavailableError,
    KnowledgeNodeNotFoundError,
    MemoryEntryNotFoundError,
    PatternNotFoundError,
    ScopeIsolationError,
    TrajectoryNotFoundError,
    WriteGateAuthError,
    WriteGateRetentionError,
)
from platform.memory.exceptions import (
    MemoryError as MemoryDomainError,
)
from platform.memory.memory_setup import setup_memory_collections
from platform.memory.models import MemoryScope, RetentionPolicy
from platform.memory.router import _requester_identity, _workspace_id
from platform.memory.schemas import (
    ConflictResolution,
    CrossScopeTransferRequest,
    GraphTraversalQuery,
    KnowledgeEdgeCreate,
    PatternReview,
    RetrievalResult,
)
from platform.memory.write_gate import MemoryWriteGate, request_embedding
from types import SimpleNamespace
from typing import ClassVar
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.integration.memory_flow_support import build_memory_flow_stack
from tests.memory_support import (
    MemoryRepoStub,
    Neo4jStub,
    QdrantStub,
    build_conflict,
    build_embedding_job,
    build_knowledge_node,
    build_memory_entry,
    build_pattern_asset,
    build_settings,
    install_qdrant_models_stub,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class _FakeAsyncClient:
    payloads: ClassVar[list[dict[str, object]]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        tb: object,
    ) -> bool:
        del exc_type, exc, tb
        return False

    async def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        del url, json
        return _FakeResponse(self.payloads.pop(0))


class _FailingDeleteQdrant(QdrantStub):
    async def delete_points(self, collection: str, point_ids: list[str | int]) -> None:
        del collection, point_ids
        raise RuntimeError("delete failed")


class _SetupQdrant:
    def __init__(self) -> None:
        self.connected = False
        self.closed = False
        self.collection_calls: list[dict[str, object]] = []
        self.payload_indexes: list[dict[str, object]] = []

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True

    async def create_collection_if_not_exists(self, **kwargs: object) -> bool:
        self.collection_calls.append(dict(kwargs))
        return True

    async def create_payload_index(self, **kwargs: object) -> None:
        self.payload_indexes.append(dict(kwargs))


class _SetupNeo4j:
    def __init__(self, *, mode: str) -> None:
        self.mode = mode
        self.connected = False
        self.closed = False
        self.cypher_calls: list[str] = []

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True

    async def run_cypher(self, statement: str) -> None:
        self.cypher_calls.append(statement)


@pytest.mark.asyncio
async def test_memory_request_embedding_and_write_gate_helper_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_qdrant_models_stub(monkeypatch)
    _FakeAsyncClient.payloads = [
        {"embedding": [1, 2]},
        {"data": [{"embedding": [3, 4]}]},
        {},
    ]
    monkeypatch.setattr("platform.memory.write_gate.httpx.AsyncClient", _FakeAsyncClient)

    assert await request_embedding(
        api_url="http://emb",
        model="test",
        content="hello",
    ) == [1.0, 2.0]
    assert await request_embedding(
        api_url="http://emb",
        model="test",
        content="hello",
    ) == [3.0, 4.0]
    with pytest.raises(MemoryDomainError):
        await request_embedding(api_url="http://emb", model="test", content="hello")

    workspace_id = uuid4()
    settings = build_settings(
        MEMORY_DIFFERENTIAL_PRIVACY_ENABLED=True,
        MEMORY_DIFFERENTIAL_PRIVACY_EPSILON=0.5,
    )
    registry_repo = SimpleNamespace(
        get_namespace_by_name=lambda workspace_id, name: _awaitable(
            SimpleNamespace(name=name)
        ),
        get_agent_by_fqn=lambda workspace_id, agent_fqn: _awaitable(
            SimpleNamespace(
                namespace=SimpleNamespace(name="finance"),
                role_types=["executor"],
            )
        ),
    )
    workspaces_repo = SimpleNamespace(
        get_workspace_by_id_any=lambda workspace_id: _awaitable(
            SimpleNamespace(id=workspace_id)
        )
    )
    gate = MemoryWriteGate(
        repository=MemoryRepoStub(),
        qdrant=QdrantStub(
            search_results=[
                {
                    "id": str(uuid4()),
                    "score": 0.99,
                    "payload": {"memory_entry_id": str(uuid4())},
                }
            ]
        ),
        redis_client=SimpleNamespace(check_rate_limit=lambda *args: _awaitable(None)),
        settings=settings,
        registry_service=SimpleNamespace(repo=registry_repo),
        workspaces_service=SimpleNamespace(repo=workspaces_repo),
        producer=RecordingProducer(),
    )
    candidate = build_memory_entry(workspace_id=workspace_id, content="same text")
    gate.repository.memory_entries[candidate.id] = candidate
    gate.qdrant.search_results = [
        {
            "id": str(candidate.id),
            "score": 0.99,
            "payload": {"memory_entry_id": str(candidate.id)},
        }
    ]

    await gate._check_authorization(
        "finance:writer",
        "finance",
        MemoryScope.per_agent,
        workspace_id,
    )
    with pytest.raises(WriteGateAuthError):
        await gate._check_authorization(
            "finance:writer",
            "finance",
            MemoryScope.shared_orchestrator,
            workspace_id,
        )
    with pytest.raises(WriteGateRetentionError):
        gate._validate_retention(RetentionPolicy.time_limited, MemoryScope.per_agent, None, None)
    with pytest.raises(WriteGateRetentionError):
        gate._validate_retention(RetentionPolicy.permanent, MemoryScope.per_agent, None, 10)
    assert gate._validate_retention(
        RetentionPolicy.time_limited,
        MemoryScope.per_agent,
        None,
        10,
    ) is not None
    assert await gate._find_contradiction(
        content="same text",
        scope=MemoryScope.per_agent,
        agent_fqn="finance:writer",
        workspace_id=workspace_id,
        embedding=[0.1, 0.2, 0.3],
    ) is None
    monkeypatch.setattr(gate, "_laplace_noise", lambda scale: 0.25)
    transformed, applied = await gate._apply_differential_privacy("Price 10.5", workspace_id)
    assert applied is True
    assert transformed != "Price 10.5"


@pytest.mark.asyncio
async def test_memory_setup_and_embedding_worker_edge_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_qdrant_models_stub(monkeypatch)
    setup_qdrant = _SetupQdrant()
    setup_neo4j = _SetupNeo4j(mode="local")
    monkeypatch.setattr(
        "platform.memory.memory_setup.AsyncQdrantClient.from_settings",
        lambda settings: setup_qdrant,
    )
    monkeypatch.setattr(
        "platform.memory.memory_setup.AsyncNeo4jClient.from_settings",
        lambda settings: setup_neo4j,
    )

    await setup_memory_collections(settings=build_settings())

    assert setup_qdrant.connected is True
    assert setup_qdrant.closed is True
    assert len(setup_qdrant.payload_indexes) == 3
    assert setup_neo4j.connected is True
    assert setup_neo4j.closed is True
    assert setup_neo4j.cypher_calls == []

    repo = MemoryRepoStub()
    missing_job = build_embedding_job()
    repo.embedding_jobs[missing_job.id] = missing_job
    entry = build_memory_entry()
    repo.memory_entries[entry.id] = entry
    failing_job = build_embedding_job(memory_entry_id=entry.id)
    failing_job.retry_count = 2
    repo.embedding_jobs[failing_job.id] = failing_job

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("platform.memory.embedding_worker.request_embedding", _fake_embedding)

    await EmbeddingWorker(
        repository=repo,
        qdrant=QdrantStub(fail_upsert=RuntimeError("qdrant down")),
        settings=build_settings(),
    ).run()

    assert repo.embedding_jobs[missing_job.id].status.value == "failed"
    assert repo.embedding_jobs[failing_job.id].status.value == "failed"


def test_memory_router_helpers_cover_workspace_and_requester_resolution() -> None:
    workspace_id = uuid4()
    request = SimpleNamespace(headers={})

    assert _workspace_id({"workspace_id": str(workspace_id)}, request) == workspace_id
    assert _workspace_id(
        {"roles": [{"workspace_id": str(workspace_id)}]},
        request,
    ) == workspace_id
    with pytest.raises(PlatformValidationError):
        _workspace_id({"roles": [{}]}, request)

    assert _requester_identity({}, SimpleNamespace(headers={"X-Agent-FQN": "finance:writer"})) == (
        "finance:writer"
    )
    assert _requester_identity({"agent_fqn": "finance:writer"}, request) == "finance:writer"
    assert _requester_identity({"sub": "user-1"}, request) == "user-1"


@pytest.mark.asyncio
async def test_memory_service_error_paths_and_helper_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = build_memory_flow_stack()
    workspace_id = uuid4()
    entry = build_memory_entry(workspace_id=workspace_id, agent_fqn="finance:writer")
    stack.repo.memory_entries[entry.id] = entry
    conflict = build_conflict(workspace_id=workspace_id)
    stack.repo.conflicts[conflict.id] = conflict
    pattern = build_pattern_asset(workspace_id=workspace_id)
    stack.repo.patterns[pattern.id] = pattern
    node = build_knowledge_node(workspace_id=workspace_id)
    stack.repo.nodes[node.id] = node

    with pytest.raises(MemoryEntryNotFoundError):
        await stack.service.get_memory_entry(uuid4(), workspace_id)
    with pytest.raises(MemoryEntryNotFoundError):
        await stack.service.delete_memory_entry(uuid4(), workspace_id, "finance:writer")
    with pytest.raises(ScopeIsolationError):
        await stack.service.delete_memory_entry(entry.id, workspace_id, "not-a-uuid")
    with pytest.raises(MemoryEntryNotFoundError):
        await stack.service.transfer_memory_scope(
            CrossScopeTransferRequest(
                memory_entry_id=None,
                target_scope=MemoryScope.per_workspace,
                target_namespace="finance",
            ),
            "finance:writer",
            workspace_id,
        )
    with pytest.raises(MemoryEntryNotFoundError):
        await stack.service.transfer_memory_scope(
            CrossScopeTransferRequest(
                memory_entry_id=uuid4(),
                target_scope=MemoryScope.per_workspace,
                target_namespace="finance",
            ),
            "finance:writer",
            workspace_id,
        )

    async def _explode(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("degraded")

    monkeypatch.setattr(stack.service, "retrieve", _explode)
    assert (
        await stack.service.retrieve_for_context(
            "acme",
            "finance:writer",
            workspace_id,
            None,
        )
        == []
    )

    async def _fake_context(*args: object, **kwargs: object) -> list[RetrievalResult]:
        del args, kwargs
        return [
            RetrievalResult(
                memory_entry_id=entry.id,
                content=entry.content,
                scope=entry.scope,
                agent_fqn=entry.agent_fqn,
                source_authority=entry.source_authority,
                rrf_score=1.0,
                recency_factor=1.0,
                final_score=0.8,
                sources_contributed=["keyword"],
                contradiction_flag=False,
            )
        ]

    monkeypatch.setattr(stack.service, "retrieve_for_context", _fake_context)
    mapped = await stack.service.search_agent_memory(
        workspace_id=workspace_id,
        agent_fqn="finance:writer",
        query="acme",
        limit=5,
    )
    assert mapped[0]["id"] == entry.id

    with pytest.raises(ScopeIsolationError):
        await stack.service.resolve_conflict(
            conflict.id,
            ConflictResolution(action="dismiss"),
            "not-a-uuid",
            workspace_id,
        )
    with pytest.raises(EvidenceConflictNotFoundError):
        await stack.service.resolve_conflict(
            uuid4(),
            ConflictResolution(action="dismiss"),
            str(uuid4()),
            workspace_id,
        )
    with pytest.raises(TrajectoryNotFoundError):
        await stack.service.get_trajectory(uuid4(), workspace_id)
    with pytest.raises(ScopeIsolationError):
        await stack.service.review_pattern(
            pattern.id,
            PatternReview(approved=False, rejection_reason="no"),
            "not-a-uuid",
            workspace_id,
        )
    with pytest.raises(PatternNotFoundError):
        await stack.service.review_pattern(
            uuid4(),
            PatternReview(approved=False, rejection_reason="no"),
            str(uuid4()),
            workspace_id,
        )
    with pytest.raises(KnowledgeNodeNotFoundError):
        await stack.service.create_knowledge_edge(
            KnowledgeEdgeCreate(
                source_node_id=uuid4(),
                target_node_id=node.id,
                relationship_type="uses",
                metadata={},
            ),
            workspace_id,
        )
    with pytest.raises(KnowledgeNodeNotFoundError):
        await stack.service.create_knowledge_edge(
            KnowledgeEdgeCreate(
                source_node_id=node.id,
                target_node_id=uuid4(),
                relationship_type="uses",
                metadata={},
            ),
            workspace_id,
        )
    with pytest.raises(KnowledgeNodeNotFoundError):
        await stack.service.traverse_graph(GraphTraversalQuery(start_node_id=uuid4()), workspace_id)
    with pytest.raises(KnowledgeNodeNotFoundError):
        await stack.service.get_provenance_chain(uuid4(), workspace_id)

    degraded_stack = build_memory_flow_stack(neo4j=Neo4jStub(fail_traverse=RuntimeError("down")))
    degraded_stack.repo.nodes[node.id] = node
    degraded = await degraded_stack.service.traverse_graph(
        GraphTraversalQuery(start_node_id=node.id, max_hops=2),
        workspace_id,
    )
    assert degraded.partial_sources == ["graph"]
    stack.service.registry_service = None
    assert await stack.service._is_orchestrator("finance:writer", workspace_id) is False
    assert await stack.service._is_workspace_admin("not-a-uuid", workspace_id) is False
    stack.service.workspaces_service = object()
    assert await stack.service._is_workspace_admin(str(uuid4()), workspace_id) is False


@pytest.mark.asyncio
async def test_memory_consolidation_and_exception_edge_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = build_memory_flow_stack()
    workspace_id = uuid4()

    class _SummaryClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> _SummaryClient:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            del exc_type, exc, tb
            return False

        async def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
            del url, json
            return _FakeResponse({"summary": "distilled summary"})

    monkeypatch.setattr(
        "platform.memory.consolidation_worker.httpx.AsyncClient",
        _SummaryClient,
    )
    stack.service.settings.memory.consolidation_llm_enabled = True
    assert await ConsolidationWorker(
        repository=stack.repo,
        write_gate=stack.write_gate,
        settings=stack.service.settings,
        producer=stack.producer,
    )._distill([], workspace_id) == ""

    entry = build_memory_entry(workspace_id=workspace_id, content="alpha memory")
    stack.repo.memory_entries[entry.id] = entry
    summary = await ConsolidationWorker(
        repository=stack.repo,
        write_gate=stack.write_gate,
        settings=stack.service.settings,
        producer=stack.producer,
    )._distill([entry.id], workspace_id)
    assert summary == "distilled summary"

    empty_repo = MemoryRepoStub()
    worker = ConsolidationWorker(
        repository=empty_repo,
        write_gate=stack.write_gate,
        settings=build_settings(),
        producer=RecordingProducer(),
    )
    await worker.run()
    await worker._promote("content", [uuid4()], workspace_id)

    expired = build_memory_entry(
        workspace_id=workspace_id,
        retention_policy=RetentionPolicy.session_only,
        ttl_expires_at=datetime.now(UTC),
        qdrant_point_id=uuid4(),
    )
    stack.repo.memory_entries[expired.id] = expired
    await SessionMemoryCleaner(
        repository=stack.repo,
        qdrant=_FailingDeleteQdrant(),
    ).run()
    assert expired.deleted_at is not None

    conflict_error = EvidenceConflictNotFoundError(uuid4())
    trajectory_error = TrajectoryNotFoundError(uuid4())
    pattern_error = PatternNotFoundError(uuid4())
    node_error = KnowledgeNodeNotFoundError(uuid4())
    edge_error = GraphUnavailableError()
    assert conflict_error.status_code == 404
    assert trajectory_error.status_code == 404
    assert pattern_error.status_code == 404
    assert node_error.status_code == 404
    assert edge_error.status_code == 503


def _awaitable(value: object):
    async def _inner(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return value

    return _inner()
