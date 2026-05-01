from __future__ import annotations

from pathlib import Path
from platform.tenants.seeder import DEFAULT_TENANT_ID
from platform.tenants.table_catalog import TENANT_SCOPED_TABLES

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "audit_pass_realistic.sql"


async def load_audit_pass_fixture(database_url: str) -> None:
    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            raw = await connection.get_raw_connection()
            await raw.driver_connection.execute(FIXTURE_PATH.read_text())
    finally:
        await engine.dispose()


async def catalog_row_counts(connection: AsyncConnection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in TENANT_SCOPED_TABLES:
        if not await table_exists(connection, table_name):
            counts[table_name] = -1
            continue
        counts[table_name] = int(
            await connection.scalar(text(f"SELECT COUNT(*) FROM {_quote(table_name)}")) or 0
        )
    return counts


async def assert_catalog_tables_present(connection: AsyncConnection) -> None:
    missing = [
        table_name
        for table_name in TENANT_SCOPED_TABLES
        if not await table_exists(connection, table_name)
    ]
    assert missing == []


async def assert_all_catalog_rows_default_tenant(connection: AsyncConnection) -> None:
    for table_name in TENANT_SCOPED_TABLES:
        if not await table_exists(connection, table_name):
            continue
        mismatches = await connection.scalar(
            text(
                f"""
                SELECT COUNT(*)
                FROM {_quote(table_name)}
                WHERE tenant_id IS NULL OR tenant_id != :default_tenant_id
                """
            ),
            {"default_tenant_id": DEFAULT_TENANT_ID},
        )
        assert int(mismatches or 0) == 0, table_name


async def assert_tenant_columns_removed(connection: AsyncConnection) -> None:
    for table_name in TENANT_SCOPED_TABLES:
        if not await table_exists(connection, table_name):
            continue
        assert not await column_exists(connection, table_name, "tenant_id"), table_name


async def assert_tenant_migration_shape(connection: AsyncConnection) -> None:
    for table_name in TENANT_SCOPED_TABLES:
        assert await column_is_not_null(connection, table_name, "tenant_id"), table_name
        assert await tenant_id_index_exists(connection, table_name), table_name
        assert await tenant_rls_is_forced(connection, table_name), table_name
        assert await tenant_policy_exists(connection, table_name), table_name


async def table_exists(connection: AsyncConnection, table_name: str) -> bool:
    return bool(
        await connection.scalar(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
    )


async def column_exists(connection: AsyncConnection, table_name: str, column_name: str) -> bool:
    return bool(
        await connection.scalar(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        )
    )


async def column_is_not_null(
    connection: AsyncConnection,
    table_name: str,
    column_name: str,
) -> bool:
    value = await connection.scalar(
        text(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return value == "NO"


async def tenant_id_index_exists(connection: AsyncConnection, table_name: str) -> bool:
    return bool(
        await connection.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_class table_class
                    JOIN pg_namespace ns ON ns.oid = table_class.relnamespace
                    JOIN pg_index idx ON idx.indrelid = table_class.oid
                    JOIN pg_attribute attr
                      ON attr.attrelid = table_class.oid
                     AND attr.attnum = ANY(idx.indkey)
                    WHERE ns.nspname = 'public'
                      AND table_class.relname = :table_name
                      AND attr.attname = 'tenant_id'
                )
                """
            ),
            {"table_name": table_name},
        )
    )


async def tenant_rls_is_forced(connection: AsyncConnection, table_name: str) -> bool:
    row = (
        await connection.execute(
            text(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = :table_name
                """
            ),
            {"table_name": table_name},
        )
    ).one()
    return bool(row.relrowsecurity and row.relforcerowsecurity)


async def tenant_policy_exists(connection: AsyncConnection, table_name: str) -> bool:
    return bool(
        await connection.scalar(
            text(
                """
                SELECT 1
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = :table_name
                  AND policyname = 'tenant_isolation'
                """
            ),
            {"table_name": table_name},
        )
    )


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
