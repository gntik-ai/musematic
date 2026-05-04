"""Service for the ``invoices`` BC (UPD-052)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.billing.invoices.models import Invoice
from platform.billing.invoices.repository import InvoicesRepository
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID

LOGGER = get_logger(__name__)


def _ts(value: object) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(int(value), tz=UTC)
    return None


def _eur_from_cents(value: object) -> Decimal:
    if isinstance(value, int | float):
        return Decimal(int(value)) / Decimal(100)
    return Decimal("0.00")


class InvoicesService:
    def __init__(self, repository: InvoicesRepository) -> None:
        self.repo = repository

    async def upsert_from_stripe(
        self,
        *,
        tenant_id: UUID,
        subscription_id: UUID,
        stripe_invoice: dict[str, Any],
    ) -> Invoice:
        """Idempotent upsert keyed on ``stripe_invoice_id``.

        ``stripe_invoice`` is the raw Stripe payload (the same shape that
        arrives in the ``invoice.payment_succeeded`` webhook payload). The
        method extracts the fields the local row needs and converts cents
        to EUR ``Decimal`` for the totals.
        """
        stripe_invoice_id = str(stripe_invoice.get("id", ""))
        if not stripe_invoice_id:
            raise ValueError("Stripe invoice payload is missing 'id'.")

        currency = str(stripe_invoice.get("currency", "eur")).upper() or "EUR"
        status = str(stripe_invoice.get("status", "open"))

        amount_total = _eur_from_cents(stripe_invoice.get("total"))
        amount_subtotal = _eur_from_cents(stripe_invoice.get("subtotal"))
        amount_tax = _eur_from_cents(stripe_invoice.get("tax"))
        period_start = _ts(stripe_invoice.get("period_start"))
        period_end = _ts(stripe_invoice.get("period_end"))
        issued_at = _ts(stripe_invoice.get("created"))
        paid_at = _ts(
            (stripe_invoice.get("status_transitions") or {}).get("paid_at"),
        )

        record = await self.repo.upsert(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            stripe_invoice_id=stripe_invoice_id,
            invoice_number=stripe_invoice.get("number"),
            amount_total=amount_total,
            amount_subtotal=amount_subtotal,
            amount_tax=amount_tax,
            currency=currency,
            status=status,
            period_start=period_start,
            period_end=period_end,
            issued_at=issued_at,
            paid_at=paid_at,
            pdf_url=stripe_invoice.get("invoice_pdf"),
            metadata_json={
                "lines_count": len(
                    (stripe_invoice.get("lines") or {}).get("data", []) or []
                ),
            },
        )
        LOGGER.info(
            "billing.invoice_upserted",
            invoice_id=str(record.id),
            stripe_invoice_id=stripe_invoice_id,
            status=status,
        )
        return record

    async def list_recent(self, tenant_id: UUID, *, limit: int = 6) -> list[Invoice]:
        return await self.repo.list_for_tenant(tenant_id, limit=limit)
