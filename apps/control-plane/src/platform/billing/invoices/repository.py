"""Repository for the ``invoices`` table (UPD-052)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.billing.invoices.models import Invoice
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class InvoicesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_stripe_id(self, stripe_invoice_id: str) -> Invoice | None:
        result = await self.session.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self,
        tenant_id: UUID,
        *,
        limit: int = 20,
    ) -> list[Invoice]:
        stmt = (
            select(Invoice)
            .where(Invoice.tenant_id == tenant_id)
            .order_by(Invoice.period_end.desc().nullslast())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert(
        self,
        *,
        tenant_id: UUID,
        subscription_id: UUID,
        stripe_invoice_id: str,
        invoice_number: str | None,
        amount_total: Decimal,
        amount_subtotal: Decimal,
        amount_tax: Decimal,
        currency: str,
        status: str,
        period_start: datetime | None,
        period_end: datetime | None,
        issued_at: datetime | None,
        paid_at: datetime | None,
        pdf_url: str | None,
        metadata_json: dict[str, Any] | None = None,
    ) -> Invoice:
        existing = await self.get_by_stripe_id(stripe_invoice_id)
        if existing is not None:
            existing.amount_total = amount_total
            existing.amount_subtotal = amount_subtotal
            existing.amount_tax = amount_tax
            existing.currency = currency
            existing.status = status
            existing.period_start = period_start
            existing.period_end = period_end
            existing.issued_at = issued_at
            existing.paid_at = paid_at
            existing.pdf_url = pdf_url
            if metadata_json is not None:
                existing.metadata_json = metadata_json
            await self.session.flush()
            return existing
        record = Invoice(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            stripe_invoice_id=stripe_invoice_id,
            invoice_number=invoice_number,
            amount_total=amount_total,
            amount_subtotal=amount_subtotal,
            amount_tax=amount_tax,
            currency=currency,
            status=status,
            period_start=period_start,
            period_end=period_end,
            issued_at=issued_at,
            paid_at=paid_at,
            pdf_url=pdf_url,
            metadata_json=metadata_json or {},
        )
        self.session.add(record)
        await self.session.flush()
        return record
