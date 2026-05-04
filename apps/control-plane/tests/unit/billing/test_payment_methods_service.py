"""T023 unit tests — payment_methods service idempotent upsert + set_default."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from platform.billing.payment_methods.models import PaymentMethod
from platform.billing.payment_methods.service import PaymentMethodsService


class FakeRepo:
    def __init__(self) -> None:
        self.rows: dict[str, PaymentMethod] = {}
        self.default_set_calls: list[tuple[UUID, UUID | None, UUID]] = []

    async def get_by_stripe_id(self, stripe_payment_method_id: str) -> PaymentMethod | None:
        return self.rows.get(stripe_payment_method_id)

    async def get_default_for_workspace(
        self,
        tenant_id: UUID,
        workspace_id: UUID | None,
    ) -> PaymentMethod | None:
        for pm in self.rows.values():
            if (
                pm.tenant_id == tenant_id
                and pm.workspace_id == workspace_id
                and pm.is_default
            ):
                return pm
        return None

    async def upsert_attached(self, **kwargs: Any) -> PaymentMethod:
        existing = self.rows.get(kwargs["stripe_payment_method_id"])
        if existing is not None:
            for k, v in kwargs.items():
                setattr(existing, k, v)
            return existing
        pm = PaymentMethod(**kwargs)
        pm.id = uuid4()
        self.rows[kwargs["stripe_payment_method_id"]] = pm
        return pm

    async def set_default(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        payment_method_id: UUID,
    ) -> None:
        self.default_set_calls.append((tenant_id, workspace_id, payment_method_id))
        for pm in self.rows.values():
            if (
                pm.tenant_id == tenant_id
                and pm.workspace_id == workspace_id
                and pm.is_default
                and pm.id != payment_method_id
            ):
                pm.is_default = False
        for pm in self.rows.values():
            if pm.id == payment_method_id:
                pm.is_default = True


@pytest.mark.asyncio
async def test_record_attached_inserts_new_row() -> None:
    service = PaymentMethodsService(FakeRepo())  # type: ignore[arg-type]
    tenant = uuid4()
    workspace = uuid4()

    pm = await service.record_attached(
        tenant_id=tenant,
        workspace_id=workspace,
        stripe_payment_method_id="pm_test_1",
        brand="visa",
        last4="4242",
        exp_month=12,
        exp_year=2030,
        is_default=True,
    )

    assert pm.brand == "visa"
    assert pm.last4 == "4242"
    assert pm.is_default is True


@pytest.mark.asyncio
async def test_record_attached_idempotent_upsert() -> None:
    repo = FakeRepo()
    service = PaymentMethodsService(repo)  # type: ignore[arg-type]
    tenant = uuid4()

    first = await service.record_attached(
        tenant_id=tenant,
        workspace_id=None,
        stripe_payment_method_id="pm_dup",
        brand="visa",
        last4="0001",
        exp_month=1,
        exp_year=2030,
        is_default=False,
    )
    second = await service.record_attached(
        tenant_id=tenant,
        workspace_id=None,
        stripe_payment_method_id="pm_dup",
        brand="mastercard",
        last4="9999",
        exp_month=2,
        exp_year=2031,
        is_default=True,
    )

    assert first.id == second.id
    assert second.brand == "mastercard"
    assert second.last4 == "9999"
    assert second.is_default is True
    assert len(repo.rows) == 1


@pytest.mark.asyncio
async def test_set_default_swaps_old_default() -> None:
    repo = FakeRepo()
    service = PaymentMethodsService(repo)  # type: ignore[arg-type]
    tenant = uuid4()
    workspace = uuid4()

    old = await service.record_attached(
        tenant_id=tenant,
        workspace_id=workspace,
        stripe_payment_method_id="pm_old",
        brand="visa",
        last4="0001",
        exp_month=1,
        exp_year=2030,
        is_default=True,
    )
    new = await service.record_attached(
        tenant_id=tenant,
        workspace_id=workspace,
        stripe_payment_method_id="pm_new",
        brand="visa",
        last4="0002",
        exp_month=2,
        exp_year=2031,
        is_default=False,
    )

    await service.set_default(
        tenant_id=tenant,
        workspace_id=workspace,
        payment_method_id=new.id,
    )

    assert (tenant, workspace, new.id) in repo.default_set_calls
    refreshed_old = repo.rows["pm_old"]
    refreshed_new = repo.rows["pm_new"]
    assert refreshed_old.is_default is False
    assert refreshed_new.is_default is True
