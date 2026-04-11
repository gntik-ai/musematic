from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from platform.common.clients.redis import RateLimitResult
from platform.common.config import PlatformSettings
from platform.memory.models import (
    ConflictStatus,
    EmbeddingJob,
    EmbeddingJobStatus,
    EmbeddingStatus,
    EvidenceConflict,
    KnowledgeEdge,
    KnowledgeNode,
    MemoryEntry,
    MemoryScope,
    PatternAsset,
    PatternStatus,
    RetentionPolicy,
    TrajectoryRecord,
)
from platform.workspaces.models import WorkspaceRole
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from tests.registry_support import SessionStub


def build_settings(**overrides: Any) -> PlatformSettings:
    return PlatformSettings(**overrides)


def build_memory_entry(
    *,
    entry_id: UUID | None = None,
    workspace_id: UUID | None = None,
    agent_fqn: str = "finance:writer",
    namespace: str = "finance",
    scope: MemoryScope = MemoryScope.per_agent,
    content: str = "ACME prefers NET-30 terms.",
    source_authority: float = 0.8,
    retention_policy: RetentionPolicy = RetentionPolicy.permanent,
    ttl_expires_at: datetime | None = None,
    execution_id: UUID | None = None,
    embedding_status: EmbeddingStatus = EmbeddingStatus.pending,
    qdrant_point_id: UUID | None = None,
    tags: list[str] | None = None,
) -> MemoryEntry:
    now = datetime.now(UTC)
    entry = MemoryEntry(
        id=entry_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        agent_fqn=agent_fqn,
        namespace=namespace,
        scope=scope,
        content=content,
        content_hash="a" * 64,
        source_authority=source_authority,
        retention_policy=retention_policy,
        ttl_expires_at=ttl_expires_at,
        execution_id=execution_id,
        embedding_status=embedding_status,
        qdrant_point_id=qdrant_point_id,
        tags=tags or ["customer"],
    )
    entry.created_at = now
    entry.updated_at = now
    entry.deleted_at = None
    return entry


def build_conflict(
    *,
    conflict_id: UUID | None = None,
    workspace_id: UUID | None = None,
    memory_entry_id_a: UUID | None = None,
    memory_entry_id_b: UUID | None = None,
    status: ConflictStatus = ConflictStatus.open,
) -> EvidenceConflict:
    now = datetime.now(UTC)
    conflict = EvidenceConflict(
        id=conflict_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        memory_entry_id_a=memory_entry_id_a or uuid4(),
        memory_entry_id_b=memory_entry_id_b or uuid4(),
        conflict_description="conflict",
        similarity_score=0.95,
        status=status,
    )
    conflict.created_at = now
    conflict.updated_at = now
    return conflict


def build_embedding_job(
    *,
    job_id: UUID | None = None,
    memory_entry_id: UUID | None = None,
    status: EmbeddingJobStatus = EmbeddingJobStatus.pending,
) -> EmbeddingJob:
    now = datetime.now(UTC)
    job = EmbeddingJob(
        id=job_id or uuid4(),
        memory_entry_id=memory_entry_id or uuid4(),
        status=status,
        retry_count=0,
    )
    job.created_at = now
    job.updated_at = now
    return job


def build_trajectory_record(
    *,
    trajectory_id: UUID | None = None,
    workspace_id: UUID | None = None,
    execution_id: UUID | None = None,
    agent_fqn: str = "finance:writer",
) -> TrajectoryRecord:
    now = datetime.now(UTC)
    record = TrajectoryRecord(
        id=trajectory_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        execution_id=execution_id or uuid4(),
        agent_fqn=agent_fqn,
        actions=[],
        tool_invocations=[],
        reasoning_snapshots=[],
        verdicts=[],
        started_at=now,
        completed_at=now,
    )
    record.created_at = now
    record.updated_at = now
    return record


