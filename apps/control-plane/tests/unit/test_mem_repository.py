from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from platform.memory.models import (
    ConflictStatus,
    EmbeddingJobStatus,
    EmbeddingStatus,
    MemoryScope,
    PatternStatus,
    RetentionPolicy,
)
from platform.memory.repository import MemoryRepository, build_visibility_clause
from uuid import uuid4

import pytest

from tests.memory_support import (
    build_conflict,
    build_embedding_job,
    build_knowledge_edge,
    build_knowledge_node,
    build_memory_entry,
    build_pattern_asset,
    build_trajectory_record,
)
from tests.registry_support import SessionStub


@dataclass
class ScalarOneResult:
    one: object | None = None

    def scalar_one_or_none(self) -> object | None:
        return self.one


@dataclass
class ScalarsManyResult:
    many: list[object] = field(default_factory=list)

    def scalars(self):
        return type("ScalarsProxy", (), {"all": lambda self_: list(self.many)})()


@dataclass
class RowsResult:
    rows: list[tuple[object, object]] = field(default_factory=list)

    def all(self) -> list[tuple[object, object]]:
        return list(self.rows)


@pytest.mark.asyncio
async def test_memory_repository_entry_accessors_and_search() -> None:
    workspace_id = uuid4()
    entry = build_memory_entry(workspace_id=workspace_id)
    session = SessionStub(
        execute_results=[
            ScalarOneResult(one=entry),
            ScalarOneResult(one=entry),
            ScalarsManyResult(many=[entry]),
            ScalarOneResult(one=entry),
            RowsResult(rows=[(entry, 0.8)]),
            ScalarsManyResult(many=[entry]),
        ],
        scalar_results=[1],
    )
    repo = MemoryRepository(session)

    created = await repo.create_memory_entry(
        workspace_id=workspace_id,
        agent_fqn="finance:writer",
        namespace="finance",
        scope=MemoryScope.per_agent,
        content="ACME prefers NET-30.",
        content_hash="b" * 64,
        source_authority=0.9,
        retention_policy=RetentionPolicy.permanent,
        ttl_expires_at=None,
        execution_id=None,
        tags=["finance"],
    )
    fetched = await repo.get_memory_entry(entry.id, workspace_id)
    fetched_any = await repo.get_memory_entry_any(entry.id)
    listed, total = await repo.list_memory_entries(
        workspace_id=workspace_id,
        agent_fqn="finance:writer",
        is_orchestrator=False,
        scope=None,
        agent_fqn_filter=None,
        page=1,
        page_size=20,
    )
    updated = await repo.update_memory_entry_embedding(
        entry.id,
        status=EmbeddingStatus.completed,
        qdrant_point_id=entry.id,
    )
    ranked = await repo.find_similar_by_scope(
        query_text="ACME",
        workspace_id=workspace_id,
        agent_fqn="finance:writer",
        is_orchestrator=False,
        scope_filter=None,
        agent_fqn_filter=None,
        limit=10,
    )
    ordered = await repo.get_memory_entries_by_ids(workspace_id, [entry.id])
    await repo.soft_delete_memory_entry(created)

    assert created.agent_fqn == "finance:writer"
    assert fetched == entry
    assert fetched_any == entry
    assert listed == [entry]
    assert total == 1
    assert updated is entry
    assert updated.embedding_status is EmbeddingStatus.completed
    assert ranked[0]["entry"] == entry
    assert ordered == [entry]
    assert created.deleted_at is not None


@pytest.mark.asyncio
async def test_memory_repository_conflicts_and_embedding_jobs() -> None:
    workspace_id = uuid4()
    conflict = build_conflict(workspace_id=workspace_id)
    job = build_embedding_job(memory_entry_id=uuid4())
    session = SessionStub(
        execute_results=[
            ScalarOneResult(one=conflict),
            ScalarsManyResult(many=[conflict]),
            ScalarsManyResult(many=[conflict]),
            ScalarOneResult(one=job),
            ScalarsManyResult(many=[job]),
        ],
        scalar_results=[1],
    )
    repo = MemoryRepository(session)

    created_conflict = await repo.create_evidence_conflict(
        workspace_id=workspace_id,
        memory_entry_id_a=conflict.memory_entry_id_a,
        memory_entry_id_b=conflict.memory_entry_id_b,
        conflict_description="Conflict",
        similarity_score=0.97,
    )
    fetched_conflict = await repo.get_conflict(conflict.id, workspace_id)
    listed_conflicts, total_conflicts = await repo.list_conflicts(
        workspace_id=workspace_id,
        status=None,
        page=1,
        page_size=20,
    )
    updated_conflict = await repo.update_conflict_status(
        conflict,
        status=ConflictStatus.resolved,
        reviewed_by="reviewer",
        resolution_notes="resolved",
    )
    open_conflicts = await repo.list_open_conflicts_for_entries(
        workspace_id,
        [conflict.memory_entry_id_a],
    )
    created_job = await repo.create_embedding_job(job.memory_entry_id)
    fetched_job = await repo.get_embedding_job(job.memory_entry_id)
    pending_jobs = await repo.get_pending_embedding_jobs()
    updated_job = await repo.update_embedding_job_status(
        job,
        status=EmbeddingJobStatus.completed,
        error_message=None,
    )

    assert created_conflict.conflict_description == "Conflict"
    assert fetched_conflict == conflict
    assert listed_conflicts == [conflict]
    assert total_conflicts == 1
    assert updated_conflict.status is ConflictStatus.resolved
    assert open_conflicts == [conflict]
    assert created_job.memory_entry_id == job.memory_entry_id
    assert fetched_job == job
    assert pending_jobs == [job]
    assert updated_job.completed_at is not None


