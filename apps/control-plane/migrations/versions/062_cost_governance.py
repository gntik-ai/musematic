"""Cost governance and chargeback tables.

Revision ID: 062_cost_governance
Revises: 061_content_safety_fairness
Create Date: 2026-04-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "062_cost_governance"
down_revision: str | None = "061_content_safety_fairness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else sa.text("now()"),
    )


def _jsonb(name: str, default: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=nullable,
        server_default=sa.text(default),
    )


def upgrade() -> None:
    op.create_table(
        "cost_attributions",
        _uuid_pk(),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(length=255), nullable=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("registry_agent_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("origin", sa.String(length=64), nullable=False, server_default="user_trigger"),
        sa.Column("model_id", sa.String(length=256), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column(
            "model_cost_cents",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "compute_cost_cents",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "storage_cost_cents",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "overhead_cost_cents",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_cost_cents",
            sa.Numeric(precision=14, scale=4),
            sa.Computed(
                "model_cost_cents + compute_cost_cents + storage_cost_cents + overhead_cost_cents",
                persisted=True,
            ),
            nullable=False,
        ),
        _jsonb("token_counts", "'{}'::jsonb"),
        _jsonb("metadata", "'{}'::jsonb"),
        sa.Column(
            "correction_of",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cost_attributions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        _ts("created_at"),
        sa.CheckConstraint(
            "correction_of IS NOT NULL OR model_cost_cents >= 0",
            name="ck_cost_attr_model_nonnegative_original",
        ),
        sa.CheckConstraint(
            "correction_of IS NOT NULL OR compute_cost_cents >= 0",
            name="ck_cost_attr_compute_nonnegative_original",
        ),
        sa.CheckConstraint(
            "correction_of IS NOT NULL OR storage_cost_cents >= 0",
            name="ck_cost_attr_storage_nonnegative_original",
        ),
        sa.CheckConstraint(
            "correction_of IS NOT NULL OR overhead_cost_cents >= 0",
            name="ck_cost_attr_overhead_nonnegative_original",
        ),
    )
    op.create_index(
        "ix_cost_attributions_workspace_created",
        "cost_attributions",
        ["workspace_id", "created_at"],
    )
    op.create_index("ix_cost_attributions_execution", "cost_attributions", ["execution_id"])
    op.create_index(
        "ix_cost_attributions_workspace_agent_created",
        "cost_attributions",
        ["workspace_id", "agent_id", "created_at"],
    )
    op.create_index(
        "ix_cost_attributions_workspace_created_original",
        "cost_attributions",
        ["workspace_id", "created_at"],
        postgresql_where=sa.text("correction_of IS NULL"),
    )

    op.create_table(
        "workspace_budgets",
        _uuid_pk(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("budget_cents", sa.Integer(), nullable=False),
        _jsonb("soft_alert_thresholds", "'[50,80,100]'::jsonb"),
        sa.Column("hard_cap_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "admin_override_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("workspace_id", "period_type", name="uq_workspace_budget_period"),
        sa.CheckConstraint(
            "period_type IN ('daily','weekly','monthly')",
            name="ck_workspace_budget_period_type",
        ),
        sa.CheckConstraint("budget_cents > 0", name="ck_workspace_budget_positive"),
    )
    op.create_index("ix_workspace_budgets_workspace", "workspace_budgets", ["workspace_id"])

    op.create_table(
        "budget_alerts",
        _uuid_pk(),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace_budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("threshold_percentage", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spend_cents", sa.Numeric(precision=14, scale=4), nullable=False),
        _ts("triggered_at"),
        sa.UniqueConstraint(
            "budget_id",
            "threshold_percentage",
            "period_start",
            name="uq_budget_alert_threshold_period",
        ),
    )
    op.create_index(
        "ix_budget_alerts_workspace_triggered",
        "budget_alerts",
        ["workspace_id", "triggered_at"],
    )

    op.create_table(
        "cost_forecasts",
        _uuid_pk(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_cents", sa.Numeric(precision=14, scale=4), nullable=True),
        _jsonb("confidence_interval", "'{}'::jsonb"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        _ts("computed_at"),
    )
    op.create_index(
        "ix_cost_forecasts_workspace_period_end",
        "cost_forecasts",
        ["workspace_id", "period_end"],
    )

    op.create_table(
        "cost_anomalies",
        _uuid_pk(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("anomaly_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("baseline_cents", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("observed_cents", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("correlation_fingerprint", sa.String(length=128), nullable=False),
        _ts("detected_at"),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "acknowledged_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "anomaly_type IN ('sudden_spike','sustained_deviation')",
            name="ck_cost_anomaly_type",
        ),
        sa.CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name="ck_cost_anomaly_severity",
        ),
        sa.CheckConstraint(
            "state IN ('open','acknowledged','resolved')",
            name="ck_cost_anomaly_state",
        ),
    )
    op.create_index(
        "ix_cost_anomalies_workspace_open_detected",
        "cost_anomalies",
        ["workspace_id", "detected_at"],
        postgresql_where=sa.text("state = 'open'"),
    )
    op.create_index(
        "ix_cost_anomalies_workspace_fingerprint",
        "cost_anomalies",
        ["workspace_id", "correlation_fingerprint"],
    )

    op.create_table(
        "cost_overrides",
        _uuid_pk(),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "issued_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "redeemed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("created_at"),
    )
    op.create_index(
        "ix_cost_overrides_workspace_created",
        "cost_overrides",
        ["workspace_id", "created_at"],
    )
    op.create_index("uq_cost_overrides_token_hash", "cost_overrides", ["token_hash"], unique=True)

    op.add_column(
        "workspaces_settings",
        _jsonb("cost_budget", "'{}'::jsonb"),
    )
    op.execute(
        "COMMENT ON COLUMN workspaces_settings.cost_budget IS "
        "'Workspace settings may include cost_budget UI hints; workspace_budgets is source of truth.'"
    )


def downgrade() -> None:
    op.drop_column("workspaces_settings", "cost_budget")
    op.drop_index("uq_cost_overrides_token_hash", table_name="cost_overrides")
    op.drop_index("ix_cost_overrides_workspace_created", table_name="cost_overrides")
    op.drop_table("cost_overrides")
    op.drop_index("ix_cost_anomalies_workspace_fingerprint", table_name="cost_anomalies")
    op.drop_index("ix_cost_anomalies_workspace_open_detected", table_name="cost_anomalies")
    op.drop_table("cost_anomalies")
    op.drop_index("ix_cost_forecasts_workspace_period_end", table_name="cost_forecasts")
    op.drop_table("cost_forecasts")
    op.drop_index("ix_budget_alerts_workspace_triggered", table_name="budget_alerts")
    op.drop_table("budget_alerts")
    op.drop_index("ix_workspace_budgets_workspace", table_name="workspace_budgets")
    op.drop_table("workspace_budgets")
    op.drop_index("ix_cost_attributions_workspace_created_original", table_name="cost_attributions")
    op.drop_index("ix_cost_attributions_workspace_agent_created", table_name="cost_attributions")
    op.drop_index("ix_cost_attributions_execution", table_name="cost_attributions")
    op.drop_index("ix_cost_attributions_workspace_created", table_name="cost_attributions")
    op.drop_table("cost_attributions")