def build_pattern_asset(
    *,
    pattern_id: UUID | None = None,
    workspace_id: UUID | None = None,
    nominated_by: str = "finance:writer",
    status: PatternStatus = PatternStatus.pending,
) -> PatternAsset:
    now = datetime.now(UTC)
    pattern = PatternAsset(
        id=pattern_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        trajectory_record_id=None,
        nominated_by=nominated_by,
        content="Always confirm tax IDs before payout.",
        description="A reusable finance rule",
        tags=["finance"],
        status=status,
    )
    pattern.created_at = now
    pattern.updated_at = now
    return pattern


def build_knowledge_node(
    *,
    node_id: UUID | None = None,
    workspace_id: UUID | None = None,
    external_name: str = "ACME Corp",
    created_by_fqn: str = "finance:writer",
) -> KnowledgeNode:
    now = datetime.now(UTC)
    node = KnowledgeNode(
        id=node_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        neo4j_element_id="neo4j-node",
        node_type="Organization",
        external_name=external_name,
        attributes={"kind": "company"},
        created_by_fqn=created_by_fqn,
    )
    node.created_at = now
    node.updated_at = now
    return node


def build_knowledge_edge(
    *,
    edge_id: UUID | None = None,
    workspace_id: UUID | None = None,
    source_node_id: UUID | None = None,
    target_node_id: UUID | None = None,
) -> KnowledgeEdge:
    now = datetime.now(UTC)
    edge = KnowledgeEdge(
        id=edge_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        neo4j_element_id="neo4j-edge",
        source_node_id=source_node_id or uuid4(),
        target_node_id=target_node_id or uuid4(),
        relationship_type="used",
        edge_metadata={"source": "memory"},
    )
    edge.created_at = now
    edge.updated_at = now
    return edge


def install_qdrant_models_stub(monkeypatch: Any) -> None:
    class MatchValue:
        def __init__(self, *, value: Any) -> None:
            self.value = value

    class FieldCondition:
        def __init__(self, *, key: str, match: Any) -> None:
            self.key = key
            self.match = match

    class Filter:
        def __init__(
            self,
            *,
            must: list[Any] | None = None,
            should: list[Any] | None = None,
            must_not: list[Any] | None = None,
        ) -> None:
            self.must = must or []
            self.should = should or []
            self.must_not = must_not or []

    class VectorParams:
        def __init__(self, *, size: int, distance: Any) -> None:
            self.size = size
            self.distance = distance

    class HnswConfigDiff:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    models_module = SimpleNamespace(
        MatchValue=MatchValue,
        FieldCondition=FieldCondition,
        Filter=Filter,
        VectorParams=VectorParams,
        HnswConfigDiff=HnswConfigDiff,
        PayloadSchemaType=SimpleNamespace(KEYWORD="keyword"),
        Distance=SimpleNamespace(COSINE="cosine"),
    )
    monkeypatch.setitem(__import__("sys").modules, "qdrant_client.models", models_module)
    monkeypatch.setitem(
        __import__("sys").modules,
        "qdrant_client",
        SimpleNamespace(models=models_module),
    )


