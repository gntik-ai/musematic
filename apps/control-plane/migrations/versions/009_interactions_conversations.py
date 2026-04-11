"""Interactions and conversations schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "009_interactions_conversations"
down_revision = "008_memory_knowledge"
branch_labels = None
depends_on = None


interactions_interaction_state = postgresql.ENUM(
    "initializing",
    "ready",
    "running",
    "waiting",
    "paused",
    "completed",
    "failed",
    "canceled",
    name="interactions_interaction_state",
    create_type=False,
)
interactions_message_type = postgresql.ENUM(
    "user",
    "agent",
    "system",
    "injection",
    name="interactions_message_type",
    create_type=False,
)
interactions_participant_role = postgresql.ENUM(
    "initiator",
    "responder",
    "observer",
    name="interactions_participant_role",
    create_type=False,
)
interactions_branch_status = postgresql.ENUM(
    "active",
    "merged",
    "abandoned",
    name="interactions_branch_status",
    create_type=False,
)
interactions_attention_urgency = postgresql.ENUM(
    "low",
    "medium",
    "high",
    "critical",
    name="interactions_attention_urgency",
    create_type=False,
)
interactions_attention_status = postgresql.ENUM(
    "pending",
    "acknowledged",
    "resolved",
    "dismissed",
    name="interactions_attention_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    interactions_interaction_state.create(bind, checkfirst=True)
    interactions_message_type.create(bind, checkfirst=True)
    interactions_participant_role.create(bind, checkfirst=True)
    interactions_branch_status.create(bind, checkfirst=True)
    interactions_attention_urgency.create(bind, checkfirst=True)
    interactions_attention_status.create(bind, checkfirst=True)

    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_conversations_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_conversations_workspace_id",
        "conversations",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversations_workspace_created",
        "conversations",
        ["workspace_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "interactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "state",
            interactions_interaction_state,
            nullable=False,
            server_default=sa.text("'initializing'"),
        ),
        sa.Column(
            "state_changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "error_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["conversation_id"],
            ["conversations.id"],
            name="fk_interactions_conversation_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_interactions_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["workspaces_goals.id"],
            name="fk_interactions_goal_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_interactions_conversation_id",
        "interactions",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_interactions_workspace_id",
        "interactions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index("ix_interactions_goal_id", "interactions", ["goal_id"], unique=False)
    op.create_index("ix_interactions_state", "interactions", ["state"], unique=False)
    op.create_index(
        "ix_interactions_conversation_state",
        "interactions",
        ["conversation_id", "state"],
        unique=False,
    )
    op.create_index(
        "ix_interactions_workspace_goal",
        "interactions",
        ["workspace_id", "goal_id"],
        unique=False,
    )

    op.create_table(
        "interaction_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sender_identity", sa.String(length=255), nullable=False),
        sa.Column("message_type", interactions_message_type, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
            ["interaction_id"],
            ["interactions.id"],
            name="fk_interaction_messages_interaction_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_message_id"],
            ["interaction_messages.id"],
            name="fk_interaction_messages_parent_message_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_interaction_messages_interaction_id",
        "interaction_messages",
        ["interaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_interaction_messages_interaction_created",
        "interaction_messages",
        ["interaction_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_interaction_messages_parent",
        "interaction_messages",
        ["parent_message_id"],
        unique=False,
    )

    op.create_table(
        "interaction_participants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity", sa.String(length=255), nullable=False),
        sa.Column("role", interactions_participant_role, nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
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
            ["interaction_id"],
            ["interactions.id"],
            name="fk_interaction_participants_interaction_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "interaction_id",
            "identity",
            name="uq_interaction_participants_identity",
        ),
    )
    op.create_index(
        "ix_interaction_participants_interaction_id",
        "interaction_participants",
        ["interaction_id"],
        unique=False,
    )

    op.create_table(
        "workspace_goal_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_identity", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_workspace_goal_messages_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["workspaces_goals.id"],
            name="fk_workspace_goal_messages_goal_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["interactions.id"],
            name="fk_workspace_goal_messages_interaction_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_workspace_goal_messages_workspace_id",
        "workspace_goal_messages",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_goal_messages_goal_id",
        "workspace_goal_messages",
        ["goal_id"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_goal_messages_goal_created",
        "workspace_goal_messages",
        ["goal_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_goal_messages_workspace_goal",
        "workspace_goal_messages",
        ["workspace_id", "goal_id"],
        unique=False,
    )

    op.create_table(
        "conversation_branches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_interaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_interaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_point_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            interactions_branch_status,
            nullable=False,
            server_default=sa.text("'active'"),
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
            ["conversation_id"],
            ["conversations.id"],
            name="fk_conversation_branches_conversation_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_interaction_id"],
            ["interactions.id"],
            name="fk_conversation_branches_parent_interaction_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["branch_interaction_id"],
            ["interactions.id"],
            name="fk_conversation_branches_branch_interaction_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["branch_point_message_id"],
            ["interaction_messages.id"],
            name="fk_conversation_branches_branch_point_message_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "branch_interaction_id",
            name="uq_conversation_branches_branch_interaction_id",
        ),
    )
    op.create_index(
        "ix_conversation_branches_conversation_id",
        "conversation_branches",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_branches_parent",
        "conversation_branches",
        ["parent_interaction_id"],
        unique=False,
    )

    op.create_table(
        "branch_merge_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merged_by", sa.String(length=255), nullable=False),
        sa.Column(
            "conflict_detected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("conflict_resolution", sa.Text(), nullable=True),
        sa.Column("messages_merged_count", sa.Integer(), nullable=False),
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
            ["branch_id"],
            ["conversation_branches.id"],
            name="fk_branch_merge_records_branch_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_branch_merge_records_branch_id",
        "branch_merge_records",
        ["branch_id"],
        unique=False,
    )

    op.create_table(
        "attention_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_agent_fqn", sa.String(length=255), nullable=False),
        sa.Column("target_identity", sa.String(length=255), nullable=False),
        sa.Column("urgency", interactions_attention_urgency, nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=False),
        sa.Column("related_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            interactions_attention_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_attention_requests_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["related_interaction_id"],
            ["interactions.id"],
            name="fk_attention_requests_related_interaction_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["related_goal_id"],
            ["workspaces_goals.id"],
            name="fk_attention_requests_related_goal_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_attention_requests_workspace_id",
        "attention_requests",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_attention_requests_target_identity",
        "attention_requests",
        ["target_identity"],
        unique=False,
    )
    op.create_index(
        "ix_attention_requests_status",
        "attention_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_attention_requests_target_status",
        "attention_requests",
        ["target_identity", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attention_requests_target_status", table_name="attention_requests")
    op.drop_index("ix_attention_requests_status", table_name="attention_requests")
    op.drop_index("ix_attention_requests_target_identity", table_name="attention_requests")
    op.drop_index("ix_attention_requests_workspace_id", table_name="attention_requests")
    op.drop_table("attention_requests")

    op.drop_index("ix_branch_merge_records_branch_id", table_name="branch_merge_records")
    op.drop_table("branch_merge_records")

    op.drop_index("ix_conversation_branches_parent", table_name="conversation_branches")
    op.drop_index("ix_conversation_branches_conversation_id", table_name="conversation_branches")
    op.drop_table("conversation_branches")

    op.drop_index(
        "ix_workspace_goal_messages_workspace_goal",
        table_name="workspace_goal_messages",
    )
    op.drop_index(
        "ix_workspace_goal_messages_goal_created",
        table_name="workspace_goal_messages",
    )
    op.drop_index("ix_workspace_goal_messages_goal_id", table_name="workspace_goal_messages")
    op.drop_index(
        "ix_workspace_goal_messages_workspace_id",
        table_name="workspace_goal_messages",
    )
    op.drop_table("workspace_goal_messages")

    op.drop_index(
        "ix_interaction_participants_interaction_id",
        table_name="interaction_participants",
    )
    op.drop_table("interaction_participants")

    op.drop_index(
        "ix_interaction_messages_parent",
        table_name="interaction_messages",
    )
    op.drop_index(
        "ix_interaction_messages_interaction_created",
        table_name="interaction_messages",
    )
    op.drop_index(
        "ix_interaction_messages_interaction_id",
        table_name="interaction_messages",
    )
    op.drop_table("interaction_messages")

    op.drop_index("ix_interactions_workspace_goal", table_name="interactions")
    op.drop_index("ix_interactions_conversation_state", table_name="interactions")
    op.drop_index("ix_interactions_state", table_name="interactions")
    op.drop_index("ix_interactions_goal_id", table_name="interactions")
    op.drop_index("ix_interactions_workspace_id", table_name="interactions")
    op.drop_index("ix_interactions_conversation_id", table_name="interactions")
    op.drop_table("interactions")

    op.drop_index("ix_conversations_workspace_created", table_name="conversations")
    op.drop_index("ix_conversations_workspace_id", table_name="conversations")
    op.drop_table("conversations")

    interactions_attention_status.drop(op.get_bind(), checkfirst=True)
    interactions_attention_urgency.drop(op.get_bind(), checkfirst=True)
    interactions_branch_status.drop(op.get_bind(), checkfirst=True)
    interactions_participant_role.drop(op.get_bind(), checkfirst=True)
    interactions_message_type.drop(op.get_bind(), checkfirst=True)
    interactions_interaction_state.drop(op.get_bind(), checkfirst=True)
