"""Add execution status for quota-paused work.

Revision ID: 105_execution_paused_quota
Revises: 104_cost_attr_subscription
Create Date: 2026-05-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "105_execution_paused_quota"
down_revision: str | None = "104_cost_attr_subscription"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE execution_status ADD VALUE IF NOT EXISTS 'paused_quota_exceeded'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value without recreating the type. The value is additive
    # and safe to leave in place for downgrade symmetry with earlier execution-status migrations.
    pass
