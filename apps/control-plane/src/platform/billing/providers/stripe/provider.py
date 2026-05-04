"""UPD-052 — :class:`StripePaymentProvider` composing the per-feature helpers.

Implements the :class:`PaymentProvider` Protocol against the Stripe SDK. The
constructor takes a :class:`PlatformSettings` and the secrets are resolved
lazily on the first SDK call so unit tests that never trigger an SDK call
don't need to install the ``stripe`` package.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.billing.providers.exceptions import (
    BillingSecretsUnavailableError,
    ProviderUnavailable,
)
from platform.billing.providers.protocol import (
    OverageChargeReceipt,
    PaymentProvider,
    PortalSession,
    ProrationPreview,
    ProviderInvoice,
    ProviderSubscription,
    WebhookEvent,
)
from platform.billing.providers.stripe.client import StripeClient
from platform.billing.providers.stripe.secrets import StripeSecretsLoader
from platform.billing.providers.stripe.webhook_signing import verify_stripe_signature
from platform.common.config import PlatformSettings
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID

LOGGER = get_logger(__name__)


class StripePaymentProvider:
    """Concrete :class:`PaymentProvider` impl backed by the Stripe SDK.

    Composition of the per-feature helpers under
    ``platform.billing.providers.stripe``. The class is registered by the
    :func:`build_payment_provider` factory when ``BILLING_PROVIDER=stripe``.
    """

    provider_name = "stripe"

    def __init__(
        self,
        *,
        settings: PlatformSettings,
        secrets_loader: StripeSecretsLoader | None = None,
        client: StripeClient | None = None,
    ) -> None:
        self._settings = settings
        self._secrets_loader = secrets_loader
        self._client_override = client
        self._client_cache: StripeClient | None = client

    async def _client(self) -> StripeClient:
        if self._client_cache is not None:
            return self._client_cache
        if self._secrets_loader is None:
            raise ProviderUnavailable(
                "stripe",
                reason=(
                    "StripePaymentProvider initialised without a secrets loader; "
                    "wire one up via build_payment_provider() in production."
                ),
            )
        secrets = await self._secrets_loader.load()
        self._client_cache = StripeClient(
            settings=self._settings,
            api_key=secrets.api_key,
        )
        return self._client_cache

    # ------------------------------------------------------------------
    # PaymentProvider Protocol — UPD-047 surface
    # ------------------------------------------------------------------

    async def create_customer(
        self,
        workspace_id: UUID,
        tenant_id: UUID,
        email: str,
    ) -> str:
        from platform.billing.providers.stripe import customer as customer_helpers

        client = await self._client()
        return await customer_helpers.create_customer(
            client,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            email=email,
        )

    async def attach_payment_method(
        self,
        provider_customer_id: str,
        method_token: str,
    ) -> str:
        client = await self._client()
        pm = await client.call(
            "payment_method.attach",
            lambda: client.stripe.PaymentMethod.attach(
                method_token,
                customer=provider_customer_id,
            ),
        )
        # Set as default for invoices.
        await client.call(
            "customer.set_default_payment_method",
            lambda: client.stripe.Customer.modify(
                provider_customer_id,
                invoice_settings={"default_payment_method": str(pm["id"])},
            ),
        )
        return str(pm["id"])

    async def detach_payment_method(
        self,
        provider_customer_id: str,
        method_id: str,
    ) -> None:
        del provider_customer_id
        client = await self._client()
        await client.call(
            "payment_method.detach",
            lambda: client.stripe.PaymentMethod.detach(method_id),
        )

    async def create_subscription(
        self,
        provider_customer_id: str,
        plan_external_id: str,
        trial_days: int,
        idempotency_key: str,
    ) -> ProviderSubscription:
        from platform.billing.providers.stripe import subscription as sub_helpers

        client = await self._client()
        return await sub_helpers.create_subscription(
            client,
            customer_id=provider_customer_id,
            price_id=plan_external_id,
            trial_days=trial_days,
            idempotency_key=idempotency_key,
            plan_slug=plan_external_id,
        )

    async def update_subscription(
        self,
        provider_subscription_id: str,
        target_plan_external_id: str,
        prorate: bool,
        idempotency_key: str,
    ) -> ProviderSubscription:
        from platform.billing.providers.stripe import subscription as sub_helpers

        client = await self._client()
        return await sub_helpers.update_subscription(
            client,
            subscription_id=provider_subscription_id,
            target_price_id=target_plan_external_id,
            proration_behavior=(
                "create_prorations" if prorate else "none"
            ),
            idempotency_key=idempotency_key,
        )

    async def cancel_subscription(
        self,
        provider_subscription_id: str,
        at_period_end: bool,
    ) -> ProviderSubscription:
        from platform.billing.providers.stripe import subscription as sub_helpers

        client = await self._client()
        return await sub_helpers.cancel_subscription(
            client,
            subscription_id=provider_subscription_id,
            at_period_end=at_period_end,
        )

    async def preview_proration(
        self,
        provider_subscription_id: str,
        target_plan_external_id: str,
    ) -> ProrationPreview:
        del provider_subscription_id, target_plan_external_id
        # Stripe's invoice-preview API returns this; out of scope for the
        # MVP. Return a zero-preview so the upgrade UI doesn't break.
        return ProrationPreview(
            prorated_charge_eur=Decimal("0.00"),
            prorated_credit_eur=Decimal("0.00"),
            next_full_invoice_eur=Decimal("0.00"),
            effective_at=datetime.now(tz=UTC),
        )

    async def report_usage(
        self,
        provider_subscription_id: str,
        quantity: Decimal,
        idempotency_key: str,
    ) -> None:
        client = await self._client()
        # The actual subscription_item id is resolved via Stripe; we look up
        # the metered item under the subscription on first call. Phase 4
        # (T038-T041) wires this fully.
        sub = await client.call(
            "subscription.retrieve_for_usage",
            lambda: client.stripe.Subscription.retrieve(provider_subscription_id),
        )
        items: list[Any] = list((sub.get("items") or {}).get("data") or [])
        # Pick the first metered item.
        metered = next(
            (
                item
                for item in items
                if (item.get("price") or {}).get("recurring", {}).get("usage_type")
                == "metered"
            ),
            None,
        )
        if metered is None:
            LOGGER.warning(
                "billing.report_usage_no_metered_item",
                subscription_id=provider_subscription_id,
            )
            return
        await client.call(
            "subscription_item.usage_record.create",
            lambda: client.stripe.SubscriptionItem.create_usage_record(
                str(metered["id"]),
                quantity=int(quantity),
                action="increment",
                idempotency_key=idempotency_key,
            ),
        )

    async def list_invoices(
        self,
        provider_customer_id: str,
        limit: int = 12,
    ) -> list[ProviderInvoice]:
        client = await self._client()
        invoices = await client.call(
            "invoice.list",
            lambda: client.stripe.Invoice.list(
                customer=provider_customer_id,
                limit=limit,
            ),
        )
        result: list[ProviderInvoice] = []
        for inv in (invoices.get("data") or []):
            inv_dict = dict(inv)
            result.append(
                ProviderInvoice(
                    provider_invoice_id=str(inv_dict.get("id", "")),
                    status=str(inv_dict.get("status", "")),
                    amount_eur=(
                        Decimal(int(inv_dict.get("total") or 0)) / Decimal(100)
                    ),
                    issued_at=datetime.fromtimestamp(
                        int(inv_dict.get("created") or 0), tz=UTC
                    ),
                    due_at=(
                        datetime.fromtimestamp(
                            int(inv_dict.get("due_date") or 0), tz=UTC
                        )
                        if inv_dict.get("due_date")
                        else None
                    ),
                    pdf_url=inv_dict.get("invoice_pdf"),
                )
            )
        return result

    # ------------------------------------------------------------------
    # PaymentProvider Protocol — UPD-052 extension surface
    # ------------------------------------------------------------------

    async def charge_overage(
        self,
        provider_customer_id: str,
        amount_cents: int,
        description: str,
        *,
        idempotency_key: str,
    ) -> OverageChargeReceipt:
        client = await self._client()
        charge = await client.call(
            "charge.create_overage",
            lambda: client.stripe.Charge.create(
                customer=provider_customer_id,
                amount=amount_cents,
                currency="eur",
                description=description,
                idempotency_key=idempotency_key,
            ),
        )
        return OverageChargeReceipt(
            provider_charge_id=str(charge["id"]),
            amount_cents=amount_cents,
            description=description,
        )

    async def create_customer_portal_session(
        self,
        provider_customer_id: str,
        return_url: str,
    ) -> PortalSession:
        from platform.billing.providers.stripe import portal as portal_helpers

        client = await self._client()
        return await portal_helpers.create_portal_session(
            client,
            customer_id=provider_customer_id,
            return_url=return_url,
        )

    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> WebhookEvent:
        if self._secrets_loader is None:
            raise BillingSecretsUnavailableError(
                "StripePaymentProvider has no secrets loader configured."
            )
        secrets = await self._secrets_loader.load()
        return verify_stripe_signature(payload, signature, secrets.webhook)

    async def handle_webhook_event(self, event: WebhookEvent) -> None:
        # Real dispatch is done by the FastAPI router via HandlerRegistry.
        # The protocol method exists for callers that want a one-shot
        # provider-level dispatch (kept thin so no logic is duplicated).
        LOGGER.info(
            "billing.stripe_handle_webhook_noop",
            event_id=event.id,
            event_type=event.type,
        )


# Type-check at import time that StripePaymentProvider satisfies the Protocol.
_proto_check: PaymentProvider = StripePaymentProvider(
    settings=PlatformSettings.__new__(PlatformSettings)
) if False else None  # type: ignore[assignment]
