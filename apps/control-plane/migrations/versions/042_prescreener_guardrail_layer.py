"""Add pre_screener value to trust_guardrail_layer enum."""

from __future__ import annotations

from alembic import op

revision = "042_prescreener_guardrail_layer"
down_revision = "041_fqn_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE trust_guardrail_layer ADD VALUE IF NOT EXISTS 'pre_screener'")


def downgrade() -> None:
    pass
