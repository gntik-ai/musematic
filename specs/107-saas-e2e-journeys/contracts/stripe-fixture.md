# Contract — `tests/e2e/fixtures/stripe.py`

## Purpose

Provide a Stripe-test-mode client and helpers used by the billing journeys (J28, J32, J33, J34) and any journey that needs to assert against Stripe-side state (subscription status, invoice line items, customer state).

## Hard guarantees

- **Test mode only.** `__init__` reads the API key via the existing `SecretProvider` and refuses to construct if the key prefix is `sk_live_`. SC-007 (zero real-money charges) is enforced at this layer.
- **No production data leakage.** Every customer the fixture creates carries `metadata.musematic_test=true`; the cleanup helper `purge_test_customers()` filters on that metadata key so manual operators can run it against a shared test account without risk.
- **Webhook signing is real.** Webhook replay uses `stripe-cli events resend` against a real Stripe-issued event id; signatures are computed by Stripe-cli with the live test-mode signing secret. The platform receives a signature exactly as it would in production.

## Public surface

```python
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

class StripeTestModeClient:
    """Thin wrapper around the stripe SDK constrained to test mode.

    Refuses to construct outside test mode; redacts api_token in __repr__.
    """

    def __init__(self, *, secret_provider: SecretProvider) -> None: ...

    # ------- customer + subscription lifecycle -------

    async def create_test_customer(
        self,
        *,
        workspace_id: UUID,
        email: str,
        payment_method_token: str = "pm_card_visa",  # Stripe test token
    ) -> TestStripeCustomer: ...

    async def attach_payment_method(
        self,
        *,
        customer: TestStripeCustomer,
        payment_method_token: str,                    # e.g. "pm_card_chargeDeclined"
    ) -> None: ...

    async def create_subscription(
        self,
        *,
        customer: TestStripeCustomer,
        price_id: str,
        trial_period_days: int | None = None,
    ) -> TestSubscription: ...

    # ------- clock advancement (J33 trial expiry, J28 grace) -------

    async def advance_test_clock(
        self,
        *,
        customer: TestStripeCustomer,
        to: datetime,
    ) -> None: ...

    # ------- webhook simulation (J28 invoice events, J32 idempotency) -------

    async def trigger_webhook(
        self,
        event_type: Literal[
            "invoice.payment_succeeded",
            "invoice.payment_failed",
            "customer.subscription.trial_will_end",
            "customer.subscription.deleted",
        ],
        *,
        customer: TestStripeCustomer,
    ) -> str:
        """Run `stripe trigger <event-type>` and return the resulting
        Stripe event id so the journey can assert on it later or replay it.
        """

    async def resend_webhook(self, *, event_id: str) -> None:
        """Run `stripe events resend <event-id>` for the J32 idempotency
        test. The event_id MUST come from a prior trigger_webhook call —
        replaying arbitrary ids from production-mode Stripe is forbidden.
        """

    # ------- cleanup -------

    async def purge_test_customers(self) -> int:
        """Delete every Stripe test-mode customer carrying
        metadata.musematic_test=true. Returns the count purged.
        Used by the SC-006 soak verifier.
        """
```

## Behaviour notes

### Stripe Test Clock

Stripe's "Test Clocks" are the canonical way to simulate time advancement in test mode. The fixture creates one clock per `TestStripeCustomer` (lazily, when `advance_test_clock` is first called) and reuses it for the lifetime of the customer. Clock destruction happens automatically when the customer is deleted. Concurrent clock-advance against the same customer is serialised via a `pytest-xdist` `filelock` keyed on the customer id (see research R7).

### Webhook trigger vs. webhook resend

`trigger_webhook` produces a *new* event id; the platform processes it as it would any production event. `resend_webhook` issues a duplicate of an already-processed event — used exclusively for J32 (Stripe webhook idempotency) to prove the dedupe TTL holds.

### Failure modes

| Exception | When | Handler expectation |
|---|---|---|
| `LiveKeyDetectedError` | API key prefix is `sk_live_` | Fixture refuses to construct; the run aborts with a clear message |
| `StripeCliMissingError` | `stripe-cli` is not on PATH | Fixture refuses to operate; CI installs `stripe-cli` in a setup step (Phase 1 task) |
| `WebhookReplayWindowExceededError` | Event id is older than 7 days | Stripe rejects the resend; the fixture surfaces this with a hint (J32 should always replay events from the same test run) |

## Cross-references

- The platform-side webhook handler is `apps/control-plane/src/platform/billing/webhooks/stripe_router.py` (UPD-052).
- Subscription state machine: `specs/105-billing-payment-provider/data-model.md`.
- Event types relevant to journeys are catalogued in `apps/control-plane/src/platform/billing/webhooks/events.py`.
