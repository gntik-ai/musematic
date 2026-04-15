from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin, WorkspaceScopedMixin
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class _CreatedOnlyMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BaselineStatus(StrEnum):
    pending = "pending"
    ready = "ready"
    superseded = "superseded"


class RegressionAlertStatus(StrEnum):
    active = "active"
    resolved = "resolved"
    dismissed = "dismissed"


class CanaryDeploymentStatus(StrEnum):
    active = "active"
    auto_promoted = "auto_promoted"
    auto_rolled_back = "auto_rolled_back"
    manually_promoted = "manually_promoted"
    manually_rolled_back = "manually_rolled_back"
    completed = "completed"


class RetirementWorkflowStatus(StrEnum):
    initiated = "initiated"
    grace_period = "grace_period"
    retired = "retired"
    halted = "halted"


class AdaptationProposalStatus(StrEnum):
    proposed = "proposed"
    no_opportunities = "no_opportunities"
    approved = "approved"
    rejected = "rejected"
    testing = "testing"
    passed = "passed"
    failed = "failed"
    promoted = "promoted"


class AgentHealthConfig(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_health_configs"
    __table_args__ = (
        Index("uq_agentops_health_configs_workspace_id", "workspace_id", unique=True),
    )

    weight_uptime: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("20.00"),
        server_default=text("20.00"),
    )
    weight_quality: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("35.00"),
        server_default=text("35.00"),
    )
    weight_safety: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("25.00"),
        server_default=text("25.00"),
    )
    weight_cost_efficiency: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("10.00"),
        server_default=text("10.00"),
    )
    weight_satisfaction: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("10.00"),
        server_default=text("10.00"),
    )
    warning_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("60.00"),
        server_default=text("60.00"),
    )
    critical_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("40.00"),
        server_default=text("40.00"),
    )
    scoring_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=15,
        server_default=text("15"),
    )
    min_sample_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=50,
        server_default=text("50"),
    )
    rolling_window_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default=text("30"),
    )


class AgentHealthScore(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_health_scores"
    __table_args__ = (
        Index("ix_agentops_health_scores_agent_workspace", "agent_fqn", "workspace_id"),
        Index(
            "uq_agentops_health_scores_agent_workspace",
            "agent_fqn",
            "workspace_id",
            unique=True,
        ),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    composite_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    uptime_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    safety_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    cost_efficiency_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    satisfaction_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    weights_snapshot: Mapped[dict[str, float]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    missing_dimensions: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(String(length=64)),
        nullable=False,
        default=list,
        server_default=text("'{}'::varchar[]"),
    )
    sample_counts: Mapped[dict[str, int]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    observation_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    observation_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    below_warning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    below_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    insufficient_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BehavioralBaseline(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_behavioral_baselines"
    __table_args__ = (
        Index("ix_agentops_baselines_agent_workspace", "agent_fqn", "workspace_id"),
        Index("uq_agentops_baselines_revision_id", "revision_id", unique=True),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    quality_mean: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quality_stddev: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_p50_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_p95_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_stddev_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_rate_mean: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_per_execution_mean: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_per_execution_stddev: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    safety_pass_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baseline_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    baseline_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default=BaselineStatus.pending,
    )


class BehavioralRegressionAlert(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_regression_alerts"
    __table_args__ = (
        Index("ix_agentops_regression_agent_workspace", "agent_fqn", "workspace_id"),
        Index("ix_agentops_regression_new_revision", "new_revision_id"),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    new_revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    baseline_revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default=RegressionAlertStatus.active,
    )
    regressed_dimensions: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(String(length=64)),
        nullable=False,
        default=list,
        server_default=text("'{}'::varchar[]"),
    )
    statistical_test: Mapped[str] = mapped_column(String(length=64), nullable=False)
    p_value: Mapped[float] = mapped_column(Float, nullable=False)
    effect_size: Mapped[float] = mapped_column(Float, nullable=False)
    significance_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.05)
    sample_sizes: Mapped[dict[str, int]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    triggered_rollback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CiCdGateResult(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_cicd_gate_results"
    __table_args__ = (
        Index("ix_agentops_gate_results_agent_workspace", "agent_fqn", "workspace_id"),
        Index("ix_agentops_gate_results_revision", "revision_id"),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    overall_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    policy_gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    policy_gate_detail: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    policy_gate_remediation: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evaluation_gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evaluation_gate_detail: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    evaluation_gate_remediation: Mapped[str | None] = mapped_column(Text(), nullable=True)
    certification_gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    certification_gate_detail: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    certification_gate_remediation: Mapped[str | None] = mapped_column(Text(), nullable=True)
    regression_gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regression_gate_detail: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    regression_gate_remediation: Mapped[str | None] = mapped_column(Text(), nullable=True)
    trust_tier_gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trust_tier_gate_detail: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    trust_tier_gate_remediation: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    evaluation_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CanaryDeployment(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_canary_deployments"
    __table_args__ = (
        Index("ix_agentops_canary_agent_workspace", "agent_fqn", "workspace_id"),
        Index("ix_agentops_canary_status", "status"),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    production_revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    canary_revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    initiated_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    traffic_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    observation_window_hours: Mapped[float] = mapped_column(Float, nullable=False)
    quality_tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    latency_tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    error_rate_tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    cost_tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default=CanaryDeploymentStatus.active,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    observation_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    manual_override_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    manual_override_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    latest_metrics_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        postgresql.JSONB,
        nullable=True,
        default=None,
    )


class RetirementWorkflow(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_retirement_workflows"
    __table_args__ = (
        Index("ix_agentops_retirement_agent_workspace", "agent_fqn", "workspace_id"),
        Index("ix_agentops_retirement_status", "status"),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    trigger_reason: Mapped[str] = mapped_column(String(length=64), nullable=False)
    trigger_detail: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default=RetirementWorkflowStatus.initiated,
    )
    dependent_workflows: Mapped[list[dict[str, object]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    high_impact_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    operator_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notifications_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    grace_period_starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    grace_period_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    halted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    halted_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    halt_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)


class GovernanceEvent(Base, UUIDMixin, _CreatedOnlyMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_governance_events"
    __table_args__ = (
        Index("ix_agentops_governance_agent_workspace", "agent_fqn", "workspace_id"),
        Index("ix_agentops_governance_event_type", "event_type"),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    revision_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class AdaptationProposal(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "agentops_adaptation_proposals"
    __table_args__ = (
        Index("ix_agentops_adaptation_agent_workspace", "agent_fqn", "workspace_id"),
        Index("ix_agentops_adaptation_status", "status"),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    revision_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default=AdaptationProposalStatus.proposed,
    )
    proposal_details: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    signals: Mapped[list[dict[str, object]]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    review_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    candidate_revision_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    evaluation_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
