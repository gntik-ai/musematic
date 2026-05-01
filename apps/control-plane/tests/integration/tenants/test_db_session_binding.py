from __future__ import annotations

from platform.common import database
from platform.common.tenant_context import TenantContext, current_tenant
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_regular_session_binds_current_tenant_and_platform_staff_bypasses_rls(
    migrated_database_url: str,
) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    regular_engine = create_async_engine(migrated_database_url, future=True)
    platform_staff_engine = create_async_engine(migrated_database_url, future=True)
    database._install_tenant_binding_listener(regular_engine)

    try:
        await _create_probe_table(platform_staff_engine, tenant_a, tenant_b)

        async with regular_engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text("SET LOCAL ROLE tenant_binding_regular"))
                count_without_tenant = await connection.scalar(
                    text("SELECT COUNT(*) FROM tenant_binding_probe")
                )

        tenant_token = current_tenant.set(
            TenantContext(
                id=tenant_a,
                slug="tenant-a",
                subdomain="tenant-a",
                kind="enterprise",
                status="active",
                region="eu-central",
            )
        )
        try:
            async with regular_engine.connect() as connection:
                async with connection.begin():
                    await connection.execute(text("SET LOCAL ROLE tenant_binding_regular"))
                    tenant_rows = (
                        await connection.execute(
                            text(
                                """
                                SELECT label
                                FROM tenant_binding_probe
                                ORDER BY label
                                """
                            )
                        )
                    ).scalars().all()
        finally:
            current_tenant.reset(tenant_token)

        async with platform_staff_engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text("SET LOCAL ROLE tenant_binding_staff"))
                platform_rows = (
                    await connection.execute(
                        text(
                            """
                            SELECT label
                            FROM tenant_binding_probe
                            ORDER BY label
                            """
                        )
                    )
                ).scalars().all()

        assert count_without_tenant == 0
        assert tenant_rows == ["tenant-a-row"]
        assert platform_rows == ["tenant-a-row", "tenant-b-row"]
    finally:
        await _drop_probe_table(platform_staff_engine)
        await regular_engine.dispose()
        await platform_staff_engine.dispose()


async def _create_probe_table(engine, tenant_a, tenant_b) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS tenant_binding_probe"))
        await connection.execute(text("DROP ROLE IF EXISTS tenant_binding_regular"))
        await connection.execute(text("DROP ROLE IF EXISTS tenant_binding_staff"))
        await connection.execute(text("CREATE ROLE tenant_binding_regular"))
        await connection.execute(text("CREATE ROLE tenant_binding_staff BYPASSRLS"))
        await connection.execute(
            text(
                """
                CREATE TABLE tenant_binding_probe (
                    id UUID PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    label TEXT NOT NULL
                )
                """
            )
        )
        await connection.execute(
            text(
                """
                INSERT INTO tenant_binding_probe (id, tenant_id, label)
                VALUES
                    (gen_random_uuid(), :tenant_a, 'tenant-a-row'),
                    (gen_random_uuid(), :tenant_b, 'tenant-b-row')
                """
            ),
            {"tenant_a": tenant_a, "tenant_b": tenant_b},
        )
        await connection.execute(text("GRANT USAGE ON SCHEMA public TO tenant_binding_regular"))
        await connection.execute(text("GRANT USAGE ON SCHEMA public TO tenant_binding_staff"))
        await connection.execute(
            text("GRANT SELECT ON tenant_binding_probe TO tenant_binding_regular")
        )
        await connection.execute(
            text("GRANT SELECT ON tenant_binding_probe TO tenant_binding_staff")
        )
        await connection.execute(text("ALTER TABLE tenant_binding_probe ENABLE ROW LEVEL SECURITY"))
        await connection.execute(text("ALTER TABLE tenant_binding_probe FORCE ROW LEVEL SECURITY"))
        await connection.execute(
            text(
                """
                CREATE POLICY tenant_isolation ON tenant_binding_probe
                USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
                """
            )
        )


async def _drop_probe_table(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS tenant_binding_probe"))
        await connection.execute(text("REVOKE USAGE ON SCHEMA public FROM tenant_binding_regular"))
        await connection.execute(text("REVOKE USAGE ON SCHEMA public FROM tenant_binding_staff"))
        await connection.execute(text("DROP ROLE IF EXISTS tenant_binding_regular"))
        await connection.execute(text("DROP ROLE IF EXISTS tenant_binding_staff"))
