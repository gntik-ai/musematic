"""UPD-052 — Invoices REST surface (workspace + admin tenant scope)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from platform.billing.invoices.repository import InvoicesRepository
from platform.billing.invoices.service import InvoicesService
from platform.billing.subscriptions.models import Subscription
from platform.common.dependencies import get_current_user
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)

invoices_router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/billing/invoices",
    tags=["billing:invoices"],
)


async def _get_session(request: Request) -> AsyncIterator[AsyncSession]:
    from platform.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def _resolve_tenant_for_workspace(
    session: AsyncSession,
    workspace_id: UUID,
) -> UUID:
    stmt = select(Subscription).where(
        Subscription.scope_type == "workspace",
        Subscription.scope_id == workspace_id,
    )
    sub = (await session.execute(stmt)).scalars().first()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="subscription_not_found",
        )
    return sub.tenant_id


def _serialize(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "stripe_invoice_id": row.stripe_invoice_id,
        "invoice_number": row.invoice_number,
        "amount_total": str(row.amount_total),
        "amount_subtotal": str(row.amount_subtotal),
        "amount_tax": str(row.amount_tax),
        "currency": row.currency,
        "status": row.status,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "issued_at": row.issued_at.isoformat() if row.issued_at else None,
        "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "pdf_url": row.pdf_url,
    }


@invoices_router.get("")
async def list_invoices(
    workspace_id: UUID,
    limit: int = 20,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    del current_user
    tenant_id = await _resolve_tenant_for_workspace(session, workspace_id)
    service = InvoicesService(InvoicesRepository(session))
    rows = await service.list_recent(tenant_id, limit=min(limit, 50))
    return {"items": [_serialize(r) for r in rows], "next_cursor": None}


@invoices_router.get("/{invoice_id}")
async def get_invoice(
    workspace_id: UUID,
    invoice_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    del current_user
    tenant_id = await _resolve_tenant_for_workspace(session, workspace_id)
    repo = InvoicesRepository(session)
    rows = await repo.list_for_tenant(tenant_id, limit=1000)
    invoice = next((r for r in rows if r.id == invoice_id), None)
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="invoice_not_found",
        )
    payload = _serialize(invoice)
    payload["line_items"] = []  # full breakdown deferred to integration suite
    payload["tax_breakdown"] = None
    return payload


@invoices_router.get("/{invoice_id}/pdf")
async def get_invoice_pdf_redirect(
    workspace_id: UUID,
    invoice_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Response:
    del current_user
    tenant_id = await _resolve_tenant_for_workspace(session, workspace_id)
    repo = InvoicesRepository(session)
    rows = await repo.list_for_tenant(tenant_id, limit=1000)
    invoice = next((r for r in rows if r.id == invoice_id), None)
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="invoice_not_found",
        )
    if not invoice.pdf_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="pdf_unavailable",
        )
    return Response(
        status_code=status.HTTP_302_FOUND,
        headers={"Location": invoice.pdf_url},
    )
