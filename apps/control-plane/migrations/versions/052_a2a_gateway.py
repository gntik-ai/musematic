"""Add A2A gateway tables and enums."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "052_a2a_gateway"
down_revision = "051_reasoning_trace_export"
branch_labels = None
depends_on = None


a2a_task_state = postgresql.ENUM(
    "submitted",
    "working",
    "input_required",
    "completed",
    "failed",
    "cancelled",
    "cancellation_pending",
    name="a2a_task_state",
    create_type=False,
)
a2a_direction = postgresql.ENUM(
    "inbound",
    "outbound",
    name="a2a_direction",
    create_type=False,
)


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'a2a_task_state') THEN
                CREATE TYPE a2a_task_state AS ENUM (
                    'submitted',
                    'working',
                    'input_required',
                    'completed',
                    'failed',
                    'cancelled',
                    'cancellation_pending'
                );
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'a2a_direction') THEN
                CREATE TYPE a2a_direction AS ENUM ('inbound', 'outbound');
            END IF;
        END
        $$;
        """
    )

    if not _table_exists("a2a_external_endpoints"):
        op.create_table(
            "a2a_external_endpoints",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "workspace_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("endpoint_url", sa.String(length=2048), nullable=False),
            sa.Column("agent_card_url", sa.String(length=2048), nullable=False),
            sa.Column("auth_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("card_ttl_seconds", sa.Integer(), nullable=False, server_default=sa.text("3600")),
            sa.Column("cached_agent_card", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("card_cached_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("card_is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("declared_version", sa.String(length=64), nullable=True),
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")
            ),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
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
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces_workspaces.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("workspace_id", "endpoint_url", name="uq_a2a_endpoints_workspace_url"),
        )
    if not _index_exists("a2a_external_endpoints", "ix_a2a_endpoints_workspace"):
        op.create_index(
            "ix_a2a_endpoints_workspace", "a2a_external_endpoints", ["workspace_id"], unique=False
        )
    if not _index_exists("a2a_external_endpoints", "ix_a2a_endpoints_status"):
        op.create_index("ix_a2a_endpoints_status", "a2a_external_endpoints", ["status"], unique=False)

    if not _table_exists("a2a_tasks"):
        op.create_table(
            "a2a_tasks",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("task_id", sa.String(length=128), nullable=False),
            sa.Column("direction", a2a_direction, nullable=False),
            sa.Column(
                "a2a_state", a2a_task_state, nullable=False, server_default=sa.text("'submitted'")
            ),
            sa.Column("agent_fqn", sa.String(length=512), nullable=False),
            sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("external_endpoint_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("protocol_version", sa.String(length=16), nullable=False),
            sa.Column("submitted_message", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("last_event_id", sa.String(length=128), nullable=True),
            sa.Column("idle_timeout_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True),
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
                ["workspace_id"], ["workspaces_workspaces.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["external_endpoint_id"], ["a2a_external_endpoints.id"], ondelete="SET NULL"
            ),
            sa.UniqueConstraint("task_id", name="uq_a2a_tasks_task_id"),
        )
    if not _index_exists("a2a_tasks", "ix_a2a_tasks_state"):
        op.create_index("ix_a2a_tasks_state", "a2a_tasks", ["a2a_state"], unique=False)
    if not _index_exists("a2a_tasks", "ix_a2a_tasks_workspace"):
        op.create_index("ix_a2a_tasks_workspace", "a2a_tasks", ["workspace_id"], unique=False)
    if not _index_exists("a2a_tasks", "ix_a2a_tasks_principal"):
        op.create_index("ix_a2a_tasks_principal", "a2a_tasks", ["principal_id"], unique=False)
    if not _index_exists("a2a_tasks", "ix_a2a_tasks_interaction"):
        op.create_index("ix_a2a_tasks_interaction", "a2a_tasks", ["interaction_id"], unique=False)

    if not _table_exists("a2a_audit_records"):
        op.create_table(
            "a2a_audit_records",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("direction", a2a_direction, nullable=False),
            sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("agent_fqn", sa.String(length=512), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("result", sa.String(length=32), nullable=False),
            sa.Column("policy_decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(["task_id"], ["a2a_tasks.id"], ondelete="SET NULL"),
        )
    if not _index_exists("a2a_audit_records", "ix_a2a_audit_task"):
        op.create_index("ix_a2a_audit_task", "a2a_audit_records", ["task_id"], unique=False)
    if not _index_exists("a2a_audit_records", "ix_a2a_audit_occurred_at"):
        op.create_index("ix_a2a_audit_occurred_at", "a2a_audit_records", ["occurred_at"], unique=False)
    if not _index_exists("a2a_audit_records", "ix_a2a_audit_workspace"):
        op.create_index("ix_a2a_audit_workspace", "a2a_audit_records", ["workspace_id"], unique=False)


def downgrade() -> None:
    if _table_exists("a2a_audit_records") and _index_exists("a2a_audit_records", "ix_a2a_audit_workspace"):
        op.drop_index("ix_a2a_audit_workspace", table_name="a2a_audit_records")
    if _table_exists("a2a_audit_records") and _index_exists("a2a_audit_records", "ix_a2a_audit_occurred_at"):
        op.drop_index("ix_a2a_audit_occurred_at", table_name="a2a_audit_records")
    if _table_exists("a2a_audit_records") and _index_exists("a2a_audit_records", "ix_a2a_audit_task"):
        op.drop_index("ix_a2a_audit_task", table_name="a2a_audit_records")
    if _table_exists("a2a_audit_records"):
        op.drop_table("a2a_audit_records")

    if _table_exists("a2a_tasks") and _index_exists("a2a_tasks", "ix_a2a_tasks_interaction"):
        op.drop_index("ix_a2a_tasks_interaction", table_name="a2a_tasks")
    if _table_exists("a2a_tasks") and _index_exists("a2a_tasks", "ix_a2a_tasks_principal"):
        op.drop_index("ix_a2a_tasks_principal", table_name="a2a_tasks")
    if _table_exists("a2a_tasks") and _index_exists("a2a_tasks", "ix_a2a_tasks_workspace"):
        op.drop_index("ix_a2a_tasks_workspace", table_name="a2a_tasks")
    if _table_exists("a2a_tasks") and _index_exists("a2a_tasks", "ix_a2a_tasks_state"):
        op.drop_index("ix_a2a_tasks_state", table_name="a2a_tasks")
    if _table_exists("a2a_tasks"):
        op.drop_table("a2a_tasks")

    if _table_exists("a2a_external_endpoints") and _index_exists("a2a_external_endpoints", "ix_a2a_endpoints_status"):
        op.drop_index("ix_a2a_endpoints_status", table_name="a2a_external_endpoints")
    if _table_exists("a2a_external_endpoints") and _index_exists("a2a_external_endpoints", "ix_a2a_endpoints_workspace"):
        op.drop_index("ix_a2a_endpoints_workspace", table_name="a2a_external_endpoints")
    if _table_exists("a2a_external_endpoints"):
        op.drop_table("a2a_external_endpoints")

    op.execute("DROP TYPE IF EXISTS a2a_task_state")
    op.execute("DROP TYPE IF EXISTS a2a_direction")
