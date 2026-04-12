"""Marketplace discovery and intelligence schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "013_marketplace_schema"
down_revision = "012_workflow_execution_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_agent_ratings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("review_text", sa.Text(), nullable=True),
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
        sa.CheckConstraint("score >= 1 AND score <= 5", name="ck_marketplace_rating_score_range"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["accounts_users.id"],
            name="fk_marketplace_agent_ratings_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "agent_id", name="uq_marketplace_rating_user_agent"),
    )
    op.create_index(
        "ix_marketplace_agent_ratings_agent_id",
        "marketplace_agent_ratings",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketplace_agent_ratings_user_id",
        "marketplace_agent_ratings",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "marketplace_quality_aggregates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("has_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("execution_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "self_correction_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "quality_score_sum",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "quality_score_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "satisfaction_sum",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "satisfaction_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "certification_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'uncertified'"),
        ),
        sa.Column("data_source_last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_unavailable_since", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "uq_marketplace_quality_aggregates_agent_id",
        "marketplace_quality_aggregates",
        ["agent_id"],
        unique=True,
    )

    op.create_table(
        "marketplace_recommendations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("recommendation_type", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("reasoning", sa.String(length=512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            ["accounts_users.id"],
            name="fk_marketplace_recommendations_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_marketplace_recommendations_user_id",
        "marketplace_recommendations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketplace_recommendations_expires_at",
        "marketplace_recommendations",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_marketplace_recommendations_user_type",
        "marketplace_recommendations",
        ["user_id", "recommendation_type"],
        unique=False,
    )

    op.create_table(
        "marketplace_trending_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_fqn", sa.String(length=512), nullable=False),
        sa.Column("trending_score", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("growth_rate", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("invocations_this_week", sa.Integer(), nullable=False),
        sa.Column("invocations_last_week", sa.Integer(), nullable=False),
        sa.Column("trending_reason", sa.String(length=256), nullable=False),
        sa.Column("satisfaction_delta", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint(
            "snapshot_date",
            "agent_id",
            name="uq_marketplace_trending_date_agent",
        ),
    )
    op.create_index(
        "ix_marketplace_trending_date_rank",
        "marketplace_trending_snapshots",
        ["snapshot_date", "rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketplace_trending_date_rank",
        table_name="marketplace_trending_snapshots",
    )
    op.drop_table("marketplace_trending_snapshots")

    op.drop_index(
        "ix_marketplace_recommendations_user_type",
        table_name="marketplace_recommendations",
    )
    op.drop_index(
        "ix_marketplace_recommendations_expires_at",
        table_name="marketplace_recommendations",
    )
    op.drop_index(
        "ix_marketplace_recommendations_user_id",
        table_name="marketplace_recommendations",
    )
    op.drop_table("marketplace_recommendations")

    op.drop_index(
        "uq_marketplace_quality_aggregates_agent_id",
        table_name="marketplace_quality_aggregates",
    )
    op.drop_table("marketplace_quality_aggregates")

    op.drop_index(
        "ix_marketplace_agent_ratings_user_id",
        table_name="marketplace_agent_ratings",
    )
    op.drop_index(
        "ix_marketplace_agent_ratings_agent_id",
        table_name="marketplace_agent_ratings",
    )
    op.drop_table("marketplace_agent_ratings")
