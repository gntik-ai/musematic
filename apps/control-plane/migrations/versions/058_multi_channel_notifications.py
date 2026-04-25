"""Add multi-channel notification schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "058_multi_channel_notifications"
down_revision = "060"
branch_labels = None
depends_on = None

deliverymethod = postgresql.ENUM(
    "in_app",
    "email",
    "webhook",
    "slack",
    "teams",
    "sms",
    name="deliverymethod",
    create_type=False,
)


def upgrade() -> None:
    op.execute("ALTER TYPE deliverymethod ADD VALUE IF NOT EXISTS 'slack'")
    op.execute("ALTER TYPE deliverymethod ADD VALUE IF NOT EXISTS 'teams'")
    op.execute("ALTER TYPE deliverymethod ADD VALUE IF NOT EXISTS 'sms'")

    op.create_table(
        "notification_channel_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_type", deliverymethod, nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("signing_secret_ref", sa.String(length=256), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_token_hash", sa.String(length=128), nullable=True),
        sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quiet_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("alert_type_filter", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("severity_floor", sa.String(length=16), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id",
            "channel_type",
            "target",
            name="uq_notification_channel_configs_user_channel_target",
        ),
    )
    op.create_index(
        "idx_channel_configs_user_enabled",
        "notification_channel_configs",
        ["user_id", "enabled"],
        unique=False,
    )
    op.create_index(
        "idx_channel_configs_user_type_active",
        "notification_channel_configs",
        ["user_id", "channel_type"],
        unique=False,
        postgresql_where=sa.text("enabled AND verified_at IS NOT NULL"),
    )

    op.create_table(
        "outbound_webhooks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("event_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("signing_secret_ref", sa.String(length=256), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "retry_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(
                "jsonb_build_object("
                "'max_retries', 3, "
                "'backoff_seconds', jsonb_build_array(60, 300, 1800), "
                "'total_window_seconds', 86400"
                ")"
            ),
        ),
        sa.Column("region_pinned_to", sa.String(length=64), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index(
        "idx_outbound_webhooks_workspace_active",
        "outbound_webhooks",
        ["workspace_id", "active"],
        unique=False,
    )
    op.create_index(
        "idx_outbound_webhooks_workspace",
        "outbound_webhooks",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_response_status", sa.Integer(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replayed_from", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("replayed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["webhook_id"], ["outbound_webhooks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replayed_from"], ["webhook_deliveries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["replayed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('pending', 'delivering', 'delivered', 'failed', 'dead_letter')",
            name="ck_webhook_deliveries_status",
        ),
    )
    op.create_index(
        "uq_webhook_deliveries_webhook_idempotency_original",
        "webhook_deliveries",
        ["webhook_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("replayed_from IS NULL"),
    )
    op.create_index(
        "idx_webhook_deliveries_status_next_attempt",
        "webhook_deliveries",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "idx_webhook_deliveries_workspace_dlq",
        "webhook_deliveries",
        ["webhook_id", "dead_lettered_at"],
        unique=False,
        postgresql_where=sa.text("status = 'dead_letter'"),
    )


def downgrade() -> None:
    op.drop_index("idx_webhook_deliveries_workspace_dlq", table_name="webhook_deliveries")
    op.drop_index("idx_webhook_deliveries_status_next_attempt", table_name="webhook_deliveries")
    op.drop_index(
        "uq_webhook_deliveries_webhook_idempotency_original",
        table_name="webhook_deliveries",
    )
    op.drop_table("webhook_deliveries")

    op.drop_index("idx_outbound_webhooks_workspace", table_name="outbound_webhooks")
    op.drop_index("idx_outbound_webhooks_workspace_active", table_name="outbound_webhooks")
    op.drop_table("outbound_webhooks")

    op.drop_index(
        "idx_channel_configs_user_type_active",
        table_name="notification_channel_configs",
    )
    op.drop_index(
        "idx_channel_configs_user_enabled",
        table_name="notification_channel_configs",
    )
    op.drop_table("notification_channel_configs")