class MemoryRepoStub:
    def __init__(self) -> None:
        self.session = SessionStub()
        self.memory_entries: dict[UUID, MemoryEntry] = {}
        self.conflicts: dict[UUID, EvidenceConflict] = {}
        self.embedding_jobs: dict[UUID, EmbeddingJob] = {}
        self.trajectories: dict[UUID, TrajectoryRecord] = {}
        self.patterns: dict[UUID, PatternAsset] = {}
        self.nodes: dict[UUID, KnowledgeNode] = {}
        self.edges: dict[UUID, KnowledgeEdge] = {}
        self.keyword_rows: list[dict[str, Any]] = []

    async def create_memory_entry(self, **fields: Any) -> MemoryEntry:
        entry = build_memory_entry(
            workspace_id=fields["workspace_id"],
            agent_fqn=fields["agent_fqn"],
            namespace=fields["namespace"],
            scope=fields["scope"],
            content=fields["content"],
            source_authority=fields["source_authority"],
            retention_policy=fields["retention_policy"],
            ttl_expires_at=fields["ttl_expires_at"],
            execution_id=fields["execution_id"],
            tags=list(fields["tags"]),
        )
        self.memory_entries[entry.id] = entry
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_memory_entry(self, entry_id: UUID, workspace_id: UUID) -> MemoryEntry | None:
        entry = self.memory_entries.get(entry_id)
        if entry is None or entry.workspace_id != workspace_id or entry.deleted_at is not None:
            return None
        return entry

    async def get_memory_entry_any(self, entry_id: UUID) -> MemoryEntry | None:
        entry = self.memory_entries.get(entry_id)
        if entry is None or entry.deleted_at is not None:
            return None
        return entry

    async def list_memory_entries(
        self,
        *,
        workspace_id: UUID,
        agent_fqn: str,
        is_orchestrator: bool,
        scope: MemoryScope | None,
        agent_fqn_filter: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[MemoryEntry], int]:
        del page, page_size
        visible: list[MemoryEntry] = []
        for entry in self.memory_entries.values():
            if entry.workspace_id != workspace_id or entry.deleted_at is not None:
                continue
            if scope is not None and entry.scope is not scope:
                continue
            if agent_fqn_filter is not None and entry.agent_fqn != agent_fqn_filter:
                continue
            if entry.scope is MemoryScope.per_workspace:
                visible.append(entry)
                continue
            if entry.scope is MemoryScope.per_agent and entry.agent_fqn == agent_fqn:
                visible.append(entry)
                continue
            if entry.scope is MemoryScope.shared_orchestrator and is_orchestrator:
                visible.append(entry)
        ordered = sorted(visible, key=lambda item: (item.created_at, item.id), reverse=True)
        return ordered, len(ordered)

    async def soft_delete_memory_entry(self, entry: MemoryEntry) -> None:
        entry.deleted_at = datetime.now(UTC)
        await self.session.flush()

    async def update_memory_entry_embedding(
        self,
        entry_id: UUID,
        *,
        status: EmbeddingStatus,
        qdrant_point_id: UUID | None = None,
    ) -> MemoryEntry | None:
        entry = await self.get_memory_entry_any(entry_id)
        if entry is None:
            return None
        entry.embedding_status = status
        entry.qdrant_point_id = qdrant_point_id
        await self.session.flush()
        return entry

    async def find_similar_by_scope(self, **kwargs: Any) -> list[dict[str, Any]]:
        if self.keyword_rows:
            return list(self.keyword_rows)
        query_text = str(kwargs["query_text"]).lower()
        workspace_id = kwargs["workspace_id"]
        agent_fqn = kwargs["agent_fqn"]
        is_orchestrator = bool(kwargs["is_orchestrator"])
        scope_filter = kwargs["scope_filter"]
        matches: list[dict[str, Any]] = []
        for entry in self.memory_entries.values():
            if entry.workspace_id != workspace_id or entry.deleted_at is not None:
                continue
            if scope_filter is not None and entry.scope is not scope_filter:
                continue
            visible = entry.scope is MemoryScope.per_workspace
            visible = visible or (
                entry.scope is MemoryScope.per_agent and entry.agent_fqn == agent_fqn
            )
            visible = visible or (
                entry.scope is MemoryScope.shared_orchestrator and is_orchestrator
            )
            if visible and query_text in entry.content.lower():
                matches.append({"entry": entry, "score": 0.5})
        return matches

    async def get_memory_entries_by_ids(
        self,
        workspace_id: UUID,
        entry_ids: Iterable[UUID],
    ) -> list[MemoryEntry]:
        results: list[MemoryEntry] = []
        for entry_id in entry_ids:
            entry = self.memory_entries.get(entry_id)
            if entry is None or entry.deleted_at is not None:
                continue
            if workspace_id.int != 0 and entry.workspace_id != workspace_id:
                continue
            results.append(entry)
        return results

    async def create_evidence_conflict(self, **fields: Any) -> EvidenceConflict:
        conflict = build_conflict(
            workspace_id=fields["workspace_id"],
            memory_entry_id_a=fields["memory_entry_id_a"],
            memory_entry_id_b=fields["memory_entry_id_b"],
        )
        conflict.conflict_description = fields["conflict_description"]
        conflict.similarity_score = fields["similarity_score"]
        self.conflicts[conflict.id] = conflict
        self.session.add(conflict)
        await self.session.flush()
        return conflict

    async def get_conflict(self, conflict_id: UUID, workspace_id: UUID) -> EvidenceConflict | None:
        conflict = self.conflicts.get(conflict_id)
        if conflict is None or conflict.workspace_id != workspace_id:
            return None
        return conflict

    async def list_conflicts(
        self,
        *,
        workspace_id: UUID,
        status: ConflictStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[EvidenceConflict], int]:
        del page, page_size
        items = [
            conflict
            for conflict in self.conflicts.values()
            if conflict.workspace_id == workspace_id
            and (status is None or conflict.status is status)
        ]
        return items, len(items)

    async def update_conflict_status(
        self,
        conflict: EvidenceConflict,
        **fields: Any,
    ) -> EvidenceConflict:
        conflict.status = fields["status"]
        conflict.reviewed_by = fields["reviewed_by"]
        conflict.reviewed_at = datetime.now(UTC)
        conflict.resolution_notes = fields["resolution_notes"]
        await self.session.flush()
        return conflict

    async def list_open_conflicts_for_entries(
        self,
        workspace_id: UUID,
        entry_ids: Iterable[UUID],
    ) -> list[EvidenceConflict]:
        wanted = set(entry_ids)
        return [
            conflict
            for conflict in self.conflicts.values()
            if conflict.workspace_id == workspace_id
            and conflict.status is ConflictStatus.open
            and (
                conflict.memory_entry_id_a in wanted or conflict.memory_entry_id_b in wanted
            )
        ]

    async def create_embedding_job(self, memory_entry_id: UUID) -> EmbeddingJob:
        job = build_embedding_job(memory_entry_id=memory_entry_id)
        self.embedding_jobs[job.id] = job
        await self.session.flush()
        return job

    async def get_embedding_job(self, memory_entry_id: UUID) -> EmbeddingJob | None:
        for job in self.embedding_jobs.values():
            if job.memory_entry_id == memory_entry_id:
                return job
        return None

    async def get_pending_embedding_jobs(self, limit: int = 50) -> list[EmbeddingJob]:
        items = [
            job
            for job in self.embedding_jobs.values()
            if job.status is EmbeddingJobStatus.pending
        ]
        return items[:limit]

    async def update_embedding_job_status(self, job: EmbeddingJob, **fields: Any) -> EmbeddingJob:
        job.status = fields["status"]
        job.retry_count = fields.get("retry_count", job.retry_count)
        job.error_message = fields.get("error_message")
        if fields.get("touch_last_attempt", True):
            job.last_attempt_at = datetime.now(UTC)
        if job.status is EmbeddingJobStatus.completed:
            job.completed_at = datetime.now(UTC)
        await self.session.flush()
        return job

    async def create_trajectory_record(self, **fields: Any) -> TrajectoryRecord:
        record = build_trajectory_record(
            workspace_id=fields["workspace_id"],
            execution_id=fields["execution_id"],
            agent_fqn=fields["agent_fqn"],
        )
        record.actions = list(fields["actions"])
        record.tool_invocations = list(fields["tool_invocations"])
        record.reasoning_snapshots = list(fields["reasoning_snapshots"])
        record.verdicts = list(fields["verdicts"])
        record.started_at = fields["started_at"]
        record.completed_at = fields["completed_at"]
        self.trajectories[record.id] = record
        await self.session.flush()
        return record

    async def get_trajectory_record(
        self,
        trajectory_id: UUID,
        workspace_id: UUID,
    ) -> TrajectoryRecord | None:
        record = self.trajectories.get(trajectory_id)
        if record is None or record.workspace_id != workspace_id:
            return None
        return record

    async def create_pattern_asset(self, **fields: Any) -> PatternAsset:
        pattern = build_pattern_asset(
            workspace_id=fields["workspace_id"],
            nominated_by=fields["nominated_by"],
        )
        pattern.trajectory_record_id = fields["trajectory_record_id"]
        pattern.content = fields["content"]
        pattern.description = fields["description"]
        pattern.tags = list(fields["tags"])
        self.patterns[pattern.id] = pattern
        await self.session.flush()
        return pattern

    async def get_pattern_asset(self, pattern_id: UUID, workspace_id: UUID) -> PatternAsset | None:
        pattern = self.patterns.get(pattern_id)
        if pattern is None or pattern.workspace_id != workspace_id:
            return None
        return pattern

    async def list_pattern_assets(
        self,
        *,
        workspace_id: UUID,
        status: PatternStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[PatternAsset], int]:
        del page, page_size
        items = [
            pattern
            for pattern in self.patterns.values()
            if pattern.workspace_id == workspace_id and (status is None or pattern.status is status)
        ]
        return items, len(items)

    async def update_pattern_status(self, pattern: PatternAsset, **fields: Any) -> PatternAsset:
        for key, value in fields.items():
            setattr(pattern, key, value)
        await self.session.flush()
        return pattern

    async def create_knowledge_node(self, **fields: Any) -> KnowledgeNode:
        node = build_knowledge_node(
            workspace_id=fields["workspace_id"],
            external_name=fields["external_name"],
            created_by_fqn=fields["created_by_fqn"],
        )
        node.neo4j_element_id = fields["neo4j_element_id"]
        node.node_type = fields["node_type"]
        node.attributes = dict(fields["attributes"])
        self.nodes[node.id] = node
        await self.session.flush()
        return node

    async def delete_knowledge_node(self, node: KnowledgeNode) -> None:
        self.nodes.pop(node.id, None)
        await self.session.flush()

    async def get_knowledge_node(self, node_id: UUID, workspace_id: UUID) -> KnowledgeNode | None:
        node = self.nodes.get(node_id)
        if node is None or node.workspace_id != workspace_id:
            return None
        return node

    async def list_knowledge_nodes(self, workspace_id: UUID) -> list[KnowledgeNode]:
        return [node for node in self.nodes.values() if node.workspace_id == workspace_id]

    async def list_knowledge_nodes_by_query(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        limit: int,
    ) -> list[KnowledgeNode]:
        needle = query_text.lower()
        return [
            node
            for node in self.nodes.values()
            if node.workspace_id == workspace_id and needle in node.external_name.lower()
        ][:limit]

    async def create_knowledge_edge(self, **fields: Any) -> KnowledgeEdge:
        edge = build_knowledge_edge(
            workspace_id=fields["workspace_id"],
            source_node_id=fields["source_node_id"],
            target_node_id=fields["target_node_id"],
        )
        edge.neo4j_element_id = fields["neo4j_element_id"]
        edge.relationship_type = fields["relationship_type"]
        edge.edge_metadata = dict(fields["edge_metadata"])
        self.edges[edge.id] = edge
        await self.session.flush()
        return edge

    async def delete_knowledge_edge(self, edge: KnowledgeEdge) -> None:
        self.edges.pop(edge.id, None)
        await self.session.flush()

    async def get_knowledge_edge(self, edge_id: UUID, workspace_id: UUID) -> KnowledgeEdge | None:
        edge = self.edges.get(edge_id)
        if edge is None or edge.workspace_id != workspace_id:
            return None
        return edge

    async def list_incoming_edges(self, node_id: UUID, workspace_id: UUID) -> list[KnowledgeEdge]:
        return [
            edge
            for edge in self.edges.values()
            if edge.workspace_id == workspace_id and edge.target_node_id == node_id
        ]

    async def get_session_only_expired(self) -> list[MemoryEntry]:
        now = datetime.now(UTC)
        return [
            entry
            for entry in self.memory_entries.values()
            if entry.retention_policy is RetentionPolicy.session_only
            and entry.ttl_expires_at is not None
            and entry.ttl_expires_at < now
            and entry.deleted_at is None
        ]

    async def list_workspace_ids_with_agent_memories(self) -> list[UUID]:
        workspace_ids = {
            entry.workspace_id
            for entry in self.memory_entries.values()
            if entry.scope is MemoryScope.per_agent and entry.deleted_at is None
        }
        return list(workspace_ids)

    async def get_consolidation_candidates(self, workspace_id: UUID) -> list[MemoryEntry]:
        return [
            entry
            for entry in self.memory_entries.values()
            if entry.workspace_id == workspace_id
            and entry.scope is MemoryScope.per_agent
            and entry.deleted_at is None
        ]

    async def bulk_link_consolidated_entries(
        self,
        *,
        source_ids: Iterable[UUID],
        consolidated_id: UUID,
    ) -> None:
        for entry_id in source_ids:
            entry = self.memory_entries.get(entry_id)
            if entry is not None:
                entry.provenance_consolidated_by = consolidated_id
        await self.session.flush()


