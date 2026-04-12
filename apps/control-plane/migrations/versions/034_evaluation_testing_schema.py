"""Evaluation and testing subsystem schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "034_evaluation_testing_schema"
down_revision = "033_fleet_management"
branch_labels = None
depends_on = None


evaluation_eval_set_status = postgresql.ENUM(
    "active",
    "archived",
    name="evaluation_eval_set_status",
    create_type=False,
)
evaluation_run_status = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    name="evaluation_run_status",
    create_type=False,
)
evaluation_verdict_status = postgresql.ENUM(
    "scored",
    "error",
    name="evaluation_verdict_status",
    create_type=False,
)
evaluation_experiment_status = postgresql.ENUM(
    "pending",
    "completed",
    "failed",
    name="evaluation_experiment_status",
    create_type=False,
)
evaluation_ate_run_status = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    "pre_check_failed",
    name="evaluation_ate_run_status",
    create_type=False,
)
evaluation_review_decision = postgresql.ENUM(
    "confirmed",
    "overridden",
    name="evaluation_review_decision",
    create_type=False,
)
testing_suite_type = postgresql.ENUM(
    "adversarial",
    "positive",
    "mixed",
    name="testing_suite_type",
    create_type=False,
)
testing_adversarial_category = postgresql.ENUM(
    "prompt_injection",
    "jailbreak",
    "contradictory",
    "malformed_data",
    "ambiguous",
    "resource_exhaustion",
    name="testing_adversarial_category",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    evaluation_eval_set_status.create(bind, checkfirst=True)
    evaluation_run_status.create(bind, checkfirst=True)
    evaluation_verdict_status.create(bind, checkfirst=True)
    evaluation_experiment_status.create(bind, checkfirst=True)
    evaluation_ate_run_status.create(bind, checkfirst=True)
    evaluation_review_decision.create(bind, checkfirst=True)
    testing_suite_type.create(bind, checkfirst=True)
    testing_adversarial_category.create(bind, checkfirst=True)

    op.create_table(
        "evaluation_eval_sets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scorer_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "pass_threshold",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.7"),
        ),
        sa.Column(
            "status",
            evaluation_eval_set_status,
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "ix_evaluation_eval_sets_workspace_status",
        "evaluation_eval_sets",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_evaluation_eval_sets_workspace_name_active",
        "evaluation_eval_sets",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "evaluation_benchmark_cases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("eval_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "input_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column(
            "scoring_criteria",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
        sa.ForeignKeyConstraint(
            ["eval_set_id"],
            ["evaluation_eval_sets.id"],
            name="fk_evaluation_benchmark_cases_eval_set_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_evaluation_benchmark_cases_eval_set_id",
        "evaluation_benchmark_cases",
        ["eval_set_id"],
        unique=False,
    )
    op.create_index(
        "uq_evaluation_benchmark_cases_eval_set_position",
        "evaluation_benchmark_cases",
        ["eval_set_id", "position"],
        unique=True,
    )

    op.create_table(
        "evaluation_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("eval_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            evaluation_run_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("passed_cases", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_cases", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_cases", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("aggregate_score", sa.Float(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["eval_set_id"],
            ["evaluation_eval_sets.id"],
            name="fk_evaluation_runs_eval_set_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_evaluation_runs_eval_set_id", "evaluation_runs", ["eval_set_id"], unique=False
    )
    op.create_index(
        "ix_evaluation_runs_workspace_status",
        "evaluation_runs",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index("ix_evaluation_runs_agent_fqn", "evaluation_runs", ["agent_fqn"], unique=False)

    op.create_table(
        "evaluation_judge_verdicts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actual_output", sa.Text(), nullable=False),
        sa.Column(
            "scorer_results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "status",
            evaluation_verdict_status,
            nullable=False,
            server_default=sa.text("'scored'"),
        ),
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
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evaluation_runs.id"],
            name="fk_evaluation_judge_verdicts_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_case_id"],
            ["evaluation_benchmark_cases.id"],
            name="fk_evaluation_judge_verdicts_case_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_evaluation_judge_verdicts_run_id", "evaluation_judge_verdicts", ["run_id"], unique=False
    )
    op.create_index(
        "ix_evaluation_judge_verdicts_case_id",
        "evaluation_judge_verdicts",
        ["benchmark_case_id"],
        unique=False,
    )
    op.create_index(
        "uq_evaluation_judge_verdicts_run_case",
        "evaluation_judge_verdicts",
        ["run_id", "benchmark_case_id"],
        unique=True,
    )

    op.create_table(
        "evaluation_ab_experiments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("run_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            evaluation_experiment_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("p_value", sa.Float(), nullable=True),
        sa.Column("confidence_interval", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("effect_size", sa.Float(), nullable=True),
        sa.Column("winner", sa.String(length=16), nullable=True),
        sa.Column("analysis_summary", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "ix_evaluation_ab_experiments_workspace_status",
        "evaluation_ab_experiments",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_ab_experiments_run_a_id",
        "evaluation_ab_experiments",
        ["run_a_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_ab_experiments_run_b_id",
        "evaluation_ab_experiments",
        ["run_b_id"],
        unique=False,
    )

    op.create_table(
        "evaluation_ate_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scenarios",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "scorer_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "performance_thresholds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "safety_checks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "ix_evaluation_ate_configs_workspace_id",
        "evaluation_ate_configs",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "uq_evaluation_ate_configs_workspace_name_active",
        "evaluation_ate_configs",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "evaluation_ate_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ate_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("simulation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            evaluation_ate_run_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_artifact_key", sa.String(length=512), nullable=True),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pre_check_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["ate_config_id"],
            ["evaluation_ate_configs.id"],
            name="fk_evaluation_ate_runs_ate_config_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_evaluation_ate_runs_ate_config_id",
        "evaluation_ate_runs",
        ["ate_config_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_ate_runs_workspace_status",
        "evaluation_ate_runs",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_ate_runs_agent_fqn", "evaluation_ate_runs", ["agent_fqn"], unique=False
    )

    op.create_table(
        "evaluation_robustness_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("eval_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("trial_count", sa.Integer(), nullable=False),
        sa.Column("completed_trials", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "status",
            evaluation_run_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("distribution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_unreliable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("variance_threshold", sa.Float(), nullable=False, server_default=sa.text("0.15")),
        sa.Column(
            "trial_run_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
        sa.ForeignKeyConstraint(
            ["eval_set_id"],
            ["evaluation_eval_sets.id"],
            name="fk_evaluation_robustness_runs_eval_set_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_case_id"],
            ["evaluation_benchmark_cases.id"],
            name="fk_evaluation_robustness_runs_case_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_evaluation_robustness_runs_eval_set_id",
        "evaluation_robustness_runs",
        ["eval_set_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_robustness_runs_workspace_status",
        "evaluation_robustness_runs",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_robustness_runs_agent_fqn",
        "evaluation_robustness_runs",
        ["agent_fqn"],
        unique=False,
    )

    op.create_table(
        "evaluation_human_grades",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("verdict_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", evaluation_review_decision, nullable=False),
        sa.Column("override_score", sa.Float(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("original_score", sa.Float(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
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
        sa.ForeignKeyConstraint(
            ["verdict_id"],
            ["evaluation_judge_verdicts.id"],
            name="fk_evaluation_human_grades_verdict_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_evaluation_human_grades_reviewer_id",
        "evaluation_human_grades",
        ["reviewer_id"],
        unique=False,
    )
    op.create_index(
        "uq_evaluation_human_grades_verdict_id",
        "evaluation_human_grades",
        ["verdict_id"],
        unique=True,
    )

    op.create_table(
        "testing_generated_suites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("suite_type", testing_suite_type, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "category_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("artifact_key", sa.String(length=512), nullable=True),
        sa.Column("imported_into_eval_set_id", postgresql.UUID(as_uuid=True), nullable=True),
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
    )
    op.create_index(
        "ix_testing_generated_suites_agent_fqn",
        "testing_generated_suites",
        ["agent_fqn"],
        unique=False,
    )
    op.create_index(
        "ix_testing_generated_suites_workspace_suite_type",
        "testing_generated_suites",
        ["workspace_id", "suite_type"],
        unique=False,
    )
    op.create_index(
        "uq_testing_generated_suites_agent_type_version",
        "testing_generated_suites",
        ["workspace_id", "agent_fqn", "suite_type", "version"],
        unique=True,
    )

    op.create_table(
        "testing_adversarial_cases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("suite_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", testing_adversarial_category, nullable=False),
        sa.Column(
            "input_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("expected_behavior", sa.String(length=64), nullable=False),
        sa.Column("generation_prompt_hash", sa.String(length=64), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["suite_id"],
            ["testing_generated_suites.id"],
            name="fk_testing_adversarial_cases_suite_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_testing_adversarial_cases_suite_id",
        "testing_adversarial_cases",
        ["suite_id"],
        unique=False,
    )
    op.create_index(
        "ix_testing_adversarial_cases_category",
        "testing_adversarial_cases",
        ["category"],
        unique=False,
    )

    op.create_table(
        "testing_coordination_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completion_score", sa.Float(), nullable=False),
        sa.Column("coherence_score", sa.Float(), nullable=False),
        sa.Column("goal_achievement_score", sa.Float(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column(
            "per_agent_scores",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "insufficient_members", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
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
    )
    op.create_index(
        "ix_testing_coordination_results_fleet_id",
        "testing_coordination_results",
        ["fleet_id"],
        unique=False,
    )
    op.create_index(
        "ix_testing_coordination_results_workspace_id",
        "testing_coordination_results",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "testing_drift_alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("eval_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("deviation_magnitude", sa.Float(), nullable=False),
        sa.Column("stddevs_from_baseline", sa.Float(), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "ix_testing_drift_alerts_agent_fqn", "testing_drift_alerts", ["agent_fqn"], unique=False
    )
    op.create_index(
        "ix_testing_drift_alerts_eval_set_id", "testing_drift_alerts", ["eval_set_id"], unique=False
    )
    op.create_index(
        "ix_testing_drift_alerts_acknowledged",
        "testing_drift_alerts",
        ["acknowledged"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_testing_drift_alerts_acknowledged", table_name="testing_drift_alerts")
    op.drop_index("ix_testing_drift_alerts_eval_set_id", table_name="testing_drift_alerts")
    op.drop_index("ix_testing_drift_alerts_agent_fqn", table_name="testing_drift_alerts")
    op.drop_table("testing_drift_alerts")

    op.drop_index(
        "ix_testing_coordination_results_workspace_id", table_name="testing_coordination_results"
    )
    op.drop_index(
        "ix_testing_coordination_results_fleet_id", table_name="testing_coordination_results"
    )
    op.drop_table("testing_coordination_results")

    op.drop_index("ix_testing_adversarial_cases_category", table_name="testing_adversarial_cases")
    op.drop_index("ix_testing_adversarial_cases_suite_id", table_name="testing_adversarial_cases")
    op.drop_table("testing_adversarial_cases")

    op.drop_index(
        "uq_testing_generated_suites_agent_type_version",
        table_name="testing_generated_suites",
    )
    op.drop_index(
        "ix_testing_generated_suites_workspace_suite_type", table_name="testing_generated_suites"
    )
    op.drop_index("ix_testing_generated_suites_agent_fqn", table_name="testing_generated_suites")
    op.drop_table("testing_generated_suites")

    op.drop_index("uq_evaluation_human_grades_verdict_id", table_name="evaluation_human_grades")
    op.drop_index("ix_evaluation_human_grades_reviewer_id", table_name="evaluation_human_grades")
    op.drop_table("evaluation_human_grades")

    op.drop_index(
        "ix_evaluation_robustness_runs_agent_fqn", table_name="evaluation_robustness_runs"
    )
    op.drop_index(
        "ix_evaluation_robustness_runs_workspace_status", table_name="evaluation_robustness_runs"
    )
    op.drop_index(
        "ix_evaluation_robustness_runs_eval_set_id", table_name="evaluation_robustness_runs"
    )
    op.drop_table("evaluation_robustness_runs")

    op.drop_index("ix_evaluation_ate_runs_agent_fqn", table_name="evaluation_ate_runs")
    op.drop_index("ix_evaluation_ate_runs_workspace_status", table_name="evaluation_ate_runs")
    op.drop_index("ix_evaluation_ate_runs_ate_config_id", table_name="evaluation_ate_runs")
    op.drop_table("evaluation_ate_runs")

    op.drop_index(
        "uq_evaluation_ate_configs_workspace_name_active",
        table_name="evaluation_ate_configs",
    )
    op.drop_index("ix_evaluation_ate_configs_workspace_id", table_name="evaluation_ate_configs")
    op.drop_table("evaluation_ate_configs")

    op.drop_index("ix_evaluation_ab_experiments_run_b_id", table_name="evaluation_ab_experiments")
    op.drop_index("ix_evaluation_ab_experiments_run_a_id", table_name="evaluation_ab_experiments")
    op.drop_index(
        "ix_evaluation_ab_experiments_workspace_status",
        table_name="evaluation_ab_experiments",
    )
    op.drop_table("evaluation_ab_experiments")

    op.drop_index("uq_evaluation_judge_verdicts_run_case", table_name="evaluation_judge_verdicts")
    op.drop_index("ix_evaluation_judge_verdicts_case_id", table_name="evaluation_judge_verdicts")
    op.drop_index("ix_evaluation_judge_verdicts_run_id", table_name="evaluation_judge_verdicts")
    op.drop_table("evaluation_judge_verdicts")

    op.drop_index("ix_evaluation_runs_agent_fqn", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_workspace_status", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_eval_set_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")

    op.drop_index(
        "uq_evaluation_benchmark_cases_eval_set_position",
        table_name="evaluation_benchmark_cases",
    )
    op.drop_index(
        "ix_evaluation_benchmark_cases_eval_set_id", table_name="evaluation_benchmark_cases"
    )
    op.drop_table("evaluation_benchmark_cases")

    op.drop_index(
        "uq_evaluation_eval_sets_workspace_name_active",
        table_name="evaluation_eval_sets",
    )
    op.drop_index("ix_evaluation_eval_sets_workspace_status", table_name="evaluation_eval_sets")
    op.drop_table("evaluation_eval_sets")

    bind = op.get_bind()
    testing_adversarial_category.drop(bind, checkfirst=True)
    testing_suite_type.drop(bind, checkfirst=True)
    evaluation_review_decision.drop(bind, checkfirst=True)
    evaluation_ate_run_status.drop(bind, checkfirst=True)
    evaluation_experiment_status.drop(bind, checkfirst=True)
    evaluation_verdict_status.drop(bind, checkfirst=True)
    evaluation_run_status.drop(bind, checkfirst=True)
    evaluation_eval_set_status.drop(bind, checkfirst=True)
