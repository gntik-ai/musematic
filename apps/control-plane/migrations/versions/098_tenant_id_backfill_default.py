"""Backfill tenant_id with default tenant.

Revision ID: 098_tenant_id_backfill_default
Revises: 097_tenant_id_columns_nullable
Create Date: 2026-05-01
"""

from __future__ import annotations

from collections.abc import Sequence
from platform.tenants.table_catalog import TENANT_SCOPED_TABLES

import sqlalchemy as sa
from alembic import op

revision: str = "098_tenant_id_backfill_default"
down_revision: str | None = "097_tenant_id_columns_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
PHASE = "backfilled_default"
BATCH_SIZE = 50_000
LARGE_TABLE_THRESHOLD = 1_000_000


def upgrade() -> None:
    connection = op.get_bind()
    for table_name in TENANT_SCOPED_TABLES:
        if _checkpoint_exists(connection, table_name):
            continue
        if not _table_has_tenant_id(connection, table_name):
            continue
        if _estimated_rows(connection, table_name) > LARGE_TABLE_THRESHOLD:
            _backfill_batched(connection, table_name)
        else:
            connection.execute(
                sa.text(
                    f"UPDATE {_quote(table_name)} "
                    "SET tenant_id = :tenant_id WHERE tenant_id IS NULL"
                ),
                {"tenant_id": DEFAULT_TENANT_ID},
            )
        connection.execute(
            sa.text(
                """
                INSERT INTO _alembic_tenant_backfill_checkpoint (table_name, completed_phase)
                VALUES (:table_name, :phase)
                ON CONFLICT (table_name) DO UPDATE
                SET completed_phase = EXCLUDED.completed_phase,
                    completed_at = now()
                """
            ),
            {"table_name": table_name, "phase": PHASE},
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM _alembic_tenant_backfill_checkpoint WHERE completed_phase = :phase"
        ).bindparams(phase=PHASE)
    )


def _backfill_batched(connection: sa.Connection, table_name: str) -> None:
    quoted = _quote(table_name)
    while True:
        result = connection.execute(
            sa.text(
                f"""
                WITH batch AS (
                    SELECT ctid FROM {quoted}
                    WHERE tenant_id IS NULL
                    LIMIT :limit
                )
                UPDATE {quoted}
                SET tenant_id = :tenant_id
                FROM batch
                WHERE {quoted}.ctid = batch.ctid
                """
            ),
            {"tenant_id": DEFAULT_TENANT_ID, "limit": BATCH_SIZE},
        )
        if result.rowcount == 0:
            break


def _checkpoint_exists(connection: sa.Connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            sa.text(
                """
                SELECT 1
                FROM _alembic_tenant_backfill_checkpoint
                WHERE table_name = :table_name AND completed_phase = :phase
                """
            ),
            {"table_name": table_name, "phase": PHASE},
        ).scalar()
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


def _estimated_rows(connection: sa.Connection, table_name: str) -> int:
    value = connection.execute(
        sa.text(
            """
            SELECT COALESCE(c.reltuples::bigint, 0)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = :table_name
            """
        ),
        {"table_name": table_name},
    ).scalar()
    return int(value or 0)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