@dataclass
class QdrantStub:
    search_results: list[dict[str, Any]] = field(default_factory=list)
    upserts: list[tuple[str, list[dict[str, Any]]]] = field(default_factory=list)
    deletes: list[tuple[str, list[str | int]]] = field(default_factory=list)
    collection_calls: list[dict[str, Any]] = field(default_factory=list)
    payload_indexes: list[dict[str, Any]] = field(default_factory=list)
    fail_upsert: Exception | None = None
    fail_search: Exception | None = None

    async def search_vectors(
        self,
        collection: str,
        query_vector: list[float],
        limit: int,
        query_filter: Any | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        del collection, query_vector, limit, query_filter
        kwargs.pop("filter", None)
        if self.fail_search is not None:
            raise self.fail_search
        return list(self.search_results)

    async def upsert_vectors(self, collection: str, points: list[dict[str, Any]]) -> None:
        if self.fail_upsert is not None:
            raise self.fail_upsert
        self.upserts.append((collection, points))

    async def delete_points(self, collection: str, point_ids: list[str | int]) -> None:
        self.deletes.append((collection, point_ids))

    async def create_collection_if_not_exists(self, **kwargs: Any) -> bool:
        self.collection_calls.append(kwargs)
        return True

    async def create_payload_index(self, **kwargs: Any) -> None:
        self.payload_indexes.append(kwargs)


@dataclass
class Neo4jPathStub:
    nodes: list[dict[str, Any]]
    relationships: list[dict[str, Any]]


@dataclass
class Neo4jStub:
    mode: str = "neo4j"
    created_nodes: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    created_relationships: list[tuple[str, str, str, dict[str, Any]]] = field(default_factory=list)
    traversed: list[tuple[str, list[str], int, str]] = field(default_factory=list)
    cypher_calls: list[str] = field(default_factory=list)
    traverse_results: list[Any] = field(default_factory=list)
    fail_create_node: Exception | None = None
    fail_create_relationship: Exception | None = None
    fail_traverse: Exception | None = None

    async def create_node(self, label: str, properties: dict[str, Any]) -> str:
        if self.fail_create_node is not None:
            raise self.fail_create_node
        self.created_nodes.append((label, properties))
        return "neo4j-node-id"

    async def create_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: dict[str, Any],
    ) -> None:
        if self.fail_create_relationship is not None:
            raise self.fail_create_relationship
        self.created_relationships.append((from_id, to_id, rel_type, properties))

    async def traverse_path(
        self,
        start_id: str,
        rel_types: list[str],
        max_hops: int,
        workspace_id: str,
    ) -> list[Any]:
        self.traversed.append((start_id, rel_types, max_hops, workspace_id))
        if self.fail_traverse is not None:
            raise self.fail_traverse
        return list(self.traverse_results)

    async def run_cypher(self, statement: str) -> None:
        self.cypher_calls.append(statement)


