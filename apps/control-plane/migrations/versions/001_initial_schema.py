"""Initial PostgreSQL schema foundation."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'pending_verification'"),
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
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_status", "users", ["status"], unique=False)
    op.create_foreign_key(
        "fk_users_deleted_by_users",
        "users",
        "users",
        ["deleted_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_users_created_by_users",
        "users",
        "users",
        ["created_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_users_updated_by_users",
        "users",
        "users",
        ["updated_by"],
        ["id"],
    )

    op.create_table(
        "workspaces",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
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
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_workspaces_owner_id_users"),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["users.id"], name="fk_workspaces_deleted_by_users"
        ),
    )
    op.create_index("ix_workspaces_owner_id", "workspaces", ["owner_id"], unique=False)

    op.create_table(
        "memberships",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'member'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name="fk_memberships_workspace_id_workspaces"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_memberships_user_id_users"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_memberships_workspace_user"),
    )
    op.create_index("ix_memberships_workspace_id", "memberships", ["workspace_id"], unique=False)
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"], unique=False)

    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(length=50), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.String(length=100), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_audit_events_workspace_occurred_at",
        "audit_events",
        ["workspace_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_actor_occurred_at",
        "audit_events",
        ["actor_id", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "execution_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("step_id", sa.String(length=255), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "correlation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_execution_events_execution_occurred_at",
        "execution_events",
        ["execution_id", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "agent_namespaces",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name="fk_agent_namespaces_workspace_id_workspaces"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_agent_namespaces_created_by_users"
        ),
        sa.UniqueConstraint("name", name="uq_agent_namespaces_name"),
    )
    op.create_index(
        "ix_agent_namespaces_workspace_id",
        "agent_namespaces",
        ["workspace_id"],
        unique=False,
    )

    op.execute(
        "CREATE RULE audit_no_update AS ON UPDATE TO audit_events DO INSTEAD NOTHING"
    )
    op.execute(
        "CREATE RULE audit_no_delete AS ON DELETE TO audit_events DO INSTEAD NOTHING"
    )
    op.execute(
        "CREATE RULE exec_events_no_update AS ON UPDATE TO execution_events DO INSTEAD NOTHING"
    )
    op.execute(
        "CREATE RULE exec_events_no_delete AS ON DELETE TO execution_events DO INSTEAD NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP RULE IF EXISTS exec_events_no_delete ON execution_events")
    op.execute("DROP RULE IF EXISTS exec_events_no_update ON execution_events")
    op.execute("DROP RULE IF EXISTS audit_no_delete ON audit_events")
    op.execute("DROP RULE IF EXISTS audit_no_update ON audit_events")

    op.drop_index("ix_agent_namespaces_workspace_id", table_name="agent_namespaces")
    op.drop_table("agent_namespaces")

    op.drop_index("ix_execution_events_execution_occurred_at", table_name="execution_events")
    op.drop_table("execution_events")

    op.drop_index("ix_audit_events_actor_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_workspace_occurred_at", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_workspace_id", table_name="memberships")
    op.drop_table("memberships")

    op.drop_index("ix_workspaces_owner_id", table_name="workspaces")
    op.drop_table("workspaces")

    op.drop_index("ix_users_status", table_name="users")
    op.drop_constraint("fk_users_updated_by_users", "users", type_="foreignkey")
    op.drop_constraint("fk_users_created_by_users", "users", type_="foreignkey")
    op.drop_constraint("fk_users_deleted_by_users", "users", type_="foreignkey")
    op.drop_table("users")

