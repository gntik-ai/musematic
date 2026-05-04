"""T024 unit tests — invoices service idempotent upsert."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from platform.billing.invoices.models import Invoice
from platform.billing.invoices.service import InvoicesService


class FakeRepo:
    def __init__(self) -> None:
        self.rows: dict[str, Invoice] = {}

    async def get_by_stripe_id(self, stripe_invoice_id: str) -> Invoice | None:
        return self.rows.get(stripe_invoice_id)

    async def list_for_tenant(self, tenant_id: object, *, limit: int = 20) -> list[Invoice]:
        del tenant_id, limit
        return list(self.rows.values())

    async def upsert(self, **kwargs: Any) -> Invoice:
        existing = self.rows.get(kwargs["stripe_invoice_id"])
        if existing is not None:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            return existing
        row = Invoice(**kwargs)
        row.id = uuid4()
        self.rows[kwargs["stripe_invoice_id"]] = row
        return row


@pytest.mark.asyncio
async def test_upsert_from_stripe_creates_new_row_with_eur_amounts() -> None:
    service = InvoicesService(FakeRepo())  # type: ignore[arg-type]

    invoice = await service.upsert_from_stripe(
        tenant_id=uuid4(),
        subscription_id=uuid4(),
        stripe_invoice={
            "id": "in_test_1",
            "number": "INV-0001",
            "currency": "eur",
            "status": "paid",
            "total": 2420,  # cents
            "subtotal": 2000,
            "tax": 420,
            "created": 1_750_000_000,
            "period_start": 1_749_900_000,
            "period_end": 1_752_500_000,
            "status_transitions": {"paid_at": 1_750_005_000},
            "invoice_pdf": "https://files.stripe.com/test.pdf",
            "lines": {"data": [{}, {}]},
        },
    )

    assert invoice.amount_total == Decimal("24.20")
    assert invoice.amount_tax == Decimal("4.20")
    assert invoice.currency == "EUR"
    assert invoice.status == "paid"
    assert invoice.pdf_url == "https://files.stripe.com/test.pdf"
    assert invoice.metadata_json["lines_count"] == 2


@pytest.mark.asyncio
async def test_upsert_from_stripe_is_idempotent() -> None:
    repo = FakeRepo()
    service = InvoicesService(repo)  # type: ignore[arg-type]
    tenant = uuid4()
    subscription = uuid4()

    first = await service.upsert_from_stripe(
        tenant_id=tenant,
        subscription_id=subscription,
        stripe_invoice={
            "id": "in_test_dup",
            "currency": "eur",
            "status": "open",
            "total": 1000,
            "subtotal": 1000,
            "tax": 0,
        },
    )
    second = await service.upsert_from_stripe(
        tenant_id=tenant,
        subscription_id=subscription,
        stripe_invoice={
            "id": "in_test_dup",
            "currency": "eur",
            "status": "paid",
            "total": 1000,
            "subtotal": 1000,
            "tax": 0,
        },
    )

    assert first.id == second.id
    assert second.status == "paid"
    assert len(repo.rows) == 1


@pytest.mark.asyncio
async def test_upsert_from_stripe_rejects_payload_without_id() -> None:
    service = InvoicesService(FakeRepo())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="missing 'id'"):
        await service.upsert_from_stripe(
            tenant_id=uuid4(),
            subscription_id=uuid4(),
            stripe_invoice={"currency": "eur", "status": "open"},
        )


@pytest.mark.asyncio
async def test_list_recent_returns_repo_rows() -> None:
    repo = FakeRepo()
    service = InvoicesService(repo)  # type: ignore[arg-type]
    await service.upsert_from_stripe(
        tenant_id=uuid4(),
        subscription_id=uuid4(),
        stripe_invoice={
            "id": "in_test_list",
            "currency": "eur",
            "status": "paid",
            "total": 5000,
            "subtotal": 5000,
            "tax": 0,
        },
    )
    rows = await service.list_recent(uuid4(), limit=10)
    assert len(rows) == 1
