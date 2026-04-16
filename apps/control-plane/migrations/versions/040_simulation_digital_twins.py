"""Simulation and digital twins schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "040_simulation_digital_twins"
down_revision = "039_scientific_discovery"
branch_labels = None
depends_on = None


def _uuid_pk() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def _workspace() -> sa.Column[object]:
    return sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "simulation_isolation_policies",
        _uuid_pk(),
        _workspace(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "blocked_actions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "stubbed_actions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "permitted_read_sources",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "halt_on_critical_breach", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        *_timestamps(),
    )
    op.create_index(
        "ix_isolation_policies_workspace_default",
        "simulation_isolation_policies",
        ["workspace_id", "is_default"],
    )
    op.create_index(
        "ix_simulation_isolation_policies_workspace_id",
        "simulation_isolation_policies",
        ["workspace_id"],
    )

    op.create_table(
        "simulation_runs",
        _uuid_pk(),
        _workspace(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scenario_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "digital_twin_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="provisioning"),
        sa.Column("isolation_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("controller_run_id", sa.String(length=128), nullable=True),
        sa.Column("isolation_bundle_fingerprint", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("results", postgresql.JSONB(), nullable=True),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["isolation_policy_id"],
            ["simulation_isolation_policies.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('provisioning', 'running', 'completed', 'cancelled', 'failed', 'timeout')",
            name="ck_run_status",
        ),
    )
    op.create_index(
        "ix_simulation_runs_workspace_status", "simulation_runs", ["workspace_id", "status"]
    )
    op.create_index("ix_simulation_runs_workspace_id", "simulation_runs", ["workspace_id"])

    op.create_table(
        "simulation_digital_twins",
        _uuid_pk(),
        _workspace(),
        sa.Column("source_agent_fqn", sa.String(length=255), nullable=False),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_twin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "config_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "behavioral_history_summary",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "modifications",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["parent_twin_id"], ["simulation_digital_twins.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint("version >= 1", name="ck_twin_version_positive"),
    )
    op.create_index("ix_digital_twins_agent_fqn", "simulation_digital_twins", ["source_agent_fqn"])
    op.create_index(
        "ix_digital_twins_workspace_active",
        "simulation_digital_twins",
        ["workspace_id", "is_active"],
    )
    op.create_index(
        "ix_simulation_digital_twins_workspace_id", "simulation_digital_twins", ["workspace_id"]
    )

    op.create_table(
        "simulation_behavioral_predictions",
        _uuid_pk(),
        sa.Column("digital_twin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "condition_modifiers",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("predicted_metrics", postgresql.JSONB(), nullable=True),
        sa.Column("confidence_level", sa.String(length=32), nullable=True),
        sa.Column("history_days_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accuracy_report", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["digital_twin_id"], ["simulation_digital_twins.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "confidence_level IS NULL OR confidence_level IN "
            "('high', 'medium', 'low', 'insufficient_data')",
            name="ck_prediction_confidence_level",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'insufficient_data', 'failed')",
            name="ck_prediction_status",
        ),
    )
    op.create_index(
        "ix_behavioral_predictions_twin_id",
        "simulation_behavioral_predictions",
        ["digital_twin_id"],
    )

    op.create_table(
        "simulation_comparison_reports",
        _uuid_pk(),
        sa.Column("comparison_type", sa.String(length=64), nullable=False),
        sa.Column("primary_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secondary_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("production_baseline_period", postgresql.JSONB(), nullable=True),
        sa.Column("prediction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metric_differences",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("overall_verdict", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("compatible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "incompatibility_reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(["primary_run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["secondary_run_id"], ["simulation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["prediction_id"],
            ["simulation_behavioral_predictions.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "comparison_type IN "
            "('simulation_vs_simulation', 'simulation_vs_production', 'prediction_vs_actual')",
            name="ck_comparison_type",
        ),
        sa.CheckConstraint(
            "overall_verdict IS NULL OR overall_verdict IN "
            "('primary_better', 'secondary_better', 'equivalent', 'inconclusive')",
            name="ck_comparison_verdict",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_comparison_status",
        ),
    )
    op.create_index(
        "ix_comparison_reports_primary_run_id",
        "simulation_comparison_reports",
        ["primary_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_comparison_reports_primary_run_id", table_name="simulation_comparison_reports"
    )
    op.drop_table("simulation_comparison_reports")
    op.drop_index(
        "ix_behavioral_predictions_twin_id", table_name="simulation_behavioral_predictions"
    )
    op.drop_table("simulation_behavioral_predictions")
    op.drop_index("ix_simulation_digital_twins_workspace_id", table_name="simulation_digital_twins")
    op.drop_index("ix_digital_twins_workspace_active", table_name="simulation_digital_twins")
    op.drop_index("ix_digital_twins_agent_fqn", table_name="simulation_digital_twins")
    op.drop_table("simulation_digital_twins")
    op.drop_index("ix_simulation_runs_workspace_id", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_workspace_status", table_name="simulation_runs")
    op.drop_table("simulation_runs")
    op.drop_index(
        "ix_simulation_isolation_policies_workspace_id",
        table_name="simulation_isolation_policies",
    )
    op.drop_index(
        "ix_isolation_policies_workspace_default",
        table_name="simulation_isolation_policies",
    )
    op.drop_table("simulation_isolation_policies")
