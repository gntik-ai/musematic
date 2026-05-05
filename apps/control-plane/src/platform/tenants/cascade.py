"""Tenant cascade handlers — registered cleanup hooks invoked by
``TenantsService.complete_deletion`` to wipe tenant-scoped DB rows.

UPD-053 (106) note on DNS teardown placement: per-tenant DNS records
(``<slug>``, ``<slug>.api``, ``<slug>.grafana`` x {A, AAAA}) are NOT
removed via this module. The DNS teardown adapter lives at
``platform.tenants.dns_teardown.DnsTeardownService`` and is wired through
the data-lifecycle BC's phase-2 cascade dispatch (see
``platform.data_lifecycle.cascade_dispatch.tenant_cascade.dispatch_tenant_cascade``).
Splitting the two paths keeps the ``TenantCascadeHandler`` signature
narrow (session + tenant_id → int) while letting the data-lifecycle BC
own the orchestration of side-effects that touch external systems.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from platform.tenants.table_catalog import TENANT_SCOPED_TABLES
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TenantCascadeHandler = Callable[[AsyncSession, UUID], Awaitable[int]]

_HANDLERS: list[tuple[str, TenantCascadeHandler]] = []


def register_tenant_cascade_handler(name: str, handler: TenantCascadeHandler) -> None:
    if any(existing_name == name for existing_name, _ in _HANDLERS):
        return
    _HANDLERS.append((name, handler))


def tenant_cascade_handlers() -> tuple[tuple[str, TenantCascadeHandler], ...]:
    if not _HANDLERS:
        register_tenant_cascade_handler("tenant_scoped_tables", delete_catalogued_rows)
    return tuple(_HANDLERS)


async def delete_catalogued_rows(session: AsyncSession, tenant_id: UUID) -> int:
    deleted = 0
    for table_name in reversed(TENANT_SCOPED_TABLES):
        exists = await session.scalar(
            text("SELECT to_regclass(:table_name) IS NOT NULL"),
            {"table_name": f"public.{table_name}"},
        )
        if not exists:
            continue
        result = await session.execute(
            text(f'DELETE FROM "{_quote_identifier(table_name)}" WHERE tenant_id = :tenant_id'),
            {"tenant_id": tenant_id},
        )
        deleted += int(getattr(result, "rowcount", 0) or 0)
    return deleted


def _quote_identifier(identifier: str) -> str:
    return identifier.replace('"', '""')
