"""Compatibility marker for model catalog revisions.

Revision ID: 059_model_catalog
Revises: 057_api_governance
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op

revision: str = "059_model_catalog"
down_revision: str | None = "057_api_governance"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # The model catalog objects are not present in this tree; retain the
    # revision id so existing local clusters can continue upgrading.
    op.execute("SELECT 1")


def downgrade() -> None:
    op.execute("SELECT 1")
