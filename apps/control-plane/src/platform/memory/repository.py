from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
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
from typing import Any
from uuid import UUID

from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


def build_visibility_clause(
    *,
    agent_fqn: str,
    is_orchestrator: bool,
    scope_filter: MemoryScope | None = None,
    agent_fqn_filter: str | None = None,
) -> Any:
    visible: list[Any] = [
        MemoryEntry.scope == MemoryScope.per_workspace,
    ]
    if agent_fqn:
        visible.append(
            and_(
                MemoryEntry.scope == MemoryScope.per_agent,
                MemoryEntry.agent_fqn == agent_fqn,
            )
        )
    if is_orchestrator:
        visible.append(MemoryEntry.scope == MemoryScope.shared_orchestrator)

    clause = or_(*visible)
    if scope_filter is not None:
        clause = and_(clause, MemoryEntry.scope == scope_filter)
    if agent_fqn_filter is not None:
        clause = and_(clause, MemoryEntry.agent_fqn == agent_fqn_filter)
    return clause


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_memory_entry(self, **fields: Any) -> MemoryEntry:
        entry = MemoryEntry(**fields)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_memory_entry(self, entry_id: UUID, workspace_id: UUID) -> MemoryEntry | None:
        result = await self.session.execute(
            select(MemoryEntry).where(
                MemoryEntry.id == entry_id,
                MemoryEntry.workspace_id == workspace_id,
                MemoryEntry.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_memory_entry_any(self, entry_id: UUID) -> MemoryEntry | None:
        result = await self.session.execute(
            select(MemoryEntry).where(
                MemoryEntry.id == entry_id,
                MemoryEntry.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

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
        visibility = build_visibility_clause(
            agent_fqn=agent_fqn,
            is_orchestrator=is_orchestrator,
            scope_filter=scope,
            agent_fqn_filter=agent_fqn_filter,
        )
        base = select(MemoryEntry).where(
            MemoryEntry.workspace_id == workspace_id,
            MemoryEntry.deleted_at.is_(None),
            visibility,
        )
        total = await self.session.scalar(
            select(func.count())
            .select_from(MemoryEntry)
            .where(
                MemoryEntry.workspace_id == workspace_id,
                MemoryEntry.deleted_at.is_(None),
                visibility,
            )
        )
        result = await self.session.execute(
            base.order_by(MemoryEntry.created_at.desc(), MemoryEntry.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

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

    async def find_similar_by_scope(
        self,
        *,
        query_text: str,
        workspace_id: UUID,
        agent_fqn: str,
        is_orchestrator: bool,
        scope_filter: MemoryScope | None,
        agent_fqn_filter: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        ts_query = func.websearch_to_tsquery("english", query_text)
        rank = func.ts_rank(MemoryEntry.content_tsv, ts_query)
        visibility = build_visibility_clause(
            agent_fqn=agent_fqn,
            is_orchestrator=is_orchestrator,
            scope_filter=scope_filter,
            agent_fqn_filter=agent_fqn_filter,
        )
        result = await self.session.execute(
            select(MemoryEntry, rank.label("rank"))
            .where(
                MemoryEntry.workspace_id == workspace_id,
                MemoryEntry.deleted_at.is_(None),
                visibility,
                MemoryEntry.content_tsv.op("@@")(ts_query),
            )
            .order_by(rank.desc(), MemoryEntry.created_at.desc())
            .limit(limit)
        )
        return [
            {"entry": entry, "score": float(score or 0.0)}
            for entry, score in result.all()
        ]

    async def get_memory_entries_by_ids(
        self,
        workspace_id: UUID,
        entry_ids: Sequence[UUID],
    ) -> list[MemoryEntry]:
        if not entry_ids:
            return []
        result = await self.session.execute(
            select(MemoryEntry).where(
                MemoryEntry.workspace_id == workspace_id,
                MemoryEntry.id.in_(list(entry_ids)),
                MemoryEntry.deleted_at.is_(None),
            )
        )
        entries = list(result.scalars().all())
        entry_map = {entry.id: entry for entry in entries}
        return [entry_map[entry_id] for entry_id in entry_ids if entry_id in entry_map]

    async def create_evidence_conflict(self, **fields: Any) -> EvidenceConflict:
        conflict = EvidenceConflict(**fields)
        self.session.add(conflict)
        await self.session.flush()
        return conflict

    async def get_conflict(self, conflict_id: UUID, workspace_id: UUID) -> EvidenceConflict | None:
        result = await self.session.execute(
            select(EvidenceConflict).where(
                EvidenceConflict.id == conflict_id,
                EvidenceConflict.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_conflicts(
        self,
        *,
        workspace_id: UUID,
        status: ConflictStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[EvidenceConflict], int]:
        filters = [EvidenceConflict.workspace_id == workspace_id]
        if status is not None:
            filters.append(EvidenceConflict.status == status)
        total = await self.session.scalar(
            select(func.count()).select_from(EvidenceConflict).where(*filters)
        )
        result = await self.session.execute(
            select(EvidenceConflict)
            .where(*filters)
            .order_by(EvidenceConflict.created_at.desc(), EvidenceConflict.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_conflict_status(
        self,
        conflict: EvidenceConflict,
        *,
        status: ConflictStatus,
        reviewed_by: str,
        resolution_notes: str | None,
    ) -> EvidenceConflict:
        conflict.status = status
        conflict.reviewed_by = reviewed_by
        conflict.reviewed_at = datetime.now(UTC)
        conflict.resolution_notes = resolution_notes
        await self.session.flush()
        return conflict

    async def list_open_conflicts_for_entries(
        self,
        workspace_id: UUID,
        entry_ids: Sequence[UUID],
    ) -> list[EvidenceConflict]:
        if not entry_ids:
            return []
        result = await self.session.execute(
            select(EvidenceConflict).where(
                EvidenceConflict.workspace_id == workspace_id,
                EvidenceConflict.status == ConflictStatus.open,
                or_(
                    EvidenceConflict.memory_entry_id_a.in_(list(entry_ids)),
                    EvidenceConflict.memory_entry_id_b.in_(list(entry_ids)),
                ),
            )
        )
        return list(result.scalars().all())

    async def create_embedding_job(self, memory_entry_id: UUID) -> EmbeddingJob:
        job = EmbeddingJob(memory_entry_id=memory_entry_id, status=EmbeddingJobStatus.pending)
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_embedding_job(self, memory_entry_id: UUID) -> EmbeddingJob | None:
        result = await self.session.execute(
            select(EmbeddingJob).where(EmbeddingJob.memory_entry_id == memory_entry_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_embedding_jobs(self, limit: int = 50) -> list[EmbeddingJob]:
        result = await self.session.execute(
            select(EmbeddingJob)
            .where(EmbeddingJob.status == EmbeddingJobStatus.pending)
            .order_by(EmbeddingJob.created_at.asc(), EmbeddingJob.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_embedding_job_status(
        self,
        job: EmbeddingJob,
        *,
        status: EmbeddingJobStatus,
        retry_count: int | None = None,
        error_message: str | None = None,
        touch_last_attempt: bool = True,
    ) -> EmbeddingJob:
        job.status = status
        if retry_count is not None:
            job.retry_count = retry_count
        job.error_message = error_message
        if touch_last_attempt:
            job.last_attempt_at = datetime.now(UTC)
        if status is EmbeddingJobStatus.completed:
            job.completed_at = datetime.now(UTC)
        await self.session.flush()
        return job

    async def create_trajectory_record(self, **fields: Any) -> TrajectoryRecord:
        record = TrajectoryRecord(**fields)
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_trajectory_record(
        self,
        trajectory_id: UUID,
        workspace_id: UUID,
    ) -> TrajectoryRecord | None:
        result = await self.session.execute(
            select(TrajectoryRecord).where(
                TrajectoryRecord.id == trajectory_id,
                TrajectoryRecord.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_pattern_asset(self, **fields: Any) -> PatternAsset:
        pattern = PatternAsset(**fields)
        self.session.add(pattern)
        await self.session.flush()
        return pattern

    async def get_pattern_asset(self, pattern_id: UUID, workspace_id: UUID) -> PatternAsset | None:
        result = await self.session.execute(
            select(PatternAsset).where(
                PatternAsset.id == pattern_id,
                PatternAsset.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_pattern_assets(
        self,
        *,
        workspace_id: UUID,
        status: PatternStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[PatternAsset], int]:
        filters = [PatternAsset.workspace_id == workspace_id]
        if status is not None:
            filters.append(PatternAsset.status == status)
        total = await self.session.scalar(
            select(func.count()).select_from(PatternAsset).where(*filters)
        )
        result = await self.session.execute(
            select(PatternAsset)
            .where(*filters)
            .order_by(PatternAsset.created_at.desc(), PatternAsset.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_pattern_status(self, pattern: PatternAsset, **fields: Any) -> PatternAsset:
        for key, value in fields.items():
            setattr(pattern, key, value)
        await self.session.flush()
        return pattern

    async def create_knowledge_node(self, **fields: Any) -> KnowledgeNode:
        node = KnowledgeNode(**fields)
        self.session.add(node)
        await self.session.flush()
        return node

    async def delete_knowledge_node(self, node: KnowledgeNode) -> None:
        await self.session.delete(node)
        await self.session.flush()

    async def get_knowledge_node(self, node_id: UUID, workspace_id: UUID) -> KnowledgeNode | None:
        result = await self.session.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.id == node_id,
                KnowledgeNode.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_knowledge_nodes(
        self,
        workspace_id: UUID,
    ) -> list[KnowledgeNode]:
        result = await self.session.execute(
            select(KnowledgeNode)
            .where(KnowledgeNode.workspace_id == workspace_id)
            .order_by(KnowledgeNode.created_at.asc(), KnowledgeNode.id.asc())
        )
        return list(result.scalars().all())

    async def list_knowledge_nodes_by_query(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        limit: int,
    ) -> list[KnowledgeNode]:
        needle = f"%{query_text.lower()}%"
        result = await self.session.execute(
            select(KnowledgeNode)
            .where(
                KnowledgeNode.workspace_id == workspace_id,
                func.lower(KnowledgeNode.external_name).like(needle),
            )
            .order_by(KnowledgeNode.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_knowledge_edge(self, **fields: Any) -> KnowledgeEdge:
        edge = KnowledgeEdge(**fields)
        self.session.add(edge)
        await self.session.flush()
        return edge

    async def delete_knowledge_edge(self, edge: KnowledgeEdge) -> None:
        await self.session.delete(edge)
        await self.session.flush()

    async def get_knowledge_edge(self, edge_id: UUID, workspace_id: UUID) -> KnowledgeEdge | None:
        result = await self.session.execute(
            select(KnowledgeEdge).where(
                KnowledgeEdge.id == edge_id,
                KnowledgeEdge.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_incoming_edges(self, node_id: UUID, workspace_id: UUID) -> list[KnowledgeEdge]:
        result = await self.session.execute(
            select(KnowledgeEdge)
            .where(
                KnowledgeEdge.target_node_id == node_id,
                KnowledgeEdge.workspace_id == workspace_id,
            )
            .order_by(KnowledgeEdge.created_at.asc(), KnowledgeEdge.id.asc())
        )
        return list(result.scalars().all())

    async def get_session_only_expired(self) -> list[MemoryEntry]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(MemoryEntry).where(
                MemoryEntry.retention_policy == RetentionPolicy.session_only,
                MemoryEntry.ttl_expires_at.is_not(None),
                MemoryEntry.ttl_expires_at < now,
                MemoryEntry.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_workspace_ids_with_agent_memories(self) -> list[UUID]:
        result = await self.session.execute(
            select(distinct(MemoryEntry.workspace_id)).where(
                MemoryEntry.scope == MemoryScope.per_agent,
                MemoryEntry.deleted_at.is_(None),
            )
        )
        return [row[0] for row in result.all()]

    async def get_consolidation_candidates(self, workspace_id: UUID) -> list[MemoryEntry]:
        result = await self.session.execute(
            select(MemoryEntry).where(
                MemoryEntry.workspace_id == workspace_id,
                MemoryEntry.scope == MemoryScope.per_agent,
                MemoryEntry.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def bulk_link_consolidated_entries(
        self,
        *,
        source_ids: Sequence[UUID],
        consolidated_id: UUID,
    ) -> None:
        if not source_ids:
            return
        result = await self.session.execute(
            select(MemoryEntry).where(MemoryEntry.id.in_(list(source_ids)))
        )
        for entry in result.scalars().all():
            entry.provenance_consolidated_by = consolidated_id
        await self.session.flush()