@dataclass
class RedisRateLimitStub:
    results: list[RateLimitResult] = field(default_factory=list)
    calls: list[tuple[str, str, int, int]] = field(default_factory=list)

    async def check_rate_limit(
        self,
        resource: str,
        key: str,
        limit: int,
        window_ms: int,
    ) -> RateLimitResult:
        self.calls.append((resource, key, limit, window_ms))
        if self.results:
            return self.results.pop(0)
        return RateLimitResult(allowed=True, remaining=max(limit - 1, 0), retry_after_ms=0)


@dataclass
class NamespaceRecordStub:
    name: str


@dataclass
class ProfileRecordStub:
    namespace: NamespaceRecordStub
    role_types: list[str] = field(default_factory=lambda: ["executor"])


class RegistryServiceStub:
    def __init__(
        self,
        *,
        namespace_name: str = "finance",
        profile_namespace: str = "finance",
        role_types: list[str] | None = None,
    ) -> None:
        self.namespace = NamespaceRecordStub(name=namespace_name)
        self.profile = ProfileRecordStub(
            namespace=NamespaceRecordStub(name=profile_namespace),
            role_types=role_types or ["executor"],
        )
        self.repo = SimpleNamespace(get_namespace_by_name=self._get_namespace_by_name)

    async def _get_namespace_by_name(
        self,
        workspace_id: UUID,
        name: str,
    ) -> NamespaceRecordStub | None:
        del workspace_id
        return self.namespace if name == self.namespace.name else None

    async def get_by_fqn(self, workspace_id: UUID, agent_fqn: str) -> ProfileRecordStub | None:
        del workspace_id, agent_fqn
        return self.profile


