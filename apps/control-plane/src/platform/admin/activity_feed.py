from __future__ import annotations

from datetime import datetime
from platform.audit.models import AuditChainEntry
from platform.common.tenant_context import current_tenant
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def list_admin_activity(
    session: AsyncSession,
    tenant_id: UUID | None,
    limit: int = 50,
    since: datetime | None = None,
) -> list[AuditChainEntry]:
    resolved_tenant = current_tenant.get(None)
    if tenant_id is None and resolved_tenant is not None:
        tenant_id = resolved_tenant.id
    statement = select(AuditChainEntry).where(
        AuditChainEntry.audit_event_source.like("platform.admin%")
    )
    if tenant_id is not None:
        statement = statement.where(
            AuditChainEntry.canonical_payload["tenant_id"].as_string() == str(tenant_id)
        )
    if since is not None:
        statement = statement.where(AuditChainEntry.created_at >= since)
    result = await session.execute(
        statement.order_by(AuditChainEntry.created_at.desc()).limit(min(limit, 500))
    )
    return list(result.scalars().all())