@pytest.mark.asyncio
async def test_memory_repository_trajectory_pattern_and_graph_helpers() -> None:
    workspace_id = uuid4()
    record = build_trajectory_record(workspace_id=workspace_id)
    pattern = build_pattern_asset(workspace_id=workspace_id)
    node = build_knowledge_node(workspace_id=workspace_id)
    edge = build_knowledge_edge(
        workspace_id=workspace_id,
        source_node_id=node.id,
        target_node_id=uuid4(),
    )
    session = SessionStub(
        execute_results=[
            ScalarOneResult(one=record),
            ScalarOneResult(one=pattern),
            ScalarsManyResult(many=[pattern]),
            ScalarOneResult(one=node),
            ScalarsManyResult(many=[node]),
            ScalarsManyResult(many=[node]),
            ScalarOneResult(one=edge),
            ScalarsManyResult(many=[edge]),
        ],
        scalar_results=[1],
    )
    repo = MemoryRepository(session)

    created_record = await repo.create_trajectory_record(
        workspace_id=workspace_id,
        execution_id=record.execution_id,
        agent_fqn=record.agent_fqn,
        actions=[],
        tool_invocations=[],
        reasoning_snapshots=[],
        verdicts=[],
        started_at=record.started_at,
        completed_at=record.completed_at,
    )
    fetched_record = await repo.get_trajectory_record(record.id, workspace_id)
    created_pattern = await repo.create_pattern_asset(
        workspace_id=workspace_id,
        trajectory_record_id=None,
        nominated_by=pattern.nominated_by,
        content=pattern.content,
        description=pattern.description,
        tags=pattern.tags,
    )
    fetched_pattern = await repo.get_pattern_asset(pattern.id, workspace_id)
    listed_patterns, total_patterns = await repo.list_pattern_assets(
        workspace_id=workspace_id,
        status=None,
        page=1,
        page_size=20,
    )
    updated_pattern = await repo.update_pattern_status(pattern, status=PatternStatus.approved)
    created_node = await repo.create_knowledge_node(
        workspace_id=workspace_id,
        neo4j_element_id=node.neo4j_element_id,
        node_type=node.node_type,
        external_name=node.external_name,
        attributes=node.attributes,
        created_by_fqn=node.created_by_fqn,
    )
    fetched_node = await repo.get_knowledge_node(node.id, workspace_id)
    listed_nodes = await repo.list_knowledge_nodes(workspace_id)
    queried_nodes = await repo.list_knowledge_nodes_by_query(
        workspace_id=workspace_id,
        query_text=node.external_name,
        limit=5,
    )
    created_edge = await repo.create_knowledge_edge(
        workspace_id=workspace_id,
        neo4j_element_id=edge.neo4j_element_id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        relationship_type=edge.relationship_type,
        edge_metadata=edge.edge_metadata,
    )
    fetched_edge = await repo.get_knowledge_edge(edge.id, workspace_id)
    incoming_edges = await repo.list_incoming_edges(edge.target_node_id, workspace_id)
    await repo.delete_knowledge_node(created_node)
    await repo.delete_knowledge_edge(created_edge)

    assert created_record.execution_id == record.execution_id
    assert fetched_record == record
    assert created_pattern.content == pattern.content
    assert fetched_pattern == pattern
    assert listed_patterns == [pattern]
    assert total_patterns == 1
    assert updated_pattern.status is PatternStatus.approved
    assert created_node.external_name == node.external_name
    assert fetched_node == node
    assert listed_nodes == [node]
    assert queried_nodes == [node]
    assert created_edge.relationship_type == edge.relationship_type
    assert fetched_edge == edge
    assert incoming_edges == [edge]
    assert session.deleted == [created_node, created_edge]


@pytest.mark.asyncio
async def test_memory_repository_cleanup_helpers_and_visibility_clause() -> None:
    workspace_id = uuid4()
    expired = build_memory_entry(
        workspace_id=workspace_id,
        retention_policy=RetentionPolicy.session_only,
        ttl_expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    active = build_memory_entry(
        workspace_id=workspace_id,
        content="Cluster me",
        scope=MemoryScope.per_agent,
    )
    consolidated = build_memory_entry(
        workspace_id=workspace_id,
        content="Also cluster me",
        scope=MemoryScope.per_agent,
    )
    session = SessionStub(
        execute_results=[
            ScalarsManyResult(many=[expired]),
            RowsResult(rows=[(workspace_id,)]),
            ScalarsManyResult(many=[active, consolidated]),
            ScalarsManyResult(many=[active, consolidated]),
        ]
    )
    repo = MemoryRepository(session)

    expired_entries = await repo.get_session_only_expired()
    workspace_ids = await repo.list_workspace_ids_with_agent_memories()
    candidates = await repo.get_consolidation_candidates(workspace_id)
    await repo.bulk_link_consolidated_entries(
        source_ids=[active.id, consolidated.id],
        consolidated_id=uuid4(),
    )

    assert expired_entries == [expired]
    assert workspace_ids == [workspace_id]
    assert candidates == [active, consolidated]
    assert active.provenance_consolidated_by is not None
    clause = build_visibility_clause(
        agent_fqn="finance:writer",
        is_orchestrator=True,
        scope_filter=MemoryScope.per_agent,
        agent_fqn_filter="finance:writer",
    )
    assert clause is not None
