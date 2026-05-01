from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.helpers import make_async_database_url, run_alembic
from tests.integration.migrations.tenant_upgrade_helpers import (
    assert_tenant_columns_removed,
    catalog_row_counts,
    load_audit_pass_fixture,
    table_exists,
)


async def test_reverse_migration_restores_pre_tenant_shape(postgres_container) -> None:
    database_url = make_async_database_url(postgres_container.get_connection_url())
    run_alembic(database_url, "upgrade", "095_status_page_and_scenarios")
    await load_audit_pass_fixture(database_url)

    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            pre_upgrade_counts = await catalog_row_counts(connection)

        run_alembic(database_url, "upgrade", "101_platform_staff_role")
        run_alembic(database_url, "downgrade", "095_status_page_and_scenarios")

        async with engine.connect() as connection:
            assert not await table_exists(connection, "tenants")
            assert not await table_exists(connection, "tenant_enforcement_violations")
            assert not await table_exists(connection, "_alembic_tenant_backfill_checkpoint")
            await assert_tenant_columns_removed(connection)
            assert await catalog_row_counts(connection) == pre_upgrade_counts
            assert await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == "095_status_page_and_scenarios"
    finally:
        await engine.dispose()
        run_alembic(database_url, "downgrade", "base")
