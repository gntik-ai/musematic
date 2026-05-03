"""Sub-processor email change subscriptions (UPD-051 / T080).

Adds the ``sub_processor_email_subscriptions`` table backing the public
``POST /api/v1/public/sub-processors/subscribe`` endpoint. Pending
subscribers store a SHA-256 hashed verification token; only after the
subscriber clicks the verification link (sent via UPD-077 email channel)
does ``verified_at`` get populated. Only verified subscribers receive
change notifications.

The table is platform-level (NOT tenant-scoped) because the public
sub-processors page is a public artifact — subscribers don't belong to
any tenant.

Revision ID: 113_sub_processor_email_subscriptions
Revises: 112_data_lifecycle_tag_types
Create Date: 2026-05-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "113_sub_processor_email_subscriptions"
down_revision: str | None = "112_data_lifecycle_tag_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "sub_processor_email_subscriptions",
        sa.Column(
            "id",
            PG_UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "verification_token_hash",
            postgresql.BYTEA(),
            nullable=False,
        ),
        sa.Column(
            "verification_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "unsubscribed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # An email may have multiple historical rows (re-subscribe after
    # unsubscribe); the unique guard is on the verification-token hash
    # so one token cannot resolve two rows.
    op.create_index(
        "uq_sub_processor_email_subscriptions_token_hash",
        "sub_processor_email_subscriptions",
        ["verification_token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_sub_processor_email_subscriptions_email_active",
        "sub_processor_email_subscriptions",
        ["email"],
        postgresql_where=sa.text(
            "verified_at IS NOT NULL AND unsubscribed_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sub_processor_email_subscriptions_email_active",
        table_name="sub_processor_email_subscriptions",
    )
    op.drop_index(
        "uq_sub_processor_email_subscriptions_token_hash",
        table_name="sub_processor_email_subscriptions",
    )
    op.drop_table("sub_processor_email_subscriptions")
