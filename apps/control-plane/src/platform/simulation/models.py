from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin, WorkspaceScopedMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy import (
    UUID as SQLUUID,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

JSONBType = JSON().with_variant(postgresql.JSONB, "postgresql")


class SimulationRunStatus(StrEnum):
    provisioning = "provisioning"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"
    timeout = "timeout"


class PredictionStatus(StrEnum):
    pending = "pending"
    completed = "completed"
    insufficient_data = "insufficient_data"
    failed = "failed"


class PredictionConfidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"
    insufficient_data = "insufficient_data"


class ComparisonType(StrEnum):
    simulation_vs_simulation = "simulation_vs_simulation"
    simulation_vs_production = "simulation_vs_production"
    prediction_vs_actual = "prediction_vs_actual"


class ComparisonStatus(StrEnum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class ComparisonVerdict(StrEnum):
    primary_better = "primary_better"
    secondary_better = "secondary_better"
    equivalent = "equivalent"
    inconclusive = "inconclusive"


class SimulationIsolationPolicy(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "simulation_isolation_policies"
    __table_args__ = (
        Index("ix_isolation_policies_workspace_default", "workspace_id", "is_default"),
    )

    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    blocked_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONBType,
        nullable=False,
        default=list,
    )
    stubbed_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONBType,
        nullable=False,
        default=list,
    )
    permitted_read_sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONBType,
        nullable=False,
        default=list,
    )
    is_default: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    halt_on_critical_breach: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)


class SimulationScenario(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "simulation_scenarios"
    __table_args__ = (
        Index("IX_simulation_scenarios_workspace_id_archived_at", "workspace_id", "archived_at"),
        Index(
            "UQ_simulation_scenarios_workspace_name_active",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    agents_config: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    workflow_template_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    mock_set_config: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    input_distribution: Mapped[dict[str, Any]] = mapped_column(
        JSONBType,
        nullable=False,
        default=dict,
    )
    twin_fidelity: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    success_criteria: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONBType,
        nullable=False,
        default=list,
    )
    run_schedule: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )


class SimulationRun(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "simulation_runs"
    __table_args__ = (
        Index("ix_simulation_runs_workspace_status", "workspace_id", "status"),
        CheckConstraint(
            "status IN ('provisioning', 'running', 'completed', 'cancelled', 'failed', 'timeout')",
            name="ck_run_status",
        ),
    )

    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    scenario_config: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    digital_twin_ids: Mapped[list[str]] = mapped_column(JSONBType, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default=SimulationRunStatus.provisioning.value,
    )
    isolation_policy_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("simulation_isolation_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    scenario_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("simulation_scenarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    controller_run_id: Mapped[str | None] = mapped_column(String(length=128), nullable=True)
    isolation_bundle_fingerprint: Mapped[str | None] = mapped_column(
        String(length=255),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, nullable=True)
    initiated_by: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), nullable=False)

    isolation_policy: Mapped[SimulationIsolationPolicy | None] = relationship(
        "platform.simulation.models.SimulationIsolationPolicy",
    )
    scenario: Mapped[SimulationScenario | None] = relationship(
        "platform.simulation.models.SimulationScenario",
    )


class DigitalTwin(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "simulation_digital_twins"
    __table_args__ = (
        Index("ix_digital_twins_agent_fqn", "source_agent_fqn"),
        Index("ix_digital_twins_workspace_active", "workspace_id", "is_active"),
        CheckConstraint("version >= 1", name="ck_twin_version_positive"),
    )

    source_agent_fqn: Mapped[str] = mapped_column(String(length=255), nullable=False)
    source_revision_id: Mapped[UUID | None] = mapped_column(SQLUUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    parent_twin_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("simulation_digital_twins.id", ondelete="SET NULL"),
        nullable=True,
    )
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONBType,
        nullable=False,
        default=dict,
    )
    behavioral_history_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONBType,
        nullable=False,
        default=dict,
    )
    modifications: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONBType,
        nullable=False,
        default=list,
    )
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    parent_twin: Mapped[DigitalTwin | None] = relationship(
        "platform.simulation.models.DigitalTwin",
        remote_side="DigitalTwin.id",
    )


class BehavioralPrediction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "simulation_behavioral_predictions"
    __table_args__ = (
        Index("ix_behavioral_predictions_twin_id", "digital_twin_id"),
        CheckConstraint(
            "confidence_level IS NULL OR confidence_level IN "
            "('high', 'medium', 'low', 'insufficient_data')",
            name="ck_prediction_confidence_level",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'insufficient_data', 'failed')",
            name="ck_prediction_status",
        ),
    )

    digital_twin_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("simulation_digital_twins.id", ondelete="CASCADE"),
        nullable=False,
    )
    condition_modifiers: Mapped[dict[str, Any]] = mapped_column(
        JSONBType,
        nullable=False,
        default=dict,
    )
    predicted_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, nullable=True)
    confidence_level: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    history_days_used: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    accuracy_report: Mapped[dict[str, Any] | None] = mapped_column(JSONBType, nullable=True)
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default=PredictionStatus.pending.value,
    )

    digital_twin: Mapped[DigitalTwin] = relationship("platform.simulation.models.DigitalTwin")


class SimulationComparisonReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "simulation_comparison_reports"
    __table_args__ = (
        Index("ix_comparison_reports_primary_run_id", "primary_run_id"),
        CheckConstraint(
            "comparison_type IN "
            "('simulation_vs_simulation', 'simulation_vs_production', 'prediction_vs_actual')",
            name="ck_comparison_type",
        ),
        CheckConstraint(
            "overall_verdict IS NULL OR overall_verdict IN "
            "('primary_better', 'secondary_better', 'equivalent', 'inconclusive')",
            name="ck_comparison_verdict",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_comparison_status",
        ),
    )

    comparison_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    primary_run_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    secondary_run_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    production_baseline_period: Mapped[dict[str, Any] | None] = mapped_column(
        JSONBType,
        nullable=True,
    )
    prediction_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("simulation_behavioral_predictions.id", ondelete="SET NULL"),
        nullable=True,
    )
    metric_differences: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONBType,
        nullable=False,
        default=list,
    )
    overall_verdict: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        default=ComparisonStatus.pending.value,
    )
    compatible: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    incompatibility_reasons: Mapped[list[str]] = mapped_column(
        JSONBType,
        nullable=False,
        default=list,
    )

    primary_run: Mapped[SimulationRun] = relationship(
        "platform.simulation.models.SimulationRun",
        foreign_keys=[primary_run_id],
    )
    secondary_run: Mapped[SimulationRun | None] = relationship(
        "platform.simulation.models.SimulationRun",
        foreign_keys=[secondary_run_id],
    )
