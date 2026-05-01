from __future__ import annotations

from platform.tenants.seeder import DEFAULT_TENANT_ID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.helpers import make_async_database_url, run_alembic
from tests.integration.migrations.tenant_upgrade_helpers import (
    assert_all_catalog_rows_default_tenant,
    assert_catalog_tables_present,
    assert_tenant_migration_shape,
    catalog_row_counts,
    load_audit_pass_fixture,
)


async def test_full_upgrade_from_audit_pass_fixture(postgres_container) -> None:
    database_url = make_async_database_url(postgres_container.get_connection_url())
    run_alembic(database_url, "upgrade", "095_status_page_and_scenarios")
    await load_audit_pass_fixture(database_url)

    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.connect() as connection:
            pre_upgrade_counts = await catalog_row_counts(connection)

        run_alembic(database_url, "upgrade", "101_platform_staff_role")

        async with engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT 1 FROM tenants WHERE id = :tenant_id"),
                {"tenant_id": DEFAULT_TENANT_ID},
            )
            assert await connection.scalar(
                text("SELECT 1 FROM tenant_enforcement_violations LIMIT 1")
            ) is None
            await assert_catalog_tables_present(connection)
            await assert_tenant_migration_shape(connection)
            await assert_all_catalog_rows_default_tenant(connection)
            assert await catalog_row_counts(connection) == pre_upgrade_counts
    finally:
        await engine.dispose()
        run_alembic(database_url, "downgrade", "base")
