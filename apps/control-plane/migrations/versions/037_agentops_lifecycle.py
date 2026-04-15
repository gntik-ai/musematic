"""AgentOps lifecycle management schema.

ClickHouse DDL for separate application via clickhouse-connect:

CREATE TABLE IF NOT EXISTS agentops_behavioral_versions (
    workspace_id UUID,
    agent_fqn String,
    revision_id UUID,
    measured_at DateTime64(3, 'UTC'),
    quality_score Float64,
    latency_ms Float64,
    error_rate Float64,
    cost_per_execution Float64,
    safety_pass_rate Float64
) ENGINE = MergeTree
PARTITION BY toYYYYMM(measured_at)
ORDER BY (workspace_id, agent_fqn, revision_id, measured_at);
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "037_agentops_lifecycle"
down_revision = "034_evaluation_testing_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agentops_health_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weight_uptime", sa.Numeric(5, 2), nullable=False, server_default=sa.text("20.00")),
        sa.Column("weight_quality", sa.Numeric(5, 2), nullable=False, server_default=sa.text("35.00")),
        sa.Column("weight_safety", sa.Numeric(5, 2), nullable=False, server_default=sa.text("25.00")),
        sa.Column(
            "weight_cost_efficiency",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("10.00"),
        ),
        sa.Column(
            "weight_satisfaction",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("10.00"),
        ),
        sa.Column(
            "warning_threshold",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("60.00"),
        ),
        sa.Column(
            "critical_threshold",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("40.00"),
        ),
        sa.Column(
            "scoring_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("15"),
        ),
        sa.Column("min_sample_size", sa.Integer(), nullable=False, server_default=sa.text("50")),
        sa.Column(
            "rolling_window_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "uq_agentops_health_configs_workspace_id",
        "agentops_health_configs",
        ["workspace_id"],
        unique=True,
    )

    op.create_table(
        "agentops_health_scores",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("composite_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("uptime_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("quality_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("safety_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("cost_efficiency_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("satisfaction_score", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "weights_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "missing_dimensions",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "sample_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("observation_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("below_warning", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("below_critical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("insufficient_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_agentops_health_scores_agent_workspace",
        "agentops_health_scores",
        ["agent_fqn", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "uq_agentops_health_scores_agent_workspace",
        "agentops_health_scores",
        ["agent_fqn", "workspace_id"],
        unique=True,
    )

    op.create_table(
        "agentops_behavioral_baselines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quality_mean", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("quality_stddev", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_p50_ms", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_p95_ms", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_stddev_ms", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_rate_mean", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_per_execution_mean", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_per_execution_stddev", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("safety_pass_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("baseline_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_agentops_baselines_agent_workspace",
        "agentops_behavioral_baselines",
        ["agent_fqn", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "uq_agentops_baselines_revision_id",
        "agentops_behavioral_baselines",
        ["revision_id"],
        unique=True,
    )

    op.create_table(
        "agentops_regression_alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("new_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "regressed_dimensions",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column("statistical_test", sa.String(length=64), nullable=False),
        sa.Column("p_value", sa.Float(), nullable=False),
        sa.Column("effect_size", sa.Float(), nullable=False),
        sa.Column("significance_threshold", sa.Float(), nullable=False, server_default=sa.text("0.05")),
        sa.Column(
            "sample_sizes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("triggered_rollback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_agentops_regression_agent_workspace",
        "agentops_regression_alerts",
        ["agent_fqn", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_agentops_regression_new_revision",
        "agentops_regression_alerts",
        ["new_revision_id"],
        unique=False,
    )

    op.create_table(
        "agentops_cicd_gate_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("overall_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("policy_gate_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("policy_gate_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("policy_gate_remediation", sa.Text(), nullable=True),
        sa.Column("evaluation_gate_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("evaluation_gate_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evaluation_gate_remediation", sa.Text(), nullable=True),
        sa.Column("certification_gate_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("certification_gate_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("certification_gate_remediation", sa.Text(), nullable=True),
        sa.Column("regression_gate_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("regression_gate_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("regression_gate_remediation", sa.Text(), nullable=True),
        sa.Column("trust_tier_gate_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("trust_tier_gate_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trust_tier_gate_remediation", sa.Text(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("evaluation_duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_agentops_gate_results_agent_workspace",
        "agentops_cicd_gate_results",
        ["agent_fqn", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_agentops_gate_results_revision",
        "agentops_cicd_gate_results",
        ["revision_id"],
        unique=False,
    )

    op.create_table(
        "agentops_canary_deployments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("production_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canary_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("traffic_percentage", sa.Integer(), nullable=False),
        sa.Column("observation_window_hours", sa.Float(), nullable=False),
        sa.Column("quality_tolerance_pct", sa.Float(), nullable=False, server_default=sa.text("5")),
        sa.Column("latency_tolerance_pct", sa.Float(), nullable=False, server_default=sa.text("5")),
        sa.Column("error_rate_tolerance_pct", sa.Float(), nullable=False, server_default=sa.text("5")),
        sa.Column("cost_tolerance_pct", sa.Float(), nullable=False, server_default=sa.text("5")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("observation_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.Column("manual_override_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("manual_override_reason", sa.Text(), nullable=True),
        sa.Column("latest_metrics_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_agentops_canary_agent_workspace",
        "agentops_canary_deployments",
        ["agent_fqn", "workspace_id"],
        unique=False,
    )
    op.create_index("ix_agentops_canary_status", "agentops_canary_deployments", ["status"], unique=False)

    op.create_table(
        "agentops_retirement_workflows",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_reason", sa.String(length=64), nullable=False),
        sa.Column("trigger_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'initiated'")),
        sa.Column("dependent_workflows", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("high_impact_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("operator_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notifications_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_period_days", sa.Integer(), nullable=False, server_default=sa.text("14")),
        sa.Column("grace_period_starts_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("grace_period_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("halted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("halted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("halt_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_agentops_retirement_agent_workspace",
        "agentops_retirement_workflows",
        ["agent_fqn", "workspace_id"],
        unique=False,
    )
    op.create_index("ix_agentops_retirement_status", "agentops_retirement_workflows", ["status"], unique=False)

    op.create_table(
        "agentops_governance_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_agentops_governance_agent_workspace",
        "agentops_governance_events",
        ["agent_fqn", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_agentops_governance_event_type",
        "agentops_governance_events",
        ["event_type"],
        unique=False,
    )

    op.create_table(
        "agentops_adaptation_proposals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'proposed'")),
        sa.Column("proposal_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("candidate_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_agentops_adaptation_agent_workspace",
        "agentops_adaptation_proposals",
        ["agent_fqn", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_agentops_adaptation_status",
        "agentops_adaptation_proposals",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agentops_adaptation_status", table_name="agentops_adaptation_proposals")
    op.drop_index("ix_agentops_adaptation_agent_workspace", table_name="agentops_adaptation_proposals")
    op.drop_table("agentops_adaptation_proposals")

    op.drop_index("ix_agentops_governance_event_type", table_name="agentops_governance_events")
    op.drop_index("ix_agentops_governance_agent_workspace", table_name="agentops_governance_events")
    op.drop_table("agentops_governance_events")

    op.drop_index("ix_agentops_retirement_status", table_name="agentops_retirement_workflows")
    op.drop_index("ix_agentops_retirement_agent_workspace", table_name="agentops_retirement_workflows")
    op.drop_table("agentops_retirement_workflows")

    op.drop_index("ix_agentops_canary_status", table_name="agentops_canary_deployments")
    op.drop_index("ix_agentops_canary_agent_workspace", table_name="agentops_canary_deployments")
    op.drop_table("agentops_canary_deployments")

    op.drop_index("ix_agentops_gate_results_revision", table_name="agentops_cicd_gate_results")
    op.drop_index("ix_agentops_gate_results_agent_workspace", table_name="agentops_cicd_gate_results")
    op.drop_table("agentops_cicd_gate_results")

    op.drop_index("ix_agentops_regression_new_revision", table_name="agentops_regression_alerts")
    op.drop_index("ix_agentops_regression_agent_workspace", table_name="agentops_regression_alerts")
    op.drop_table("agentops_regression_alerts")

    op.drop_index("uq_agentops_baselines_revision_id", table_name="agentops_behavioral_baselines")
    op.drop_index("ix_agentops_baselines_agent_workspace", table_name="agentops_behavioral_baselines")
    op.drop_table("agentops_behavioral_baselines")

    op.drop_index("uq_agentops_health_scores_agent_workspace", table_name="agentops_health_scores")
    op.drop_index("ix_agentops_health_scores_agent_workspace", table_name="agentops_health_scores")
    op.drop_table("agentops_health_scores")

    op.drop_index("uq_agentops_health_configs_workspace_id", table_name="agentops_health_configs")
    op.drop_table("agentops_health_configs")
