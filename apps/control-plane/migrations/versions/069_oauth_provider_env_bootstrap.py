"""Add OAuth provider env bootstrap metadata.

Revision ID: 069_oauth_provider_env_bootstrap
Revises: 068_pending_profile_completion
Create Date: 2026-04-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "069_oauth_provider_env_bootstrap"
down_revision: str | None = "068_pending_profile_completion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

oauth_provider_source = postgresql.ENUM(
    "env_var",
    "manual",
    "imported",
    name="oauth_provider_source",
)


def upgrade() -> None:
    oauth_provider_source.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "oauth_providers",
        sa.Column(
            "source",
            oauth_provider_source,
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )
    op.add_column(
        "oauth_providers",
        sa.Column("last_edited_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "oauth_providers",
        sa.Column("last_edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "oauth_providers",
        sa.Column("last_successful_auth_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_oauth_providers_last_edited_by_users",
        "oauth_providers",
        "users",
        ["last_edited_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "oauth_provider_rate_limits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("per_ip_max", sa.Integer(), nullable=False),
        sa.Column("per_ip_window", sa.Integer(), nullable=False),
        sa.Column("per_user_max", sa.Integer(), nullable=False),
        sa.Column("per_user_window", sa.Integer(), nullable=False),
        sa.Column("global_max", sa.Integer(), nullable=False),
        sa.Column("global_window", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["provider_id"], ["oauth_providers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider_id", name="uq_oauth_provider_rate_limits_provider"),
    )
    op.create_index(
        "ix_oauth_provider_rate_limits_provider_id",
        "oauth_provider_rate_limits",
        ["provider_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oauth_provider_rate_limits_provider_id",
        table_name="oauth_provider_rate_limits",
    )
    op.drop_table("oauth_provider_rate_limits")
    op.drop_constraint(
        "fk_oauth_providers_last_edited_by_users",
        "oauth_providers",
        type_="foreignkey",
    )
    op.drop_column("oauth_providers", "last_successful_auth_at")
    op.drop_column("oauth_providers", "last_edited_at")
    op.drop_column("oauth_providers", "last_edited_by")
    op.drop_column("oauth_providers", "source")
    oauth_provider_source.drop(op.get_bind(), checkfirst=True)