class WorkspacesServiceStub:
    def __init__(self, *, membership_role: WorkspaceRole = WorkspaceRole.owner) -> None:
        self.workspace = SimpleNamespace(id=uuid4())
        self.membership = SimpleNamespace(role=membership_role)
        self.repo = SimpleNamespace(
            get_workspace_by_id_any=self._get_workspace_by_id_any,
            get_membership=self._get_membership,
        )

    async def _get_workspace_by_id_any(self, workspace_id: UUID) -> Any:
        self.workspace.id = workspace_id
        return self.workspace

    async def _get_membership(self, workspace_id: UUID, user_id: UUID) -> Any:
        del workspace_id, user_id
        return self.membership


@dataclass
class RouterMemoryServiceStub:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    async def write_memory(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("write_memory", args, kwargs))
        return {
            "memory_entry_id": str(uuid4()),
            "contradiction_detected": False,
            "conflict_id": None,
            "privacy_applied": False,
            "rate_limit_remaining_min": 59,
            "rate_limit_remaining_hour": 499,
        }

    async def get_memory_entry_for_requester(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("get_memory_entry_for_requester", args, kwargs))
        entry = build_memory_entry()
        return {
            "id": str(entry.id),
            "workspace_id": str(entry.workspace_id),
            "agent_fqn": entry.agent_fqn,
            "namespace": entry.namespace,
            "scope": entry.scope.value,
            "content": entry.content,
            "source_authority": entry.source_authority,
            "retention_policy": entry.retention_policy.value,
            "ttl_expires_at": None,
            "embedding_status": entry.embedding_status.value,
            "tags": entry.tags,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
        }

    async def list_memory_entries(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("list_memory_entries", args, kwargs))
        return [], 0

    async def delete_memory_entry(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("delete_memory_entry", args, kwargs))

    async def transfer_memory_scope(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("transfer_memory_scope", args, kwargs))
        return {
            "memory_entry_id": str(uuid4()),
            "contradiction_detected": False,
            "conflict_id": None,
            "privacy_applied": False,
            "rate_limit_remaining_min": 58,
            "rate_limit_remaining_hour": 498,
        }

    async def retrieve(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("retrieve", args, kwargs))
        return {"results": [], "partial_sources": [], "query_time_ms": 1.0}

    async def list_conflicts(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("list_conflicts", args, kwargs))
        return [], 0

    async def resolve_conflict(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("resolve_conflict", args, kwargs))
        conflict = build_conflict()
        return {
            "id": str(conflict.id),
            "workspace_id": str(conflict.workspace_id),
            "memory_entry_id_a": str(conflict.memory_entry_id_a),
            "memory_entry_id_b": str(conflict.memory_entry_id_b),
            "conflict_description": conflict.conflict_description,
            "similarity_score": conflict.similarity_score,
            "status": conflict.status.value,
            "reviewed_by": None,
            "reviewed_at": None,
            "resolution_notes": None,
            "created_at": conflict.created_at.isoformat(),
        }

    async def record_trajectory(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("record_trajectory", args, kwargs))
        record = build_trajectory_record()
        return {
            "id": str(record.id),
            "workspace_id": str(record.workspace_id),
            "execution_id": str(record.execution_id),
            "agent_fqn": record.agent_fqn,
            "actions": [],
            "tool_invocations": [],
            "reasoning_snapshots": [],
            "verdicts": [],
            "started_at": record.started_at.isoformat(),
            "completed_at": record.completed_at.isoformat(),
            "created_at": record.created_at.isoformat(),
        }

    async def get_trajectory(self, *args: Any, **kwargs: Any) -> Any:
        return await self.record_trajectory(*args, **kwargs)

    async def nominate_pattern(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("nominate_pattern", args, kwargs))
        pattern = build_pattern_asset()
        return {
            "id": str(pattern.id),
            "workspace_id": str(pattern.workspace_id),
            "trajectory_record_id": None,
            "nominated_by": pattern.nominated_by,
            "content": pattern.content,
            "description": pattern.description,
            "tags": pattern.tags,
            "status": pattern.status.value,
            "reviewed_by": None,
            "reviewed_at": None,
            "rejection_reason": None,
            "memory_entry_id": None,
            "created_at": pattern.created_at.isoformat(),
        }

    async def review_pattern(self, *args: Any, **kwargs: Any) -> Any:
        return await self.nominate_pattern(*args, **kwargs)

    async def list_patterns(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("list_patterns", args, kwargs))
        return [], 0

    async def create_knowledge_node(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("create_knowledge_node", args, kwargs))
        node = build_knowledge_node()
        return {
            "id": str(node.id),
            "workspace_id": str(node.workspace_id),
            "node_type": node.node_type,
            "external_name": node.external_name,
            "attributes": node.attributes,
            "created_by_fqn": node.created_by_fqn,
            "created_at": node.created_at.isoformat(),
        }

    async def create_knowledge_edge(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("create_knowledge_edge", args, kwargs))
        edge = build_knowledge_edge()
        return {
            "id": str(edge.id),
            "workspace_id": str(edge.workspace_id),
            "source_node_id": str(edge.source_node_id),
            "target_node_id": str(edge.target_node_id),
            "relationship_type": edge.relationship_type,
            "metadata": edge.edge_metadata,
            "created_at": edge.created_at.isoformat(),
        }

    async def traverse_graph(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(("traverse_graph", args, kwargs))
        return {"paths": [], "node_count": 0, "edge_count": 0, "query_time_ms": 0.1}

    async def get_provenance_chain(self, *args: Any, **kwargs: Any) -> Any:
        return await self.traverse_graph(*args, **kwargs)
