from __future__ import annotations

from platform.tenants.seeder import DEFAULT_TENANT_ID
from platform.tenants.table_catalog import TENANT_SCOPED_TABLES
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.helpers import make_async_database_url, run_alembic


async def test_tenant_migrations_096_to_101_smoke(postgres_container) -> None:
    database_url = make_async_database_url(postgres_container.get_connection_url())
    run_alembic(database_url, "upgrade", "095_status_page_and_scenarios")
    await _seed_pre_tenant_fixture(database_url)

    try:
        run_alembic(database_url, "upgrade", "101_platform_staff_role")

        engine = create_async_engine(database_url, future=True)
        try:
            async with engine.connect() as connection:
                default_row = (
                    await connection.execute(
                        text(
                            """
                            SELECT id, slug, subdomain, kind, status
                            FROM tenants
                            WHERE id = :default_tenant_id
                            """
                        ),
                        {"default_tenant_id": DEFAULT_TENANT_ID},
                    )
                ).mappings().one()
                assert str(default_row["id"]) == str(DEFAULT_TENANT_ID)
                assert default_row["slug"] == "default"
                assert default_row["subdomain"] == "app"
                assert default_row["kind"] == "default"
                assert default_row["status"] == "active"

                fixture_tenant_id = await connection.scalar(
                    text("SELECT tenant_id FROM users WHERE email = :email"),
                    {"email": "tenant-migration-smoke@example.com"},
                )
                assert fixture_tenant_id == DEFAULT_TENANT_ID

                missing_tables = await _catalog_tables_missing_from_database(connection)
                assert missing_tables == []

                for table_name in TENANT_SCOPED_TABLES:
                    assert await _tenant_id_column_is_not_null(connection, table_name), table_name
                    assert await _tenant_id_index_exists(connection, table_name), table_name
                    assert await _tenant_rls_is_forced(connection, table_name), table_name
                    assert await _tenant_policy_exists(connection, table_name), table_name

                staff_role = await connection.scalar(
                    text(
                        """
                        SELECT rolbypassrls
                        FROM pg_roles
                        WHERE rolname = 'musematic_platform_staff'
                        """
                    )
                )
                assert staff_role is True
        finally:
            await engine.dispose()
    finally:
        run_alembic(database_url, "downgrade", "base")


async def _seed_pre_tenant_fixture(database_url: str) -> None:
    engine = create_async_engine(database_url, future=True)
    try:
        user_id = uuid4()
        workspace_id = uuid4()
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO users (id, email, display_name, status)
                    VALUES (
                        :user_id,
                        'tenant-migration-smoke@example.com',
                        'Tenant Migration Smoke',
                        'active'
                    )
                    """
                ),
                {"user_id": user_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO workspaces (id, name, owner_id)
                    VALUES (:workspace_id, 'Tenant Migration Smoke Workspace', :user_id)
                    """
                ),
                {"workspace_id": workspace_id, "user_id": user_id},
            )
    finally:
        await engine.dispose()


async def _catalog_tables_missing_from_database(connection) -> list[str]:
    result = await connection.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
    )
    existing = {row[0] for row in result}
    return sorted(set(TENANT_SCOPED_TABLES) - existing)


async def _tenant_id_column_is_not_null(connection, table_name: str) -> bool:
    value = await connection.scalar(
        text(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = 'tenant_id'
            """
        ),
        {"table_name": table_name},
    )
    return value == "NO"


async def _tenant_id_index_exists(connection, table_name: str) -> bool:
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


async def _tenant_rls_is_forced(connection, table_name: str) -> bool:
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


async def _tenant_policy_exists(connection, table_name: str) -> bool:
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
