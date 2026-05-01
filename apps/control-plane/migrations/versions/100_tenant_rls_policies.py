"""Enable tenant RLS policies.

Revision ID: 100_tenant_rls_policies
Revises: 099_tenant_id_nn_indexes
Create Date: 2026-05-01
"""

from __future__ import annotations

from collections.abc import Sequence
from platform.tenants.table_catalog import TENANT_SCOPED_TABLES

import sqlalchemy as sa
from alembic import op

revision: str = "100_tenant_rls_policies"
down_revision: str | None = "099_tenant_id_nn_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    for table_name in TENANT_SCOPED_TABLES:
        if not _table_has_tenant_id(connection, table_name):
            continue
        quoted = _quote(table_name)
        op.execute(f"ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {quoted} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {quoted}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {quoted}
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
            """
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in reversed(TENANT_SCOPED_TABLES):
        if not _table_exists(connection, table_name):
            continue
        quoted = _quote(table_name)
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {quoted}")
        op.execute(f"ALTER TABLE {quoted} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {quoted} DISABLE ROW LEVEL SECURITY")


def _table_exists(connection: sa.Connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
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


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
