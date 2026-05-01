from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_SUBDOMAIN = "app"


async def provision_default_tenant_if_missing(session: AsyncSession) -> None:
    should_commit = not session.in_transaction()
    await session.execute(
        text(
            """
            INSERT INTO tenants (
                id,
                slug,
                kind,
                subdomain,
                display_name,
                region,
                data_isolation_mode,
                branding_config_json,
                status,
                contract_metadata_json,
                feature_flags_json
            )
            VALUES (
                :id,
                :slug,
                'default',
                :subdomain,
                'Musematic',
                'global',
                'pool',
                '{}'::jsonb,
                'active',
                '{}'::jsonb,
                '{}'::jsonb
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": DEFAULT_TENANT_ID,
            "slug": DEFAULT_TENANT_SLUG,
            "subdomain": DEFAULT_TENANT_SUBDOMAIN,
        },
    )
    if should_commit:
        await session.commit()
