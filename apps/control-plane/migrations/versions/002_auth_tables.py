"""Auth bounded context schema."""

from __future__ import annotations

from itertools import product

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002_auth_tables"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def _permission_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = [
        {
            "role": "superadmin",
            "resource_type": "*",
            "action": "*",
            "scope": "global",
        }
    ]

    seeded_roles = (
        ("platform_admin", ("workspace", "user", "agent", "connector"), ("read", "write", "delete", "admin"), "global"),
        ("workspace_owner", ("workspace", "agent", "workflow", "connector"), ("read", "write", "delete", "admin"), "workspace"),
        ("workspace_admin", ("agent", "workflow", "connector", "interaction"), ("read", "write", "delete"), "workspace"),
        ("creator", ("agent", "workflow", "prompt", "evaluation"), ("read", "write"), "workspace"),
        ("operator", ("agent", "workflow", "execution", "fleet"), ("read", "write"), "workspace"),
        ("viewer", ("agent", "workflow", "execution", "analytics"), ("read",), "workspace"),
        ("auditor", ("audit", "analytics", "trust", "execution"), ("read",), "workspace"),
        ("agent", ("execution", "memory", "tool"), ("read", "write"), "own"),
    )

    for role, resources, actions, scope in seeded_roles:
        rows.extend(
            {
                "role": role,
                "resource_type": resource_type,
                "action": action,
                "scope": scope,
            }
            for resource_type, action in product(resources, actions)
        )
    return rows


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_credentials_user_id_users"),
        sa.UniqueConstraint("user_id", name="uq_user_credentials_user_id"),
        sa.UniqueConstraint("email", name="uq_user_credentials_email"),
    )
    op.create_index(
        "ix_user_credentials_user_id",
        "user_credentials",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_credentials_email",
        "user_credentials",
        ["email"],
        unique=False,
    )

    op.create_table(
        "mfa_enrollments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "method",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'totp'"),
        ),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "recovery_codes_hash",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"],
            ["user_credentials.user_id"],
            name="fk_mfa_enrollments_user_id_user_credentials",
        ),
    )
    op.create_index("ix_mfa_enrollments_user_id", "mfa_enrollments", ["user_id"], unique=False)

    op.create_table(
        "auth_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column(
            "user_agent",
            sa.String(length=512),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_auth_attempts_user_id_users"),
    )
    op.create_index("ix_auth_attempts_user_id", "auth_attempts", ["user_id"], unique=False)
    op.create_index("ix_auth_attempts_email", "auth_attempts", ["email"], unique=False)

    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"],
            ["user_credentials.user_id"],
            name="fk_password_reset_tokens_user_id_user_credentials",
        ),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "service_account_credentials",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("service_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("api_key_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "role",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'service_account'"),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["workspaces.id"],
            name="fk_service_account_credentials_workspace_id_workspaces",
        ),
        sa.UniqueConstraint(
            "service_account_id",
            name="uq_service_account_credentials_service_account_id",
        ),
    )
    op.create_index(
        "ix_service_account_credentials_service_account_id",
        "service_account_credentials",
        ["service_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_account_credentials_workspace_id",
        "service_account_credentials",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_roles_user_id_users"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_user_roles_workspace_id_workspaces",
        ),
        sa.UniqueConstraint("user_id", "role", "workspace_id", name="uq_user_role_workspace"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"], unique=False)
    op.create_index("ix_user_roles_workspace_id", "user_roles", ["workspace_id"], unique=False)

    op.create_table(
        "role_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column(
            "scope",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'workspace'"),
        ),
        sa.UniqueConstraint("role", "resource_type", "action", name="uq_role_resource_action"),
    )
    op.create_index("ix_role_permissions_role", "role_permissions", ["role"], unique=False)

    role_permissions = sa.table(
        "role_permissions",
        sa.column("role", sa.String(length=50)),
        sa.column("resource_type", sa.String(length=100)),
        sa.column("action", sa.String(length=50)),
        sa.column("scope", sa.String(length=20)),
    )
    op.bulk_insert(role_permissions, _permission_rows())


def downgrade() -> None:
    op.drop_index("ix_role_permissions_role", table_name="role_permissions")
    op.drop_table("role_permissions")

    op.drop_index("ix_user_roles_workspace_id", table_name="user_roles")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_index(
        "ix_service_account_credentials_workspace_id",
        table_name="service_account_credentials",
    )
    op.drop_index(
        "ix_service_account_credentials_service_account_id",
        table_name="service_account_credentials",
    )
    op.drop_table("service_account_credentials")

    op.drop_index(
        "ix_password_reset_tokens_user_id",
        table_name="password_reset_tokens",
    )
    op.drop_table("password_reset_tokens")

    op.drop_index("ix_auth_attempts_email", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_user_id", table_name="auth_attempts")
    op.drop_table("auth_attempts")

    op.drop_index("ix_mfa_enrollments_user_id", table_name="mfa_enrollments")
    op.drop_table("mfa_enrollments")

    op.drop_index("ix_user_credentials_email", table_name="user_credentials")
    op.drop_index("ix_user_credentials_user_id", table_name="user_credentials")
    op.drop_table("user_credentials")
