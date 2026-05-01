"""Add nullable tenant_id columns.

Revision ID: 097_tenant_id_columns_nullable
Revises: 096_tenant_table_and_seed
Create Date: 2026-05-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.tenant_table_catalog_snapshot import TENANT_SCOPED_TABLES

revision: str = "097_tenant_id_columns_nullable"
down_revision: str | None = "096_tenant_table_and_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "_alembic_tenant_backfill_checkpoint",
        sa.Column("table_name", sa.Text(), primary_key=True, nullable=False),
        sa.Column("completed_phase", sa.Text(), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    for table_name in TENANT_SCOPED_TABLES:
        quoted = _quote(table_name)
        op.execute(f"ALTER TABLE IF EXISTS {quoted} ADD COLUMN IF NOT EXISTS tenant_id UUID NULL")


def downgrade() -> None:
    for table_name in reversed(TENANT_SCOPED_TABLES):
        op.execute(f"ALTER TABLE IF EXISTS {_quote(table_name)} DROP COLUMN IF EXISTS tenant_id")
    op.drop_table("_alembic_tenant_backfill_checkpoint")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
