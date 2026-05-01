from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.common.models.base import Base
from platform.common.models.mixins import AuditMixin, TenantScopedMixin, TimestampMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class CostAttribution(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "cost_attributions"
    __table_args__ = (
        Index("ix_cost_attributions_workspace_created", "workspace_id", "created_at"),
        Index("ix_cost_attributions_execution", "execution_id"),
        Index(
            "ix_cost_attributions_workspace_agent_created",
            "workspace_id",
            "agent_id",
            "created_at",
        ),
        Index(
            "ix_cost_attributions_workspace_created_original",
            "workspace_id",
            "created_at",
            postgresql_where=text("correction_of IS NULL"),
        ),
        CheckConstraint(
            "correction_of IS NOT NULL OR model_cost_cents >= 0",
            name="ck_cost_attr_model_nonnegative_original",
        ),
        CheckConstraint(
            "correction_of IS NOT NULL OR compute_cost_cents >= 0",
            name="ck_cost_attr_compute_nonnegative_original",
        ),
        CheckConstraint(
            "correction_of IS NOT NULL OR storage_cost_cents >= 0",
            name="ck_cost_attr_storage_nonnegative_original",
        ),
        CheckConstraint(
            "correction_of IS NOT NULL OR overhead_cost_cents >= 0",
            name="ck_cost_attr_overhead_nonnegative_original",
        ),
    )

    execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("registry_agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    origin: Mapped[str] = mapped_column(String(length=64), nullable=False, default="user_trigger")
    model_id: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    currency: Mapped[str] = mapped_column(String(length=3), nullable=False, default="USD")
    model_cost_cents: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0"),
    )
    compute_cost_cents: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0"),
    )
    storage_cost_cents: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0"),
    )
    overhead_cost_cents: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0"),
    )
    total_cost_cents: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=4),
        Computed(
            "model_cost_cents + compute_cost_cents + storage_cost_cents + overhead_cost_cents",
            persisted=True,
        ),
        nullable=False,
    )
    token_counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    attribution_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    correction_of: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("cost_attributions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class WorkspaceBudget(Base, TenantScopedMixin, UUIDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "workspace_budgets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "period_type", name="uq_workspace_budget_period"),
        CheckConstraint(
            "period_type IN ('daily','weekly','monthly')",
            name="ck_workspace_budget_period_type",
        ),
        CheckConstraint("budget_cents > 0", name="ck_workspace_budget_positive"),
        Index("ix_workspace_budgets_workspace", "workspace_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_type: Mapped[str] = mapped_column(String(length=16), nullable=False)
    budget_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    soft_alert_thresholds: Mapped[list[int]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=lambda: [50, 80, 100],
    )
    hard_cap_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    admin_override_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    currency: Mapped[str] = mapped_column(String(length=3), nullable=False, default="USD")


class BudgetAlert(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "budget_alerts"
    __table_args__ = (
        UniqueConstraint(
            "budget_id",
            "threshold_percentage",
            "period_start",
            name="uq_budget_alert_threshold_period",
        ),
        Index("ix_budget_alerts_workspace_triggered", "workspace_id", "triggered_at"),
    )

    budget_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspace_budgets.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    threshold_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    spend_cents: Mapped[Decimal] = mapped_column(Numeric(precision=14, scale=4), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CostForecast(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "cost_forecasts"
    __table_args__ = (
        Index("ix_cost_forecasts_workspace_period_end", "workspace_id", "period_end"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_cents: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=4),
        nullable=True,
    )
    confidence_interval: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    currency: Mapped[str] = mapped_column(String(length=3), nullable=False, default="USD")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CostAnomaly(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "cost_anomalies"
    __table_args__ = (
        CheckConstraint(
            "anomaly_type IN ('sudden_spike','sustained_deviation')",
            name="ck_cost_anomaly_type",
        ),
        CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name="ck_cost_anomaly_severity",
        ),
        CheckConstraint(
            "state IN ('open','acknowledged','resolved')",
            name="ck_cost_anomaly_state",
        ),
        Index(
            "ix_cost_anomalies_workspace_open_detected",
            "workspace_id",
            "detected_at",
            postgresql_where=text("state = 'open'"),
        ),
        Index("ix_cost_anomalies_workspace_fingerprint", "workspace_id", "correlation_fingerprint"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    anomaly_type: Mapped[str] = mapped_column(String(length=32), nullable=False)
    severity: Mapped[str] = mapped_column(String(length=16), nullable=False)
    state: Mapped[str] = mapped_column(String(length=16), nullable=False, default="open")
    baseline_cents: Mapped[Decimal] = mapped_column(Numeric(precision=14, scale=4), nullable=False)
    observed_cents: Mapped[Decimal] = mapped_column(Numeric(precision=14, scale=4), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_fingerprint: Mapped[str] = mapped_column(String(length=128), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OverrideRecord(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "cost_overrides"
    __table_args__ = (
        Index("ix_cost_overrides_workspace_created", "workspace_id", "created_at"),
        Index("uq_cost_overrides_token_hash", "token_hash", unique=True),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    issued_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(length=128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
