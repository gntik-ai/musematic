"""Add API governance rate-limit and debug-logging schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "057_api_governance"
down_revision = "056_proximity_graph_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_subscription_tiers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("requests_per_minute", sa.Integer(), nullable=False),
        sa.Column("requests_per_hour", sa.Integer(), nullable=False),
        sa.Column("requests_per_day", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_api_subscription_tiers_name"),
        sa.CheckConstraint(
            "requests_per_minute > 0",
            name="ck_api_subscription_tiers_rpm_positive",
        ),
        sa.CheckConstraint("requests_per_hour > 0", name="ck_api_subscription_tiers_rph_positive"),
        sa.CheckConstraint("requests_per_day > 0", name="ck_api_subscription_tiers_rpd_positive"),
    )

    op.create_table(
        "api_rate_limits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("principal_type", sa.String(length=32), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_tier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requests_per_minute_override", sa.Integer(), nullable=True),
        sa.Column("requests_per_hour_override", sa.Integer(), nullable=True),
        sa.Column("requests_per_day_override", sa.Integer(), nullable=True),
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
            ["subscription_tier_id"],
            ["api_subscription_tiers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "principal_type",
            "principal_id",
            name="uq_api_rate_limits_principal",
        ),
        sa.CheckConstraint(
            "principal_type IN ('user', 'service_account', 'external_a2a')",
            name="ck_api_rate_limits_principal_type",
        ),
        sa.CheckConstraint(
            "requests_per_minute_override IS NULL OR requests_per_minute_override > 0",
            name="ck_api_rate_limits_rpm_override_positive",
        ),
        sa.CheckConstraint(
            "requests_per_hour_override IS NULL OR requests_per_hour_override > 0",
            name="ck_api_rate_limits_rph_override_positive",
        ),
        sa.CheckConstraint(
            "requests_per_day_override IS NULL OR requests_per_day_override > 0",
            name="ck_api_rate_limits_rpd_override_positive",
        ),
    )
    op.create_index(
        "ix_api_rate_limits_tier",
        "api_rate_limits",
        ["subscription_tier_id"],
        unique=False,
    )

    op.create_table(
        "debug_logging_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_reason", sa.String(length=64), nullable=True),
        sa.Column(
            "capture_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "target_type IN ('user', 'workspace')",
            name="ck_debug_logging_sessions_target_type",
        ),
        sa.CheckConstraint(
            "length(justification) >= 10",
            name="ck_debug_logging_sessions_justification_length",
        ),
        sa.CheckConstraint(
            "expires_at <= started_at + interval '4 hours'",
            name="ck_debug_logging_sessions_expires_within_four_hours",
        ),
    )
    op.create_index(
        "ix_debug_logging_sessions_target",
        "debug_logging_sessions",
        ["target_type", "target_id", "expires_at"],
        unique=False,
        postgresql_where=sa.text("terminated_at IS NULL"),
    )
    op.create_index(
        "ix_debug_logging_sessions_requested_by",
        "debug_logging_sessions",
        ["requested_by", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_debug_logging_sessions_expires_at",
        "debug_logging_sessions",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "debug_logging_captures",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column(
            "request_headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("request_body", sa.Text(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column(
            "response_headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["debug_logging_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "duration_ms >= 0",
            name="ck_debug_logging_captures_duration_non_negative",
        ),
    )
    op.create_index(
        "ix_debug_logging_captures_session",
        "debug_logging_captures",
        ["session_id", "captured_at"],
        unique=False,
    )
    op.create_index(
        "ix_debug_logging_captures_captured_at",
        "debug_logging_captures",
        ["captured_at"],
        unique=False,
    )

    tiers_table = sa.table(
        "api_subscription_tiers",
        sa.column("name", sa.String(length=32)),
        sa.column("requests_per_minute", sa.Integer()),
        sa.column("requests_per_hour", sa.Integer()),
        sa.column("requests_per_day", sa.Integer()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        tiers_table,
        [
            {
                "name": "anonymous",
                "requests_per_minute": 60,
                "requests_per_hour": 1_000,
                "requests_per_day": 10_000,
                "description": "Baseline budget for anonymous discovery and documentation traffic.",
            },
            {
                "name": "default",
                "requests_per_minute": 300,
                "requests_per_hour": 10_000,
                "requests_per_day": 100_000,
                "description": (
                    "Default budget for authenticated users and principals without overrides."
                ),
            },
            {
                "name": "pro",
                "requests_per_minute": 1_000,
                "requests_per_hour": 50_000,
                "requests_per_day": 500_000,
                "description": "Higher-throughput budget for professional integrations.",
            },
            {
                "name": "enterprise",
                "requests_per_minute": 5_000,
                "requests_per_hour": 500_000,
                "requests_per_day": 10_000_000,
                "description": "High-capacity budget for enterprise-grade automation workloads.",
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_debug_logging_captures_captured_at", table_name="debug_logging_captures")
    op.drop_index("ix_debug_logging_captures_session", table_name="debug_logging_captures")
    op.drop_table("debug_logging_captures")

    op.drop_index("ix_debug_logging_sessions_expires_at", table_name="debug_logging_sessions")
    op.drop_index("ix_debug_logging_sessions_requested_by", table_name="debug_logging_sessions")
    op.drop_index("ix_debug_logging_sessions_target", table_name="debug_logging_sessions")
    op.drop_table("debug_logging_sessions")

    op.drop_index("ix_api_rate_limits_tier", table_name="api_rate_limits")
    op.drop_table("api_rate_limits")

    op.drop_table("api_subscription_tiers")
