from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    AuditMixin,
    TimestampMixin,
    UUIDMixin,
    WorkspaceScopedMixin,
)
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class CompactionStrategyType(StrEnum):
    relevance_truncation = "relevance_truncation"
    priority_eviction = "priority_eviction"
    hierarchical_compression = "hierarchical_compression"
    semantic_deduplication = "semantic_deduplication"


class ContextSourceType(StrEnum):
    system_instructions = "system_instructions"
    workflow_state = "workflow_state"
    conversation_history = "conversation_history"
    long_term_memory = "long_term_memory"
    tool_outputs = "tool_outputs"
    connector_payloads = "connector_payloads"
    workspace_metadata = "workspace_metadata"
    reasoning_traces = "reasoning_traces"
    workspace_goal_history = "workspace_goal_history"


class AbTestStatus(StrEnum):
    active = "active"
    paused = "paused"
    completed = "completed"


class ProfileAssignmentLevel(StrEnum):
    agent = "agent"
    role_type = "role_type"
    workspace = "workspace"


class CorrelationClassification(StrEnum):
    strong_positive = "strong_positive"
    moderate_positive = "moderate_positive"
    weak = "weak"
    moderate_negative = "moderate_negative"
    strong_negative = "strong_negative"
    inconclusive = "inconclusive"


class ContextEngineeringProfile(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin, AuditMixin):
    __tablename__ = "context_engineering_profiles"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_ce_profile_workspace_name"),
        Index("ix_ce_profile_workspace_default", "workspace_id", "is_default"),
    )

    name: Mapped[str] = mapped_column(String(length=120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    source_config: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    budget_config: Mapped[dict[str, object]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    compaction_strategies: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    quality_weights: Mapped[dict[str, float]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    privacy_overrides: Mapped[dict[str, object]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )

    assignments: Mapped[list[ContextProfileAssignment]] = relationship(
        "platform.context_engineering.models.ContextProfileAssignment",
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class ContextProfileAssignment(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "context_profile_assignments"
    __table_args__ = (
        Index("ix_ce_assignment_agent_fqn", "agent_fqn"),
        Index("ix_ce_assignment_role_type", "role_type"),
    )

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("context_engineering_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_level: Mapped[ProfileAssignmentLevel] = mapped_column(
        SAEnum(ProfileAssignmentLevel, name="ce_profile_assignment_level"),
        nullable=False,
    )
    agent_fqn: Mapped[str | None] = mapped_column(String(length=190), nullable=True)
    role_type: Mapped[str | None] = mapped_column(String(length=64), nullable=True)

    profile: Mapped[ContextEngineeringProfile] = relationship(
        "platform.context_engineering.models.ContextEngineeringProfile",
        back_populates="assignments",
    )


class ContextAssemblyRecord(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "context_assembly_records"
    __table_args__ = (
        Index("ix_ce_record_execution_step", "execution_id", "step_id"),
        Index("ix_ce_record_agent_fqn_created", "agent_fqn", "created_at"),
        Index("ix_ce_record_workspace_created", "workspace_id", "created_at"),
    )

    execution_id: Mapped[UUID] = mapped_column(nullable=False)
    step_id: Mapped[UUID] = mapped_column(nullable=False)
    agent_fqn: Mapped[str] = mapped_column(String(length=190), nullable=False)
    profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("context_engineering_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    quality_score_pre: Mapped[float] = mapped_column(Float(), nullable=False, default=0.0)
    quality_score_post: Mapped[float] = mapped_column(Float(), nullable=False, default=0.0)
    token_count_pre: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    token_count_post: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    sources_queried: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    sources_available: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    compaction_applied: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    compaction_actions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    privacy_exclusions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    provenance_chain: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    bundle_storage_key: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    ab_test_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("context_ab_tests.id", ondelete="SET NULL"),
        nullable=True,
    )
    ab_test_group: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    flags: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )


class ContextAbTest(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin, AuditMixin):
    __tablename__ = "context_ab_tests"
    __table_args__ = (
        Index("ix_ce_ab_test_workspace_status", "workspace_id", "status"),
        Index("ix_ce_ab_test_target_agent_fqn", "target_agent_fqn"),
    )

    name: Mapped[str] = mapped_column(String(length=120), nullable=False)
    control_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("context_engineering_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("context_engineering_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_agent_fqn: Mapped[str | None] = mapped_column(String(length=190), nullable=True)
    status: Mapped[AbTestStatus] = mapped_column(
        SAEnum(AbTestStatus, name="ce_ab_test_status"),
        nullable=False,
        default=AbTestStatus.active,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    control_assembly_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    variant_assembly_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    control_quality_mean: Mapped[float | None] = mapped_column(Float(), nullable=True)
    variant_quality_mean: Mapped[float | None] = mapped_column(Float(), nullable=True)
    control_token_mean: Mapped[float | None] = mapped_column(Float(), nullable=True)
    variant_token_mean: Mapped[float | None] = mapped_column(Float(), nullable=True)


class ContextDriftAlert(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "context_drift_alerts"
    __table_args__ = (
        Index("ix_ce_drift_alert_agent_fqn", "agent_fqn"),
        Index("ix_ce_drift_alert_workspace_resolved", "workspace_id", "resolved_at"),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=190), nullable=False)
    historical_mean: Mapped[float] = mapped_column(Float(), nullable=False)
    historical_stddev: Mapped[float] = mapped_column(Float(), nullable=False)
    recent_mean: Mapped[float] = mapped_column(Float(), nullable=False)
    degradation_delta: Mapped[float] = mapped_column(Float(), nullable=False)
    analysis_window_days: Mapped[int] = mapped_column(Integer(), nullable=False)
    suggested_actions: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CorrelationResult(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "context_engineering_correlation_results"
    __table_args__ = (
        Index("ix_ce_correlation_agent_window", "agent_fqn", "window_start", "window_end"),
        Index("ix_ce_correlation_classification", "classification"),
        Index(
            "uq_ce_correlation_window_metric",
            "workspace_id",
            "agent_fqn",
            "dimension",
            "performance_metric",
            "window_start",
            "window_end",
            unique=True,
        ),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=190), nullable=False)
    dimension: Mapped[str] = mapped_column(String(length=64), nullable=False)
    performance_metric: Mapped[str] = mapped_column(String(length=64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    coefficient: Mapped[float | None] = mapped_column(Float(), nullable=True)
    classification: Mapped[CorrelationClassification] = mapped_column(
        SAEnum(CorrelationClassification, name="correlation_classification", create_type=False),
        nullable=False,
    )
    data_point_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
