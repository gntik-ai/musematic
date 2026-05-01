# Contract — `PaymentProvider` Protocol

**Owner**: `apps/control-plane/src/platform/billing/providers/protocol.py`
**Constitutional rule**: SaaS-8 / SaaS-17 / AD-28 — bounded contexts call `payment_provider.x()`, never Stripe APIs directly.

## Protocol shape

```python
from typing import Protocol, runtime_checkable
from decimal import Decimal
from uuid import UUID
from datetime import datetime

@runtime_checkable
class PaymentProvider(Protocol):
    """Abstract payment-provider interface used by SubscriptionService.

    UPD-047 ships a StubPaymentProvider implementing this Protocol with deterministic
    return values and no external side effects. UPD-052 adds StripePaymentProvider as
    the production implementation. Future migration to Paddle / LemonSqueezy means a
    new Protocol implementation, not a business-logic rewrite.
    """

    async def create_customer(
        self,
        workspace_id: UUID,
        tenant_id: UUID,
        email: str,
    ) -> str:
        """Create a customer record at the payment provider; return the provider customer ID."""

    async def attach_payment_method(
        self,
        provider_customer_id: str,
        method_token: str,
    ) -> str:
        """Attach a payment method to the customer; return the provider method ID."""

    async def detach_payment_method(
        self,
        provider_customer_id: str,
        method_id: str,
    ) -> None:
        """Detach (and void) a payment method."""

    async def create_subscription(
        self,
        provider_customer_id: str,
        plan_external_id: str,
        trial_days: int,
        idempotency_key: str,
    ) -> ProviderSubscription:
        """Create a subscription at the provider for the given plan."""

    async def update_subscription(
        self,
        provider_subscription_id: str,
        target_plan_external_id: str,
        prorate: bool,
        idempotency_key: str,
    ) -> ProviderSubscription:
        """Change a subscription's plan; provider handles proration if prorate=True."""

    async def cancel_subscription(
        self,
        provider_subscription_id: str,
        at_period_end: bool,
    ) -> ProviderSubscription:
        """Cancel a subscription. at_period_end=True schedules cancellation; False is immediate."""

    async def preview_proration(
        self,
        provider_subscription_id: str,
        target_plan_external_id: str,
    ) -> ProrationPreview:
        """Compute the prorated charge/credit for a hypothetical mid-period change."""

    async def report_usage(
        self,
        provider_subscription_id: str,
        quantity: Decimal,
        idempotency_key: str,
    ) -> None:
        """Report metered usage (overage minutes) to the provider for billing."""

    async def list_invoices(
        self,
        provider_customer_id: str,
        limit: int = 12,
    ) -> list[ProviderInvoice]:
        """List recent invoices for the customer."""
```

## Companion dataclasses

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ProviderSubscription:
    provider_subscription_id: str
    status: str                    # provider's native status string; mapped to local status by SubscriptionService
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
    status: str                    # "paid", "open", "uncollectible", "void"
    amount_eur: Decimal
    issued_at: datetime
    due_at: datetime | None
    pdf_url: str | None
```

## Implementations

### `StubPaymentProvider` (this feature, UPD-047)

Behavioural contract:

- `create_customer` returns `f"stub_cus_{uuid4().hex[:24]}"`.
- `attach_payment_method` / `detach_payment_method` log and return success.
- `create_subscription` returns a `ProviderSubscription` with `status="trialing"` (if `trial_days > 0`) or `"active"`, period boundaries computed from `now()` and the local plan version's `quota_period_anchor`.
- `update_subscription` returns the new state.
- `cancel_subscription` flips `cancel_at_period_end` or sets `status="canceled"`.
- `preview_proration` returns `ProrationPreview(prorated_charge_eur=Decimal("0.00"), …)` — the stub never actually computes proration; this is the "free" experience until UPD-052.
- `report_usage` is a no-op that logs the call so test infrastructure can assert it was called.
- `list_invoices` returns an empty list.

The stub is deterministic and side-effect-free (modulo logs); E2E suites use it without any external dependency.

### `StripePaymentProvider` (UPD-052)

Implements the same Protocol with real Stripe SDK calls. The `plan_external_id` passed to Stripe is the Stripe Price ID; UPD-052 owns the mapping from local `(plan_id, version)` to Stripe Price IDs (a separate `stripe_price_mappings` table is added by UPD-052). Idempotency keys are propagated to Stripe.

## Selection at startup

`apps/control-plane/src/platform/main.py` selects the implementation based on `PlatformSettings.payment_provider`:

```python
if settings.payment_provider == "stub":
    payment_provider = StubPaymentProvider()
elif settings.payment_provider == "stripe":
    payment_provider = StripePaymentProvider(api_key=secret_provider.get(...))
```

Default in non-production profiles is `stub`. Production overrides to `stripe` once UPD-052 lands.

## Error contract

The Protocol does NOT declare exception types — implementations raise `PaymentProviderError` (and subclasses) defined in `apps/control-plane/src/platform/billing/providers/exceptions.py`. SubscriptionService catches and re-raises as the appropriate domain exception (e.g., `UpgradeFailedError`).

## Test contract

`apps/control-plane/tests/unit/billing/providers/test_stub_provider.py`:

- `StubPaymentProvider` matches the `PaymentProvider` Protocol per `runtime_checkable` `isinstance(stub, PaymentProvider)`.
- All methods are deterministic across repeated calls with the same inputs.
- `create_customer` returns distinct IDs for different `workspace_id`s.
- `report_usage` records the call (assertable via injected logger).
