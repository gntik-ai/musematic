"""Repository for the ``payment_methods`` table (UPD-052)."""

from __future__ import annotations

from platform.billing.payment_methods.models import PaymentMethod
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentMethodsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_stripe_id(self, stripe_payment_method_id: str) -> PaymentMethod | None:
        result = await self.session.execute(
            select(PaymentMethod).where(
                PaymentMethod.stripe_payment_method_id == stripe_payment_method_id
            )
        )
        return result.scalar_one_or_none()

    async def get_default_for_workspace(
        self,
        tenant_id: UUID,
        workspace_id: UUID | None,
    ) -> PaymentMethod | None:
        stmt = select(PaymentMethod).where(
            PaymentMethod.tenant_id == tenant_id,
            PaymentMethod.workspace_id == workspace_id,
            PaymentMethod.is_default.is_(True),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_attached(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        stripe_payment_method_id: str,
        brand: str | None,
        last4: str | None,
        exp_month: int | None,
        exp_year: int | None,
        is_default: bool = False,
    ) -> PaymentMethod:
        existing = await self.get_by_stripe_id(stripe_payment_method_id)
        if existing is not None:
            existing.brand = brand
            existing.last4 = last4
            existing.exp_month = exp_month
            existing.exp_year = exp_year
            if is_default:
                existing.is_default = True
            await self.session.flush()
            return existing
        record = PaymentMethod(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            stripe_payment_method_id=stripe_payment_method_id,
            brand=brand,
            last4=last4,
            exp_month=exp_month,
            exp_year=exp_year,
            is_default=is_default,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def set_default(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        payment_method_id: UUID,
    ) -> None:
        # Unset previous default(s) within the (tenant, workspace) pair.
        await self.session.execute(
            update(PaymentMethod)
            .where(
                PaymentMethod.tenant_id == tenant_id,
                PaymentMethod.workspace_id == workspace_id,
                PaymentMethod.is_default.is_(True),
                PaymentMethod.id != payment_method_id,
            )
            .values(is_default=False)
        )
        await self.session.execute(
            update(PaymentMethod)
            .where(PaymentMethod.id == payment_method_id)
            .values(is_default=True)
        )
        await self.session.flush()
