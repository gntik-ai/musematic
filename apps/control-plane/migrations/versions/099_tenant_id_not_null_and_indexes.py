"""Make tenant_id not null and indexed.

Revision ID: 099_tenant_id_nn_indexes
Revises: 098_tenant_id_backfill_default
Create Date: 2026-05-01
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from platform.tenants.table_catalog import TENANT_SCOPED_TABLES

import sqlalchemy as sa
from alembic import op

revision: str = "099_tenant_id_nn_indexes"
down_revision: str | None = "098_tenant_id_backfill_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    for table_name in TENANT_SCOPED_TABLES:
        if not _table_has_tenant_id(connection, table_name):
            continue
        quoted = _quote(table_name)
        op.execute(f"ALTER TABLE IF EXISTS {quoted} ALTER COLUMN tenant_id SET NOT NULL")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {_quote(_index_name(table_name))} ON {quoted} (tenant_id)"
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in reversed(TENANT_SCOPED_TABLES):
        op.execute(f"DROP INDEX IF EXISTS {_quote(_index_name(table_name))}")
        if _table_has_tenant_id(connection, table_name):
            op.execute(
                f"ALTER TABLE IF EXISTS {_quote(table_name)} ALTER COLUMN tenant_id DROP NOT NULL"
            )


def _table_has_tenant_id(connection: sa.Connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = 'tenant_id'
                """
            ),
            {"table_name": table_name},
        ).scalar()
    )


def _index_name(table_name: str) -> str:
    candidate = f"{table_name}_tenant_id_idx"
    if len(candidate) <= 63:
        return candidate
    digest = hashlib.sha1(candidate.encode("utf-8")).hexdigest()[:10]
    return f"{table_name[:49]}_{digest}_idx"


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
