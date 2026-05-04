from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.billing.providers.protocol import (
    OverageChargeReceipt,
    PortalSession,
    ProrationPreview,
    ProviderInvoice,
    ProviderSubscription,
    WebhookEvent,
)
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID

LOGGER = get_logger(__name__)


class StubPaymentProvider:
    provider_name = "stub"

    def __init__(self, logger: Any | None = None) -> None:
        self.logger = logger or LOGGER
        self.reported_usage: list[dict[str, object]] = []

    async def create_customer(self, workspace_id: UUID, tenant_id: UUID, email: str) -> str:
        digest = _stable_digest(str(workspace_id), str(tenant_id), email)
        return f"stub_cus_{digest[:24]}"

    async def attach_payment_method(self, provider_customer_id: str, method_token: str) -> str:
        digest = _stable_digest(provider_customer_id, method_token)
        return f"stub_pm_{digest[:24]}"

    async def detach_payment_method(self, provider_customer_id: str, method_id: str) -> None:
        self.logger.info(
            "billing.stub_payment_method_detached",
            provider_customer_id=provider_customer_id,
            method_id=method_id,
        )

    async def create_subscription(
        self,
        provider_customer_id: str,
        plan_external_id: str,
        trial_days: int,
        idempotency_key: str,
    ) -> ProviderSubscription:
        now = _now()
        period_end = _next_anniversary(now)
        trial_end = now + timedelta(days=trial_days) if trial_days > 0 else None
        return ProviderSubscription(
            provider_subscription_id=f"stub_sub_{_stable_digest(idempotency_key)[:24]}",
            status="trialing" if trial_days > 0 else "active",
            current_period_start=now,
            current_period_end=period_end,
            cancel_at_period_end=False,
            trial_end=trial_end,
            plan_external_id=plan_external_id,
        )

    async def update_subscription(
        self,
        provider_subscription_id: str,
        target_plan_external_id: str,
        prorate: bool,
        idempotency_key: str,
    ) -> ProviderSubscription:
        del prorate, idempotency_key
        now = _now()
        return ProviderSubscription(
            provider_subscription_id=provider_subscription_id,
            status="active",
            current_period_start=now,
            current_period_end=_next_anniversary(now),
            cancel_at_period_end=False,
            trial_end=None,
            plan_external_id=target_plan_external_id,
        )

    async def cancel_subscription(
        self,
        provider_subscription_id: str,
        at_period_end: bool,
    ) -> ProviderSubscription:
        now = _now()
        return ProviderSubscription(
            provider_subscription_id=provider_subscription_id,
            status="active" if at_period_end else "canceled",
            current_period_start=now,
            current_period_end=_next_anniversary(now),
            cancel_at_period_end=at_period_end,
            trial_end=None,
            plan_external_id="stub_cancelled",
        )

    async def preview_proration(
        self,
        provider_subscription_id: str,
        target_plan_external_id: str,
    ) -> ProrationPreview:
        del provider_subscription_id, target_plan_external_id
        return ProrationPreview(
            prorated_charge_eur=Decimal("0.00"),
            prorated_credit_eur=Decimal("0.00"),
            next_full_invoice_eur=Decimal("0.00"),
            effective_at=_now(),
        )

    async def report_usage(
        self,
        provider_subscription_id: str,
        quantity: Decimal,
        idempotency_key: str,
    ) -> None:
        call = {
            "provider_subscription_id": provider_subscription_id,
            "quantity": quantity,
            "idempotency_key": idempotency_key,
        }
        self.reported_usage.append(call)
        self.logger.info("billing.stub_usage_reported", **call)

    async def list_invoices(
        self,
        provider_customer_id: str,
        limit: int = 12,
    ) -> list[ProviderInvoice]:
        del provider_customer_id, limit
        return []

    async def charge_overage(
        self,
        provider_customer_id: str,
        amount_cents: int,
        description: str,
        *,
        idempotency_key: str,
    ) -> OverageChargeReceipt:
        del provider_customer_id
        digest = _stable_digest(idempotency_key)[:24]
        return OverageChargeReceipt(
            provider_charge_id=f"stub_ch_{digest}",
            amount_cents=amount_cents,
            description=description,
        )

    async def create_customer_portal_session(
        self,
        provider_customer_id: str,
        return_url: str,
    ) -> PortalSession:
        digest = _stable_digest(provider_customer_id, return_url)[:32]
        return PortalSession(
            url=f"https://stub.local/portal/{digest}",
            expires_at=_now() + timedelta(hours=1),
        )

    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> WebhookEvent:
        del signature
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("stub: payload is not valid JSON") from exc
        return WebhookEvent(
            id=str(decoded.get("id", "stub_evt")),
            type=str(decoded.get("type", "stub.event")),
            payload=decoded.get("data", {}).get("object", decoded),
            created_at=_now(),
            api_version=None,
            raw=payload,
        )

    async def handle_webhook_event(self, event: WebhookEvent) -> None:
        self.logger.info(
            "billing.stub_webhook_dispatched",
            event_id=event.id,
            event_type=event.type,
        )


def _stable_digest(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _next_anniversary(now: datetime) -> datetime:
    return now + timedelta(days=30)
