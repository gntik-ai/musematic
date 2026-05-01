from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class ProviderSubscription:
    provider_subscription_id: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    trial_end: datetime | None
    plan_external_id: str


@dataclass(frozen=True)
class ProrationPreview:
    prorated_charge_eur: Decimal
    prorated_credit_eur: Decimal
    next_full_invoice_eur: Decimal
    effective_at: datetime


@dataclass(frozen=True)
class ProviderInvoice:
    provider_invoice_id: str
    status: str
    amount_eur: Decimal
    issued_at: datetime
    due_at: datetime | None
    pdf_url: str | None


@runtime_checkable
class PaymentProvider(Protocol):
    async def create_customer(self, workspace_id: UUID, tenant_id: UUID, email: str) -> str:
        """Create a provider customer and return its provider ID."""

    async def attach_payment_method(self, provider_customer_id: str, method_token: str) -> str:
        """Attach a payment method and return its provider ID."""

    async def detach_payment_method(self, provider_customer_id: str, method_id: str) -> None:
        """Detach and void a payment method."""

    async def create_subscription(
        self,
        provider_customer_id: str,
        plan_external_id: str,
        trial_days: int,
        idempotency_key: str,
    ) -> ProviderSubscription:
        """Create a provider subscription."""

    async def update_subscription(
        self,
        provider_subscription_id: str,
        target_plan_external_id: str,
        prorate: bool,
        idempotency_key: str,
    ) -> ProviderSubscription:
        """Update a provider subscription's target plan."""

    async def cancel_subscription(
        self,
        provider_subscription_id: str,
        at_period_end: bool,
    ) -> ProviderSubscription:
        """Cancel immediately or at period end."""

    async def preview_proration(
        self,
        provider_subscription_id: str,
        target_plan_external_id: str,
    ) -> ProrationPreview:
        """Preview provider-side proration."""

    async def report_usage(
        self,
        provider_subscription_id: str,
        quantity: Decimal,
        idempotency_key: str,
    ) -> None:
        """Report metered usage."""

    async def list_invoices(
        self,
        provider_customer_id: str,
        limit: int = 12,
    ) -> list[ProviderInvoice]:
        """List recent invoices."""
