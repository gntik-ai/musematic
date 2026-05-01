from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    TenantScopedMixin,
    TimestampMixin,
    UUIDMixin,
    WorkspaceScopedMixin,
)
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class DiscoverySessionStatus(StrEnum):
    active = "active"
    converged = "converged"
    halted = "halted"
    iteration_limit_reached = "iteration_limit_reached"


class HypothesisStatus(StrEnum):
    active = "active"
    merged = "merged"
    retired = "retired"


class EmbeddingStatus(StrEnum):
    pending = "pending"
    indexed = "indexed"
    failed = "failed"


class TournamentRoundStatus(StrEnum):
    completed = "completed"
    in_progress = "in_progress"
    failed = "failed"


class GovernanceStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ExperimentExecutionStatus(StrEnum):
    not_started = "not_started"
    running = "running"
    completed = "completed"
    failed = "failed"
    timeout = "timeout"


class GDECycleStatus(StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"


class ClusterClassification(StrEnum):
    normal = "normal"
    over_explored = "over_explored"
    gap = "gap"


class DiscoverySession(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Top-level container for a scientific discovery workflow."""

    __tablename__ = "discovery_sessions"
    __table_args__ = (
        Index("ix_discovery_sessions_workspace_status", "workspace_id", "status"),
        CheckConstraint(
            "status IN ('active', 'converged', 'halted', 'iteration_limit_reached')",
            name="ck_discovery_sessions_status",
        ),
    )

    research_question: Mapped[str] = mapped_column(Text(), nullable=False)
    corpus_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    config: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default=DiscoverySessionStatus.active.value,
    )
    current_cycle: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    convergence_metrics: Mapped[dict[str, Any] | None] = mapped_column(
        postgresql.JSONB,
        nullable=True,
    )
    initiated_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    hypotheses: Mapped[list[Hypothesis]] = relationship(
        "platform.discovery.models.Hypothesis",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    cycles: Mapped[list[GDECycle]] = relationship(
        "platform.discovery.models.GDECycle",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class GDECycle(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """State for one generate-debate-evolve iteration."""

    __tablename__ = "discovery_gde_cycles"
    __table_args__ = (
        Index("ix_gde_cycles_session_id", "session_id"),
        UniqueConstraint("session_id", "cycle_number", name="uq_cycle_session_number"),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_gde_cycles_status",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    cycle_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    status: Mapped[str] = mapped_column(String(length=16), nullable=False)
    generation_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    debate_record: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
    )
    refinement_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    convergence_metric: Mapped[float | None] = mapped_column(Float(), nullable=True)
    converged: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    session: Mapped[DiscoverySession] = relationship(
        "platform.discovery.models.DiscoverySession",
        back_populates="cycles",
    )


class Hypothesis(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Scientific conjecture generated in a discovery session."""

    __tablename__ = "discovery_hypotheses"
    __table_args__ = (
        Index("ix_hypotheses_session_id", "session_id"),
        Index("ix_hypotheses_workspace_status", "workspace_id", "status"),
        CheckConstraint(
            "status IN ('active', 'merged', 'retired')",
            name="ck_hypotheses_status",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_hypotheses_confidence",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    cycle_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_gde_cycles.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(length=500), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float(), nullable=False)
    generating_agent_fqn: Mapped[str] = mapped_column(String(length=255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        default=HypothesisStatus.active.value,
    )
    merged_into_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_hypotheses.id", ondelete="SET NULL"),
        nullable=True,
    )
    qdrant_point_id: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    embedding_status: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        default=EmbeddingStatus.pending.value,
    )
    rationale_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        postgresql.JSONB,
        nullable=True,
    )

    session: Mapped[DiscoverySession] = relationship(
        "platform.discovery.models.DiscoverySession",
        back_populates="hypotheses",
    )


class HypothesisCritique(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Structured multi-dimensional evaluation by a reviewer agent."""

    __tablename__ = "discovery_critiques"
    __table_args__ = (
        Index("ix_critiques_hypothesis_id", "hypothesis_id"),
        Index("ix_critiques_session_id", "session_id"),
    )

    hypothesis_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_hypotheses.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_agent_fqn: Mapped[str] = mapped_column(String(length=255), nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    composite_summary: Mapped[dict[str, Any] | None] = mapped_column(
        postgresql.JSONB,
        nullable=True,
    )
    is_aggregated: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)


class TournamentRound(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """A single pairwise comparison tournament round."""

    __tablename__ = "discovery_tournament_rounds"
    __table_args__ = (
        Index("ix_tournament_rounds_session_id", "session_id"),
        CheckConstraint(
            "status IN ('completed', 'in_progress', 'failed')",
            name="ck_tournament_rounds_status",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    cycle_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_gde_cycles.id", ondelete="SET NULL"),
        nullable=True,
    )
    round_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    pairwise_results: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    elo_changes: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    bye_hypothesis_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(length=16), nullable=False)


class EloScore(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Persistent Elo snapshot per hypothesis."""

    __tablename__ = "discovery_elo_scores"
    __table_args__ = (
        UniqueConstraint("hypothesis_id", "session_id", name="uq_elo_hypothesis_session"),
        Index("ix_elo_scores_session_id", "session_id"),
    )

    hypothesis_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_hypotheses.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_score: Mapped[float] = mapped_column(Float(), nullable=False, default=1000.0)
    wins: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    draws: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    score_history: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )


class DiscoveryExperiment(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Experiment plan and sandbox execution result linked to a hypothesis."""

    __tablename__ = "discovery_experiments"
    __table_args__ = (
        Index("ix_experiments_hypothesis_id", "hypothesis_id"),
        Index("ix_experiments_session_id", "session_id"),
        CheckConstraint(
            "governance_status IN ('pending', 'approved', 'rejected')",
            name="ck_experiments_governance_status",
        ),
        CheckConstraint(
            "execution_status IN ('not_started', 'running', 'completed', 'failed', 'timeout')",
            name="ck_experiments_execution_status",
        ),
    )

    hypothesis_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_hypotheses.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False, default=dict)
    governance_status: Mapped[str] = mapped_column(String(length=16), nullable=False)
    governance_violations: Mapped[list[dict[str, Any]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
    )
    execution_status: Mapped[str] = mapped_column(String(length=16), nullable=False)
    sandbox_execution_id: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    results: Mapped[dict[str, Any] | None] = mapped_column(postgresql.JSONB, nullable=True)
    designed_by_agent_fqn: Mapped[str] = mapped_column(String(length=255), nullable=False)


class HypothesisCluster(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Proximity clustering result for a discovery scope."""

    __tablename__ = "discovery_hypothesis_clusters"
    __table_args__ = (
        Index("ix_clusters_session_id", "session_id"),
        Index(
            "uq_cluster_session_label",
            "session_id",
            "cluster_label",
            unique=True,
            postgresql_where=text("session_id IS NOT NULL"),
        ),
        CheckConstraint(
            "classification IN ('normal', 'over_explored', 'gap')",
            name="ck_clusters_classification",
        ),
    )

    session_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discovery_sessions.id", ondelete="CASCADE"),
        nullable=True,
    )
    cluster_label: Mapped[str] = mapped_column(String(length=128), nullable=False)
    centroid_description: Mapped[str] = mapped_column(Text(), nullable=False)
    hypothesis_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    density_metric: Mapped[float] = mapped_column(Float(), nullable=False)
    classification: Mapped[str] = mapped_column(String(length=32), nullable=False)
    hypothesis_ids: Mapped[list[str]] = mapped_column(
        postgresql.JSONB, nullable=False, default=list
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DiscoveryWorkspaceSettings(Base, TenantScopedMixin, TimestampMixin):
    """Workspace-level proximity graph settings and recompute metadata."""

    __tablename__ = "discovery_workspace_settings"

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    bias_enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    recompute_interval_minutes: Mapped[int] = mapped_column(Integer(), nullable=False, default=15)
    last_recomputed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_transition_summary: Mapped[dict[str, Any] | None] = mapped_column(
        postgresql.JSONB,
        nullable=True,
    )
