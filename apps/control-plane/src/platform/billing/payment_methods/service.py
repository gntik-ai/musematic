"""Service for the ``payment_methods`` BC (UPD-052)."""

from __future__ import annotations

from platform.billing.payment_methods.models import PaymentMethod
from platform.billing.payment_methods.repository import PaymentMethodsRepository
from platform.common.logging import get_logger
from uuid import UUID

LOGGER = get_logger(__name__)


class PaymentMethodsService:
    def __init__(self, repository: PaymentMethodsRepository) -> None:
        self.repo = repository

    async def record_attached(
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
        record = await self.repo.upsert_attached(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            stripe_payment_method_id=stripe_payment_method_id,
            brand=brand,
            last4=last4,
            exp_month=exp_month,
            exp_year=exp_year,
            is_default=is_default,
        )
        LOGGER.info(
            "billing.payment_method_recorded",
            payment_method_id=str(record.id),
            tenant_id=str(tenant_id),
            stripe_payment_method_id=stripe_payment_method_id,
            brand=brand,
            last4=last4,
        )
        return record

    async def set_default(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        payment_method_id: UUID,
    ) -> None:
        await self.repo.set_default(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            payment_method_id=payment_method_id,
        )
        LOGGER.info(
            "billing.payment_method_default_set",
            payment_method_id=str(payment_method_id),
            tenant_id=str(tenant_id),
        )
