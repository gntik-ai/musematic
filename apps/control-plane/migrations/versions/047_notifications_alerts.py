"""Add notifications alert settings, alerts, and delivery outcomes."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "047_notifications_alerts"
down_revision = "046_workspace_goal_response"
branch_labels = None
depends_on = None

deliverymethod = postgresql.ENUM(
    "in_app",
    "email",
    "webhook",
    name="deliverymethod",
    create_type=False,
)
deliveryoutcome = postgresql.ENUM(
    "success",
    "failed",
    "timed_out",
    "fallback",
    name="deliveryoutcome",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    deliverymethod.create(bind, checkfirst=True)
    deliveryoutcome.create(bind, checkfirst=True)

    op.create_table(
        "user_alert_settings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "state_transitions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(
                """'[\"working_to_pending\",\"any_to_complete\",\"any_to_failed\"]'::jsonb"""
            ),
        ),
        sa.Column(
            "delivery_method",
            deliverymethod,
            nullable=False,
            server_default=sa.text("'in_app'"),
        ),
        sa.Column("webhook_url", sa.String(length=512), nullable=True),
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
        sa.UniqueConstraint("user_id", name="uq_user_alert_settings_user"),
    )

    op.create_table(
        "user_alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_reference", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "urgency",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'medium'"),
        ),
        sa.Column(
            "read",
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interaction_id"], ["interactions.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "idx_user_alerts_user_unread",
        "user_alerts",
        ["user_id", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text("NOT read"),
    )
    op.create_index(
        "idx_user_alerts_user_created",
        "user_alerts",
        ["user_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "alert_delivery_outcomes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivery_method", deliverymethod, nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("outcome", deliveryoutcome, nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["alert_id"], ["user_alerts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("alert_id", name="uq_alert_delivery_outcomes_alert"),
    )
    op.create_index(
        "ix_alert_delivery_outcomes_retry_scan",
        "alert_delivery_outcomes",
        ["delivery_method", "next_retry_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_alert_delivery_outcomes_retry_scan", table_name="alert_delivery_outcomes")
    op.drop_table("alert_delivery_outcomes")

    op.drop_index("idx_user_alerts_user_created", table_name="user_alerts")
    op.drop_index("idx_user_alerts_user_unread", table_name="user_alerts")
    op.drop_table("user_alerts")

    op.drop_table("user_alert_settings")

    bind = op.get_bind()
    deliveryoutcome.drop(bind, checkfirst=True)
    deliverymethod.drop(bind, checkfirst=True)
