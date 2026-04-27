"""Add pending profile completion account status.

Revision ID: 068_pending_profile_completion
Revises: 067_admin_workbench
Create Date: 2026-04-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "068_pending_profile_completion"
down_revision: str | None = "067_admin_workbench"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE accounts_user_status ADD VALUE IF NOT EXISTS "
        "'pending_profile_completion'"
    )


def downgrade() -> None:
    # PostgreSQL enum additions are intentionally left in place on downgrade.
    pass
