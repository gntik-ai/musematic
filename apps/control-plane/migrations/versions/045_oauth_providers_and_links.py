"""Add OAuth provider configuration, links, and audit tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "045_oauth_providers_and_links"
down_revision = "044_ibor_and_decommission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_providers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("client_id", sa.String(length=256), nullable=False),
        sa.Column("client_secret_ref", sa.String(length=256), nullable=False),
        sa.Column("redirect_uri", sa.String(length=512), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "domain_restrictions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "org_restrictions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "group_role_mapping",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "default_role",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'member'"),
        ),
        sa.Column(
            "require_mfa",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
        sa.UniqueConstraint("provider_type", name="uq_oauth_providers_type"),
    )
    op.create_index(
        "idx_oauth_providers_enabled",
        "oauth_providers",
        ["enabled", "provider_type"],
        unique=False,
    )

    op.create_table(
        "oauth_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=256), nullable=False),
        sa.Column("external_email", sa.String(length=256), nullable=True),
        sa.Column("external_name", sa.String(length=256), nullable=True),
        sa.Column("external_avatar_url", sa.String(length=512), nullable=True),
        sa.Column(
            "external_groups",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["oauth_providers.id"]),
        sa.UniqueConstraint("provider_id", "external_id", name="uq_oauth_links_provider_ext"),
        sa.UniqueConstraint("user_id", "provider_id", name="uq_oauth_links_user_provider"),
    )
    op.create_index("idx_oauth_links_user", "oauth_links", ["user_id"], unique=False)

    op.create_table(
        "oauth_audit_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider_type", sa.String(length=32), nullable=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(length=256), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.String(length=256), nullable=True),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("changed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["oauth_providers.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index(
        "idx_oauth_audit_user",
        "oauth_audit_entries",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_oauth_audit_provider",
        "oauth_audit_entries",
        ["provider_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_oauth_audit_provider", table_name="oauth_audit_entries")
    op.drop_index("idx_oauth_audit_user", table_name="oauth_audit_entries")
    op.drop_table("oauth_audit_entries")
    op.drop_index("idx_oauth_links_user", table_name="oauth_links")
    op.drop_table("oauth_links")
    op.drop_index("idx_oauth_providers_enabled", table_name="oauth_providers")
    op.drop_table("oauth_providers")
