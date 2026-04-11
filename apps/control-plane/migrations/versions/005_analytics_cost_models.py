"""Analytics cost model schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "005_analytics_cost_models"
down_revision = "004_workspaces_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_cost_models",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("input_token_cost_usd", sa.Numeric(18, 10), nullable=False),
        sa.Column("output_token_cost_usd", sa.Numeric(18, 10), nullable=False),
        sa.Column("per_second_cost_usd", sa.Numeric(18, 10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_analytics_cost_models_model_id_is_active",
        "analytics_cost_models",
        ["model_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "uq_analytics_cost_models_model_id_active",
        "analytics_cost_models",
        ["model_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.execute(
        """
        INSERT INTO analytics_cost_models
            (model_id, provider, display_name, input_token_cost_usd, output_token_cost_usd,
             per_second_cost_usd, is_active, valid_from)
        VALUES
            ('gpt-4o', 'openai', 'GPT-4o', 0.0000025, 0.0000100, NULL, true, now()),
            (
                'claude-3-5-sonnet', 'anthropic', 'Claude 3.5 Sonnet',
                0.0000030, 0.0000150, NULL, true, now()
            ),
            (
                'claude-3-5-haiku', 'anthropic', 'Claude 3.5 Haiku',
                0.0000008, 0.0000040, NULL, true, now()
            ),
            (
                'gemini-2.0-flash', 'google', 'Gemini 2.0 Flash',
                0.0000005, 0.0000020, NULL, true, now()
            )
        """
    )


def downgrade() -> None:
    op.drop_index("uq_analytics_cost_models_model_id_active", table_name="analytics_cost_models")
    op.drop_index("ix_analytics_cost_models_model_id_is_active", table_name="analytics_cost_models")
    op.drop_table("analytics_cost_models")
