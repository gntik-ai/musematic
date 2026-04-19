"""Add reprioritization triggers and checkpoint rollback support."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "050_reprioritization_ckpts"
down_revision = "049_agent_contracts_and_certs"
branch_labels = None
depends_on = None


rollback_action_status = postgresql.ENUM(
    "completed",
    "failed",
    name="execution_rollback_action_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    rollback_action_status.create(bind, checkfirst=True)

    op.execute("ALTER TYPE execution_status ADD VALUE IF NOT EXISTS 'paused'")
    op.execute("ALTER TYPE execution_status ADD VALUE IF NOT EXISTS 'rolled_back'")
    op.execute("ALTER TYPE execution_status ADD VALUE IF NOT EXISTS 'rollback_failed'")
    op.execute("ALTER TYPE execution_event_type ADD VALUE IF NOT EXISTS 'rolled_back'")

    op.add_column(
        "execution_checkpoints",
        sa.Column("checkpoint_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "execution_checkpoints",
        sa.Column(
            "current_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "execution_checkpoints",
        sa.Column(
            "accumulated_costs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "execution_checkpoints",
        sa.Column(
            "superseded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "execution_checkpoints",
        sa.Column(
            "policy_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{\"type\":\"before_tool_invocations\"}'::jsonb"),
        ),
    )

    op.execute(
        """
        WITH numbered AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY execution_id
                    ORDER BY created_at ASC, id ASC
                ) AS checkpoint_number
            FROM execution_checkpoints
        )
        UPDATE execution_checkpoints AS checkpoints
        SET checkpoint_number = numbered.checkpoint_number
        FROM numbered
        WHERE checkpoints.id = numbered.id
        """
    )
    op.alter_column("execution_checkpoints", "checkpoint_number", nullable=False)
    op.create_unique_constraint(
        "uq_execution_checkpoints_execution_checkpoint_number",
        "execution_checkpoints",
        ["execution_id", "checkpoint_number"],
    )
    op.create_index(
        "ix_execution_checkpoints_execution_superseded",
        "execution_checkpoints",
        ["execution_id", "superseded"],
        unique=False,
    )

    op.add_column(
        "executions",
        sa.Column(
            "checkpoint_policy_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "workflow_versions",
        sa.Column(
            "checkpoint_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.create_table(
        "reprioritization_triggers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column(
            "condition_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("priority_rank", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_reprioritization_triggers_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_reprioritization_triggers_workspace_id",
        "reprioritization_triggers",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_reprioritization_triggers_workspace_enabled_priority",
        "reprioritization_triggers",
        ["workspace_id", "enabled", "priority_rank"],
        unique=False,
    )

    op.create_table(
        "execution_rollback_actions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_checkpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_checkpoint_number", sa.Integer(), nullable=False),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "cost_delta_reversed",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", rollback_action_status, nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
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
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_rollback_actions_execution_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_checkpoint_id"],
            ["execution_checkpoints.id"],
            name="fk_execution_rollback_actions_target_checkpoint_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_execution_rollback_actions_execution_id",
        "execution_rollback_actions",
        ["execution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_execution_rollback_actions_execution_id",
        table_name="execution_rollback_actions",
    )
    op.drop_table("execution_rollback_actions")

    op.drop_index(
        "ix_reprioritization_triggers_workspace_enabled_priority",
        table_name="reprioritization_triggers",
    )
    op.drop_index(
        "ix_reprioritization_triggers_workspace_id",
        table_name="reprioritization_triggers",
    )
    op.drop_table("reprioritization_triggers")

    op.drop_column("workflow_versions", "checkpoint_policy")
    op.drop_column("executions", "checkpoint_policy_snapshot")

    op.drop_index(
        "ix_execution_checkpoints_execution_superseded",
        table_name="execution_checkpoints",
    )
    op.drop_constraint(
        "uq_execution_checkpoints_execution_checkpoint_number",
        "execution_checkpoints",
        type_="unique",
    )
    op.drop_column("execution_checkpoints", "policy_snapshot")
    op.drop_column("execution_checkpoints", "superseded")
    op.drop_column("execution_checkpoints", "accumulated_costs")
    op.drop_column("execution_checkpoints", "current_context")
    op.drop_column("execution_checkpoints", "checkpoint_number")

    rollback_action_status.drop(bind=op.get_bind(), checkfirst=True)
