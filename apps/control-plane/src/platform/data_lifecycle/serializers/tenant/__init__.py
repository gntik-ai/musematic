"""Tenant-scope serializers for data export.

Mirrors the workspace serializer dispatch pattern. Tenant export ZIPs
are structured as ``tenant/`` (tenant metadata) + ``users/`` +
``audit/`` + ``costs/``. Per-workspace concatenation under
``workspaces/{id}/`` is a polish-tier optimization that walks
``workspaces_workspaces`` and invokes the workspace serializers per
workspace_id.
"""

from __future__ import annotations

from typing import AsyncIterator, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform.data_lifecycle.serializers.tenant.audit import (
    serialize_tenant_audit,
)
from platform.data_lifecycle.serializers.tenant.costs import (
    serialize_tenant_costs,
)
from platform.data_lifecycle.serializers.tenant.tenant_meta import (
    serialize_tenant_meta,
)
from platform.data_lifecycle.serializers.tenant.users import (
    serialize_tenant_users,
)


SerializerFn = Callable[..., AsyncIterator[tuple[str, bytes]]]


def build_default_tenant_serializers(
    *, session: AsyncSession
) -> dict[str, SerializerFn]:
    async def _meta(*, scope_id: UUID, tenant_id: UUID) -> AsyncIterator[tuple[str, bytes]]:
        async for entry in serialize_tenant_meta(
            session=session, tenant_id=tenant_id
        ):
            yield entry

    async def _users(*, scope_id: UUID, tenant_id: UUID) -> AsyncIterator[tuple[str, bytes]]:
        async for entry in serialize_tenant_users(
            session=session, tenant_id=tenant_id
        ):
            yield entry

    async def _audit(*, scope_id: UUID, tenant_id: UUID) -> AsyncIterator[tuple[str, bytes]]:
        async for entry in serialize_tenant_audit(
            session=session, tenant_id=tenant_id
        ):
            yield entry

    async def _costs(*, scope_id: UUID, tenant_id: UUID) -> AsyncIterator[tuple[str, bytes]]:
        async for entry in serialize_tenant_costs(
            session=session, tenant_id=tenant_id
        ):
            yield entry

    return {
        "tenant_meta": _meta,
        "users": _users,
        "audit": _audit,
        "costs": _costs,
    }
