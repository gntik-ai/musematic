"""Add adaptation lifecycle, proficiency, and correlation schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "055_adaptation_context_levels"
down_revision = "054_trajectory_evaluation_schema"
branch_labels = None
depends_on = None

proficiency_level = postgresql.ENUM(
    "undetermined",
    "novice",
    "competent",
    "advanced",
    "expert",
    name="proficiency_level",
    create_type=False,
    _create_events=False,
)
outcome_classification = postgresql.ENUM(
    "improved",
    "no_change",
    "regressed",
    "inconclusive",
    name="outcome_classification",
    create_type=False,
    _create_events=False,
)
correlation_classification = postgresql.ENUM(
    "strong_positive",
    "moderate_positive",
    "weak",
    "moderate_negative",
    "strong_negative",
    "inconclusive",
    name="correlation_classification",
    create_type=False,
    _create_events=False,
)
snapshot_type = postgresql.ENUM(
    "pre_apply",
    "post_apply",
    name="snapshot_type",
    create_type=False,
    _create_events=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    proficiency_level.create(bind, checkfirst=True)
    outcome_classification.create(bind, checkfirst=True)
    correlation_classification.create(bind, checkfirst=True)
    snapshot_type.create(bind, checkfirst=True)

    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("expected_improvement", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("pre_apply_snapshot_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("applied_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("rolled_back_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("rollback_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("revoke_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "agentops_adaptation_proposals",
        sa.Column("signal_source", sa.String(length=32), nullable=True),
    )

    op.create_index(
        "uq_agentops_adaptation_one_open_per_agent",
        "agentops_adaptation_proposals",
        ["workspace_id", "agent_fqn"],
        unique=True,
        postgresql_where=sa.text("status IN ('proposed', 'approved', 'applied')"),
    )
    op.create_index(
        "ix_agentops_adaptation_expires_at",
        "agentops_adaptation_proposals",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    op.create_index(
        "ix_agentops_adaptation_applied_at",
        "agentops_adaptation_proposals",
        ["applied_at"],
        unique=False,
        postgresql_where=sa.text("applied_at IS NOT NULL"),
    )

    op.create_table(
        "agentops_adaptation_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_type", snapshot_type, nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
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
            ["proposal_id"],
            ["agentops_adaptation_proposals.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_agentops_adaptation_snapshots_proposal",
        "agentops_adaptation_snapshots",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        "ix_agentops_adaptation_snapshots_retention",
        "agentops_adaptation_snapshots",
        ["retention_expires_at"],
        unique=False,
    )

    op.create_table(
        "agentops_adaptation_outcomes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "expected_delta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "observed_delta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("classification", outcome_classification, nullable=False),
        sa.Column("variance_annotation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "measured_at",
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
            ["proposal_id"],
            ["agentops_adaptation_proposals.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_agentops_adaptation_outcomes_proposal",
        "agentops_adaptation_outcomes",
        ["proposal_id"],
        unique=True,
    )

    op.create_table(
        "agentops_proficiency_assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("level", proficiency_level, nullable=False),
        sa.Column(
            "dimension_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("trigger", sa.String(length=32), nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column(
            "assessed_at",
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
    )
    op.create_index(
        "ix_agentops_proficiency_agent_workspace",
        "agentops_proficiency_assessments",
        ["agent_fqn", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_agentops_proficiency_level",
        "agentops_proficiency_assessments",
        ["level"],
        unique=False,
    )

    op.create_table(
        "context_engineering_correlation_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=190), nullable=False),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("performance_metric", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coefficient", sa.Float(), nullable=True),
        sa.Column("classification", correlation_classification, nullable=False),
        sa.Column("data_point_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
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
        "uq_ce_correlation_window_metric",
        "context_engineering_correlation_results",
        [
            "workspace_id",
            "agent_fqn",
            "dimension",
            "performance_metric",
            "window_start",
            "window_end",
        ],
        unique=True,
    )
    op.create_index(
        "ix_ce_correlation_agent_window",
        "context_engineering_correlation_results",
        ["agent_fqn", "window_start", "window_end"],
        unique=False,
    )
    op.create_index(
        "ix_ce_correlation_classification",
        "context_engineering_correlation_results",
        ["classification"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ce_correlation_classification", table_name="context_engineering_correlation_results")
    op.drop_index("ix_ce_correlation_agent_window", table_name="context_engineering_correlation_results")
    op.drop_index("uq_ce_correlation_window_metric", table_name="context_engineering_correlation_results")
    op.drop_table("context_engineering_correlation_results")

    op.drop_index("ix_agentops_proficiency_level", table_name="agentops_proficiency_assessments")
    op.drop_index("ix_agentops_proficiency_agent_workspace", table_name="agentops_proficiency_assessments")
    op.drop_table("agentops_proficiency_assessments")

    op.drop_index("uq_agentops_adaptation_outcomes_proposal", table_name="agentops_adaptation_outcomes")
    op.drop_table("agentops_adaptation_outcomes")

    op.drop_index("ix_agentops_adaptation_snapshots_retention", table_name="agentops_adaptation_snapshots")
    op.drop_index("ix_agentops_adaptation_snapshots_proposal", table_name="agentops_adaptation_snapshots")
    op.drop_table("agentops_adaptation_snapshots")

    op.drop_index("ix_agentops_adaptation_applied_at", table_name="agentops_adaptation_proposals")
    op.drop_index("ix_agentops_adaptation_expires_at", table_name="agentops_adaptation_proposals")
    op.drop_index("uq_agentops_adaptation_one_open_per_agent", table_name="agentops_adaptation_proposals")

    for column in [
        "signal_source",
        "revoke_reason",
        "revoked_by",
        "revoked_at",
        "expires_at",
        "rollback_reason",
        "rolled_back_by",
        "rolled_back_at",
        "applied_by",
        "applied_at",
        "pre_apply_snapshot_key",
        "expected_improvement",
    ]:
        op.drop_column("agentops_adaptation_proposals", column)

    bind = op.get_bind()
    snapshot_type.drop(bind, checkfirst=True)
    correlation_classification.drop(bind, checkfirst=True)
    outcome_classification.drop(bind, checkfirst=True)
    proficiency_level.drop(bind, checkfirst=True)
