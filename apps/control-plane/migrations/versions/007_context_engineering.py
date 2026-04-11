"""Context engineering bounded context schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "007_context_engineering"
down_revision = "006_registry_tables"
branch_labels = None
depends_on = None


ce_profile_assignment_level = postgresql.ENUM(
    "agent",
    "role_type",
    "workspace",
    name="ce_profile_assignment_level",
    create_type=False,
)
ce_ab_test_status = postgresql.ENUM(
    "active",
    "paused",
    "completed",
    name="ce_ab_test_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    ce_profile_assignment_level.create(bind, checkfirst=True)
    ce_ab_test_status.create(bind, checkfirst=True)

    op.create_table(
        "context_engineering_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "source_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "budget_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "compaction_strategies",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "quality_weights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "privacy_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint("workspace_id", "name", name="uq_ce_profile_workspace_name"),
    )
    op.create_index(
        "ix_ce_profile_workspace_default",
        "context_engineering_profiles",
        ["workspace_id", "is_default"],
        unique=False,
    )

    op.create_table(
        "context_profile_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_level", ce_profile_assignment_level, nullable=False),
        sa.Column("agent_fqn", sa.String(length=190), nullable=True),
        sa.Column("role_type", sa.String(length=64), nullable=True),
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
            ["profile_id"],
            ["context_engineering_profiles.id"],
            name="fk_ce_assignment_profile_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_ce_assignment_agent_fqn", "context_profile_assignments", ["agent_fqn"], unique=False
    )
    op.create_index(
        "ix_ce_assignment_role_type", "context_profile_assignments", ["role_type"], unique=False
    )

    op.create_table(
        "context_ab_tests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("control_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_agent_fqn", sa.String(length=190), nullable=True),
        sa.Column("status", ce_ab_test_status, nullable=False, server_default=sa.text("'active'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "control_assembly_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "variant_assembly_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("control_quality_mean", sa.Float(), nullable=True),
        sa.Column("variant_quality_mean", sa.Float(), nullable=True),
        sa.Column("control_token_mean", sa.Float(), nullable=True),
        sa.Column("variant_token_mean", sa.Float(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["control_profile_id"],
            ["context_engineering_profiles.id"],
            name="fk_ce_ab_test_control_profile_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_profile_id"],
            ["context_engineering_profiles.id"],
            name="fk_ce_ab_test_variant_profile_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_ce_ab_test_workspace_status",
        "context_ab_tests",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ce_ab_test_target_agent_fqn",
        "context_ab_tests",
        ["target_agent_fqn"],
        unique=False,
    )

    op.create_table(
        "context_assembly_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=190), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quality_score_pre", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("quality_score_post", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("token_count_pre", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("token_count_post", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "sources_queried",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "sources_available",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "compaction_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "compaction_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "privacy_exclusions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "provenance_chain",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("bundle_storage_key", sa.String(length=512), nullable=True),
        sa.Column("ab_test_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ab_test_group", sa.String(length=32), nullable=True),
        sa.Column(
            "flags",
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
            ["profile_id"],
            ["context_engineering_profiles.id"],
            name="fk_ce_record_profile_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ab_test_id"],
            ["context_ab_tests.id"],
            name="fk_ce_record_ab_test_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_ce_record_execution_step",
        "context_assembly_records",
        ["execution_id", "step_id"],
        unique=False,
    )
    op.create_index(
        "ix_ce_record_agent_fqn_created",
        "context_assembly_records",
        ["agent_fqn", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ce_record_workspace_created",
        "context_assembly_records",
        ["workspace_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "context_drift_alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=190), nullable=False),
        sa.Column("historical_mean", sa.Float(), nullable=False),
        sa.Column("historical_stddev", sa.Float(), nullable=False),
        sa.Column("recent_mean", sa.Float(), nullable=False),
        sa.Column("degradation_delta", sa.Float(), nullable=False),
        sa.Column("analysis_window_days", sa.Integer(), nullable=False),
        sa.Column(
            "suggested_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_ce_drift_alert_agent_fqn", "context_drift_alerts", ["agent_fqn"], unique=False
    )
    op.create_index(
        "ix_ce_drift_alert_workspace_resolved",
        "context_drift_alerts",
        ["workspace_id", "resolved_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ce_drift_alert_workspace_resolved", table_name="context_drift_alerts")
    op.drop_index("ix_ce_drift_alert_agent_fqn", table_name="context_drift_alerts")
    op.drop_table("context_drift_alerts")

    op.drop_index("ix_ce_record_workspace_created", table_name="context_assembly_records")
    op.drop_index("ix_ce_record_agent_fqn_created", table_name="context_assembly_records")
    op.drop_index("ix_ce_record_execution_step", table_name="context_assembly_records")
    op.drop_table("context_assembly_records")

    op.drop_index("ix_ce_ab_test_target_agent_fqn", table_name="context_ab_tests")
    op.drop_index("ix_ce_ab_test_workspace_status", table_name="context_ab_tests")
    op.drop_table("context_ab_tests")

    op.drop_index("ix_ce_assignment_role_type", table_name="context_profile_assignments")
    op.drop_index("ix_ce_assignment_agent_fqn", table_name="context_profile_assignments")
    op.drop_table("context_profile_assignments")

    op.drop_index("ix_ce_profile_workspace_default", table_name="context_engineering_profiles")
    op.drop_table("context_engineering_profiles")

    bind = op.get_bind()
    ce_ab_test_status.drop(bind, checkfirst=True)
    ce_profile_assignment_level.drop(bind, checkfirst=True)
