from __future__ import annotations

from platform.tenants.seeder import DEFAULT_TENANT_ID
from platform.tenants.table_catalog import TENANT_SCOPED_TABLES

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.helpers import make_async_database_url, run_alembic
from tests.integration.migrations.tenant_upgrade_helpers import (
    assert_all_catalog_rows_default_tenant,
    catalog_row_counts,
    load_audit_pass_fixture,
    table_exists,
)


async def test_resumable_backfill_after_checkpointed_interrupt(postgres_container) -> None:
    database_url = make_async_database_url(postgres_container.get_connection_url())
    run_alembic(database_url, "upgrade", "095_status_page_and_scenarios")
    await load_audit_pass_fixture(database_url)

    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            pre_upgrade_counts = await catalog_row_counts(connection)

        run_alembic(database_url, "upgrade", "097_tenant_id_columns_nullable")

        async with engine.begin() as connection:
            completed_tables = await _first_existing_tables(connection, count=5)
            for table_name in completed_tables:
                await connection.execute(
                    text(
                        f"""
                        UPDATE {_quote(table_name)}
                        SET tenant_id = :tenant_id
                        WHERE tenant_id IS NULL
                        """
                    ),
                    {"tenant_id": DEFAULT_TENANT_ID},
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO _alembic_tenant_backfill_checkpoint (
                            table_name,
                            completed_phase
                        )
                        VALUES (:table_name, 'backfilled_default')
                        """
                    ),
                    {"table_name": table_name},
                )

            partial_table = None
            for candidate in ("executions", "audit_chain_entries", "cost_attributions"):
                if await table_exists(connection, candidate):
                    partial_table = candidate
                    break
            assert partial_table is not None
            await connection.execute(
                text(
                    f"""
                    WITH partial AS (
                        SELECT ctid FROM {_quote(partial_table)}
                        WHERE tenant_id IS NULL
                        LIMIT 25
                    )
                    UPDATE {_quote(partial_table)}
                    SET tenant_id = :tenant_id
                    FROM partial
                    WHERE {_quote(partial_table)}.ctid = partial.ctid
                    """
                ),
                {"tenant_id": DEFAULT_TENANT_ID},
            )

        run_alembic(database_url, "upgrade", "101_platform_staff_role")

        async with engine.connect() as connection:
            await assert_all_catalog_rows_default_tenant(connection)
            assert await catalog_row_counts(connection) == pre_upgrade_counts
            duplicate_checkpoints = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT table_name
                        FROM _alembic_tenant_backfill_checkpoint
                        GROUP BY table_name
                        HAVING COUNT(*) > 1
                    ) duplicates
                    """
                )
            )
            assert int(duplicate_checkpoints or 0) == 0
    finally:
        await engine.dispose()
        run_alembic(database_url, "downgrade", "base")


async def _first_existing_tables(connection: AsyncConnection, *, count: int) -> list[str]:
    tables: list[str] = []
    for table_name in TENANT_SCOPED_TABLES:
        if await table_exists(connection, table_name):
            tables.append(table_name)
        if len(tables) == count:
            return tables
    return tables


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
