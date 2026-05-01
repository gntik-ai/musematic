from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    SoftDeleteMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from uuid import UUID

from sqlalchemy import Computed, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class MemoryScope(StrEnum):
    per_agent = "per_agent"
    per_workspace = "per_workspace"
    shared_orchestrator = "shared_orchestrator"


class RetentionPolicy(StrEnum):
    permanent = "permanent"
    time_limited = "time_limited"
    session_only = "session_only"


class EmbeddingStatus(StrEnum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class ConflictStatus(StrEnum):
    open = "open"
    dismissed = "dismissed"
    resolved = "resolved"


class EmbeddingJobStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class PatternStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class MemoryEntry(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "memory_entries"
    __table_args__ = (
        Index("ix_memory_entries_workspace_scope", "workspace_id", "scope"),
        Index("ix_memory_entries_agent_scope", "agent_fqn", "scope"),
        Index("ix_memory_entries_content_tsv", "content_tsv", postgresql_using="gin"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_fqn: Mapped[str] = mapped_column(String(length=255), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(length=255), nullable=False)
    scope: Mapped[MemoryScope] = mapped_column(
        SAEnum(MemoryScope, name="memory_scope"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    content_tsv: Mapped[object] = mapped_column(
        TSVECTOR(),
        Computed("to_tsvector('english', coalesce(content, ''))", persisted=True),
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(String(length=64), nullable=False)
    source_authority: Mapped[float] = mapped_column(Float(), nullable=False, default=1.0)
    retention_policy: Mapped[RetentionPolicy] = mapped_column(
        SAEnum(RetentionPolicy, name="memory_retention_policy"),
        nullable=False,
        default=RetentionPolicy.permanent,
    )
    ttl_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        SAEnum(EmbeddingStatus, name="memory_embedding_status"),
        nullable=False,
        default=EmbeddingStatus.pending,
    )
    qdrant_point_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    provenance_consolidated_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memory_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )


class EvidenceConflict(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "evidence_conflicts"
    __table_args__ = (
        Index("ix_evidence_conflicts_pair", "memory_entry_id_a", "memory_entry_id_b", unique=True),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    memory_entry_id_a: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memory_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_entry_id_b: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memory_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    conflict_description: Mapped[str] = mapped_column(Text(), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float(), nullable=False)
    status: Mapped[ConflictStatus] = mapped_column(
        SAEnum(ConflictStatus, name="memory_conflict_status"),
        nullable=False,
        default=ConflictStatus.open,
        index=True,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)


class EmbeddingJob(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "embedding_jobs"

    memory_entry_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memory_entries.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[EmbeddingJobStatus] = mapped_column(
        SAEnum(EmbeddingJobStatus, name="memory_embedding_job_status"),
        nullable=False,
        default=EmbeddingJobStatus.pending,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrajectoryRecord(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "trajectory_records"
    __table_args__ = (Index("ix_trajectory_records_workspace_agent", "workspace_id", "agent_fqn"),)

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    agent_fqn: Mapped[str] = mapped_column(String(length=255), nullable=False, index=True)
    actions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    tool_invocations: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    reasoning_snapshots: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    verdicts: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PatternAsset(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "pattern_assets"

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trajectory_record_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trajectory_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    nominated_by: Mapped[str] = mapped_column(String(length=255), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    status: Mapped[PatternStatus] = mapped_column(
        SAEnum(PatternStatus, name="memory_pattern_status"),
        nullable=False,
        default=PatternStatus.pending,
        index=True,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    memory_entry_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memory_entries.id", ondelete="SET NULL"),
        nullable=True,
    )


class KnowledgeNode(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        Index("ix_knowledge_nodes_workspace_type", "workspace_id", "node_type"),
        Index(
            "uq_knowledge_nodes_workspace_neo4j_element_id",
            "workspace_id",
            "neo4j_element_id",
            unique=True,
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    neo4j_element_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    node_type: Mapped[str] = mapped_column(String(length=100), nullable=False)
    external_name: Mapped[str] = mapped_column(String(length=500), nullable=False)
    attributes: Mapped[dict[str, object]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_by_fqn: Mapped[str] = mapped_column(String(length=255), nullable=False)


class KnowledgeEdge(Base, TenantScopedMixin, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        Index("ix_knowledge_edges_source_target", "source_node_id", "target_node_id"),
        Index(
            "uq_knowledge_edges_workspace_neo4j_element_id",
            "workspace_id",
            "neo4j_element_id",
            unique=True,
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    neo4j_element_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    source_node_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(String(length=100), nullable=False)
    edge_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
