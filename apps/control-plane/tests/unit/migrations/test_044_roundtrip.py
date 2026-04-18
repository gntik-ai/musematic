from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from helpers import make_async_database_url, run_alembic


async def _table_names(engine):
    async with engine.connect() as connection:
        return set(
            await connection.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        )


async def _column_names(engine, table_name: str) -> set[str]:
    async with engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns(table_name)
        )
    return {column["name"] for column in columns}


@pytest.mark.integration
async def test_migration_044_roundtrip(postgres_container) -> None:
    database_url = make_async_database_url(postgres_container.get_connection_url())
    run_alembic(database_url, "upgrade", "043_runtime_warm_pool_targets")
    engine = create_async_engine(database_url, future=True)
    try:
        run_alembic(database_url, "upgrade", "044_ibor_and_decommission")
        tables = await _table_names(engine)
        registry_columns = await _column_names(engine, "registry_agent_profiles")
        user_role_columns = await _column_names(engine, "user_roles")
        async with engine.connect() as connection:
            enum_values = [
                row[0]
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT enumlabel
                            FROM pg_enum
                            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                            WHERE pg_type.typname = 'registry_lifecycle_status'
                            ORDER BY enumsortorder
                            """
                        )
                    )
                ).all()
            ]

        assert {"ibor_connectors", "ibor_sync_runs"}.issubset(tables)
        assert {"decommissioned_at", "decommission_reason", "decommissioned_by"}.issubset(
            registry_columns
        )
        assert "source_connector_id" in user_role_columns
        assert "decommissioned" in enum_values

        run_alembic(database_url, "downgrade", "043_runtime_warm_pool_targets")
        tables_after = await _table_names(engine)
        registry_columns_after = await _column_names(engine, "registry_agent_profiles")
        user_role_columns_after = await _column_names(engine, "user_roles")
        async with engine.connect() as connection:
            enum_values_after = [
                row[0]
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT enumlabel
                            FROM pg_enum
                            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                            WHERE pg_type.typname = 'registry_lifecycle_status'
                            ORDER BY enumsortorder
                            """
                        )
                    )
                ).all()
            ]

        assert "ibor_connectors" not in tables_after
        assert "ibor_sync_runs" not in tables_after
        assert "source_connector_id" not in user_role_columns_after
        assert {"decommissioned_at", "decommission_reason", "decommissioned_by"}.isdisjoint(
            registry_columns_after
        )
        assert "decommissioned" in enum_values_after
    finally:
        await engine.dispose()
