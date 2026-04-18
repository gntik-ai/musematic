"""Add workspace goal lifecycle state and decision rationale tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "046_workspace_goal_response"
down_revision = "045_oauth_providers_and_links"
branch_labels = None
depends_on = None

workspacegoalstate = postgresql.ENUM(
    "ready",
    "working",
    "complete",
    name="workspacegoalstate",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    workspacegoalstate.create(bind, checkfirst=True)

    op.add_column(
        "workspaces_goals",
        sa.Column(
            "state",
            workspacegoalstate,
            nullable=False,
            server_default=sa.text("'ready'"),
        ),
    )
    op.add_column(
        "workspaces_goals",
        sa.Column("auto_complete_timeout_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "workspaces_goals",
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_workspaces_goals_state",
        "workspaces_goals",
        ["state"],
        unique=False,
    )
    op.create_index(
        "ix_workspaces_goals_auto_complete",
        "workspaces_goals",
        ["state", "last_message_at"],
        unique=False,
        postgresql_where=sa.text("state = 'working' AND auto_complete_timeout_seconds IS NOT NULL"),
    )

    op.create_table(
        "workspaces_agent_decision_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
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
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.Text(), nullable=False),
        sa.Column(
            "response_decision_strategy",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'llm_relevance'"),
        ),
        sa.Column(
            "response_decision_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "subscribed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("workspace_id", "agent_fqn", name="uq_wksp_agent_decision_cfg"),
    )
    op.create_index(
        "ix_wksp_agent_decision_cfg_workspace",
        "workspaces_agent_decision_configs",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "workspace_goal_decision_rationales",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.Text(), nullable=False),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=8), nullable=False),
        sa.Column("score", sa.Float(precision=24), nullable=True),
        sa.Column(
            "matched_terms",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "rationale",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["workspaces_goals.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["workspace_goal_messages.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("message_id", "agent_fqn", name="uq_wgdr_message_agent"),
    )
    op.create_index(
        "ix_wgdr_goal",
        "workspace_goal_decision_rationales",
        ["goal_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_wgdr_workspace",
        "workspace_goal_decision_rationales",
        ["workspace_id", "agent_fqn"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_wgdr_workspace", table_name="workspace_goal_decision_rationales")
    op.drop_index("ix_wgdr_goal", table_name="workspace_goal_decision_rationales")
    op.drop_table("workspace_goal_decision_rationales")

    op.drop_index(
        "ix_wksp_agent_decision_cfg_workspace",
        table_name="workspaces_agent_decision_configs",
    )
    op.drop_table("workspaces_agent_decision_configs")

    op.drop_index("ix_workspaces_goals_auto_complete", table_name="workspaces_goals")
    op.drop_index("ix_workspaces_goals_state", table_name="workspaces_goals")
    op.drop_column("workspaces_goals", "last_message_at")
    op.drop_column("workspaces_goals", "auto_complete_timeout_seconds")
    op.drop_column("workspaces_goals", "state")

    bind = op.get_bind()
    workspacegoalstate.drop(bind, checkfirst=True)
