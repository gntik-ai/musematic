"""Workspaces bounded context schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "004_workspaces_tables"
down_revision = "003_accounts_tables"
branch_labels = None
depends_on = None


workspaces_workspace_status = postgresql.ENUM(
    "active",
    "archived",
    "deleted",
    name="workspaces_workspace_status",
    create_type=False,
)
workspaces_workspace_role = postgresql.ENUM(
    "owner",
    "admin",
    "member",
    "viewer",
    name="workspaces_workspace_role",
    create_type=False,
)
workspaces_goal_status = postgresql.ENUM(
    "open",
    "in_progress",
    "completed",
    "cancelled",
    name="workspaces_goal_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    workspaces_workspace_status.create(bind, checkfirst=True)
    workspaces_workspace_role.create(bind, checkfirst=True)
    workspaces_goal_status.create(bind, checkfirst=True)

    op.add_column(
        "accounts_users",
        sa.Column(
            "max_workspaces",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_table(
        "workspaces_workspaces",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            workspaces_workspace_status,
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_workspaces_owner_id", "workspaces_workspaces", ["owner_id"], unique=False)
    op.create_index(
        "ix_workspaces_owner_name_status",
        "workspaces_workspaces",
        ["owner_id", "name", "status"],
        unique=True,
        postgresql_where=sa.text("status != 'deleted'"),
    )

    op.create_table(
        "workspaces_memberships",
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
            workspaces_workspace_role,
            nullable=False,
            server_default=sa.text("'member'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_workspaces_memberships_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_memberships_user_id", "workspaces_memberships", ["user_id"], unique=False)
    op.create_index(
        "uq_workspace_user",
        "workspaces_memberships",
        ["workspace_id", "user_id"],
        unique=True,
    )

    op.create_table(
        "workspaces_goals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            workspaces_goal_status,
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("gid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_workspaces_goals_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("uq_goal_gid", "workspaces_goals", ["gid"], unique=True)
    op.create_index("ix_goals_workspace_id", "workspaces_goals", ["workspace_id"], unique=False)
    op.create_index(
        "ix_goals_workspace_status",
        "workspaces_goals",
        ["workspace_id", "status"],
        unique=False,
    )

    op.create_table(
        "workspaces_settings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "subscribed_agents",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "subscribed_fleets",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "subscribed_policies",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "subscribed_connectors",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_workspaces_settings_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("uq_settings_workspace", "workspaces_settings", ["workspace_id"], unique=True)

    op.create_table(
        "workspaces_visibility_grants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "visibility_agents",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "visibility_tools",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            name="fk_workspaces_visibility_workspace_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_visibility_workspace",
        "workspaces_visibility_grants",
        ["workspace_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_visibility_workspace", table_name="workspaces_visibility_grants")
    op.drop_table("workspaces_visibility_grants")

    op.drop_index("uq_settings_workspace", table_name="workspaces_settings")
    op.drop_table("workspaces_settings")

    op.drop_index("ix_goals_workspace_status", table_name="workspaces_goals")
    op.drop_index("ix_goals_workspace_id", table_name="workspaces_goals")
    op.drop_index("uq_goal_gid", table_name="workspaces_goals")
    op.drop_table("workspaces_goals")

    op.drop_index("uq_workspace_user", table_name="workspaces_memberships")
    op.drop_index("ix_memberships_user_id", table_name="workspaces_memberships")
    op.drop_table("workspaces_memberships")

    op.drop_index("ix_workspaces_owner_name_status", table_name="workspaces_workspaces")
    op.drop_index("ix_workspaces_owner_id", table_name="workspaces_workspaces")
    op.drop_table("workspaces_workspaces")

    op.drop_column("accounts_users", "max_workspaces")

    bind = op.get_bind()
    workspaces_goal_status.drop(bind, checkfirst=True)
    workspaces_workspace_role.drop(bind, checkfirst=True)
    workspaces_workspace_status.drop(bind, checkfirst=True)
