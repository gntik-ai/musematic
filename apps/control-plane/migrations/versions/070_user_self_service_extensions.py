"""Add user self-service notification and API key extensions.

Revision ID: 070_user_self_service_extensions
Revises: 069_oauth_provider_env_bootstrap
Create Date: 2026-04-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "070_user_self_service_extensions"
down_revision: str | None = "069_oauth_provider_env_bootstrap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_alert_settings",
        sa.Column(
            "per_channel_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "user_alert_settings",
        sa.Column(
            "digest_mode",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "user_alert_settings",
        sa.Column(
            "quiet_hours",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.add_column(
        "service_account_credentials",
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_service_account_credentials_created_by_user_id_users",
        "service_account_credentials",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_service_account_credentials_created_by_user_id",
        "service_account_credentials",
        ["created_by_user_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_chain_actor_subject_ts
        ON audit_chain_entries (
            ((canonical_payload ->> 'actor_id')),
            ((canonical_payload ->> 'subject_id')),
            created_at DESC
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audit_chain_actor_subject_ts")
    op.drop_index(
        "ix_service_account_credentials_created_by_user_id",
        table_name="service_account_credentials",
    )
    op.drop_constraint(
        "fk_service_account_credentials_created_by_user_id_users",
        "service_account_credentials",
        type_="foreignkey",
    )
    op.drop_column("service_account_credentials", "created_by_user_id")
    op.drop_column("user_alert_settings", "quiet_hours")
    op.drop_column("user_alert_settings", "digest_mode")
    op.drop_column("user_alert_settings", "per_channel_preferences")
