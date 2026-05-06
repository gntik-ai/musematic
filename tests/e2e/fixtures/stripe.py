"""UPD-054 (107) — Stripe test-mode client + webhook helpers.

Test-mode-only Stripe client for the SaaS-pass billing journeys (J28,
J32, J33, J34). Refuses to construct outside test mode (SC-007).
Wraps the existing ``stripe`` SDK + ``stripe-cli`` for webhook trigger
and resend.

Contract: specs/107-saas-e2e-journeys/contracts/stripe-fixture.md
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

import pytest

if TYPE_CHECKING:
    pass


__all__ = [
    "TestStripeCustomer",
    "TestSubscription",
    "LiveKeyDetectedError",
    "StripeCliMissingError",
    "WebhookReplayWindowExceededError",
    "StripeTestModeClient",
    "stripe_client",
]


WebhookEventType = Literal[
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "customer.subscription.trial_will_end",
    "customer.subscription.deleted",
    "customer.subscription.updated",
]


@dataclass(frozen=True)
class TestStripeCustomer:
    """Stripe test-mode customer handle bound to a workspace."""

    stripe_customer_id: str
    workspace_id: uuid.UUID
    test_clock_id: str | None
    last_payment_method_id: str | None


@dataclass(frozen=True)
class TestSubscription:
    """Snapshot of a Stripe subscription's user-visible state."""

    stripe_subscription_id: str
    workspace_id: uuid.UUID
    plan_id: str
    plan_version: int
    status: str
    period_start: datetime
    period_end: datetime


class LiveKeyDetectedError(RuntimeError):
    """Raised when the resolved API key prefix is ``sk_live_`` — refusal
    is the SC-007 hard guarantee against real-money charges.
    """


class StripeCliMissingError(RuntimeError):
    """Raised when ``stripe-cli`` is not on PATH but the journey needs it."""


class WebhookReplayWindowExceededError(RuntimeError):
    """Raised when the test attempts to ``stripe events resend`` against an
    event id older than Stripe's 7-day replay window.
    """


class StripeTestModeClient:
    """Thin wrapper around the ``stripe`` SDK constrained to test mode.

    Resolves the API key via ``SecretProvider``-style indirection (an
    env var inside the kind cluster, a Vault path in CI). Refuses to
    construct outside test mode. Redacts the key in ``__repr__``.
    """

    def __init__(
        self,
        *,
        api_key: str,
        webhook_secret: str | None = None,
    ) -> None:
        if not api_key.startswith("sk_test_"):
            raise LiveKeyDetectedError(
                "StripeTestModeClient refuses to construct with a non-test key"
            )
        self._api_key = api_key
        self._webhook_secret = webhook_secret
        self._test_clocks: dict[str, str] = {}  # customer_id -> test_clock_id

        # The stripe SDK is module-global; we set the API key here and
        # rely on test isolation by always passing customer ids explicitly.
        import stripe  # noqa: PLC0415 — lazy import keeps fixture lightweight

        self._stripe = stripe
        stripe.api_key = api_key

    def __repr__(self) -> str:  # noqa: D401
        return "<StripeTestModeClient api_key=***REDACTED***>"

    @classmethod
    def from_environment(cls) -> "StripeTestModeClient":
        """Construct from ``STRIPE_TEST_API_KEY`` / ``STRIPE_TEST_WEBHOOK_SECRET``
        env vars. Used by ``verify_no_orphans.py`` and other CLI helpers
        outside the pytest fixture lifecycle.
        """
        api_key = os.environ.get("STRIPE_TEST_API_KEY", "")
        if not api_key:
            raise LiveKeyDetectedError(
                "STRIPE_TEST_API_KEY env var not set"
            )
        return cls(
            api_key=api_key,
            webhook_secret=os.environ.get("STRIPE_TEST_WEBHOOK_SECRET"),
        )

    # -------------------- customer + subscription --------------------

    async def create_test_customer(
        self,
        *,
        workspace_id: uuid.UUID,
        email: str,
        payment_method_token: str = "pm_card_visa",
    ) -> TestStripeCustomer:
        """Create a Stripe test-mode Customer with the
        ``musematic_test=true`` metadata tag and attach the requested
        test payment method.
        """
        customer = await asyncio.to_thread(
            self._stripe.Customer.create,
            email=email,
            metadata={"musematic_test": "true", "workspace_id": str(workspace_id)},
            payment_method=payment_method_token,
            invoice_settings={"default_payment_method": payment_method_token},
        )
        return TestStripeCustomer(
            stripe_customer_id=customer.id,
            workspace_id=workspace_id,
            test_clock_id=None,
            last_payment_method_id=payment_method_token,
        )

    async def attach_payment_method(
        self,
        *,
        customer: TestStripeCustomer,
        payment_method_token: str,
    ) -> None:
        """Replace the default payment method on a test customer."""
        await asyncio.to_thread(
            self._stripe.Customer.modify,
            customer.stripe_customer_id,
            invoice_settings={"default_payment_method": payment_method_token},
        )

    async def create_subscription(
        self,
        *,
        customer: TestStripeCustomer,
        price_id: str,
        trial_period_days: int | None = None,
    ) -> TestSubscription:
        """Create a test-mode subscription; honours trial_period_days for J33."""
        kwargs: dict[str, Any] = {
            "customer": customer.stripe_customer_id,
            "items": [{"price": price_id}],
            "metadata": {"musematic_test": "true"},
        }
        if trial_period_days:
            kwargs["trial_period_days"] = trial_period_days
        sub = await asyncio.to_thread(self._stripe.Subscription.create, **kwargs)
        return TestSubscription(
            stripe_subscription_id=sub.id,
            workspace_id=customer.workspace_id,
            plan_id=price_id,
            plan_version=1,
            status=sub.status,
            period_start=datetime.utcfromtimestamp(sub.current_period_start),
            period_end=datetime.utcfromtimestamp(sub.current_period_end),
        )

    # -------------------- test clock --------------------

    async def advance_test_clock(
        self,
        *,
        customer: TestStripeCustomer,
        to: datetime,
    ) -> None:
        """Advance a Stripe Test Clock so trial expiry / period rollover
        fires deterministically. Lazily creates a clock per-customer
        and reuses it for the customer's lifetime.
        """
        clock_id = self._test_clocks.get(customer.stripe_customer_id)
        if clock_id is None:
            clock = await asyncio.to_thread(
                self._stripe.test_helpers.TestClock.create,
                frozen_time=int(to.timestamp()),
                name=f"e2e-clock-{customer.stripe_customer_id}",
            )
            clock_id = clock.id
            self._test_clocks[customer.stripe_customer_id] = clock_id
            return
        await asyncio.to_thread(
            self._stripe.test_helpers.TestClock.advance,
            clock_id,
            frozen_time=int(to.timestamp()),
        )

    # -------------------- webhook trigger / resend --------------------

    def _ensure_stripe_cli(self) -> str:
        path = shutil.which("stripe")
        if path is None:
            raise StripeCliMissingError(
                "stripe-cli not on PATH; CI installs it in the journey-tests job"
            )
        return path

    async def trigger_webhook(
        self,
        event_type: WebhookEventType,
        *,
        customer: TestStripeCustomer,
    ) -> str:
        """Run ``stripe trigger <event-type>`` and return the resulting
        Stripe event id so the journey can assert on it or replay it.
        """
        cli = self._ensure_stripe_cli()
        result = await asyncio.to_thread(
            subprocess.run,
            [cli, "trigger", event_type, "--api-key", self._api_key],
            check=True,
            capture_output=True,
            text=True,
        )
        # Parse the event id from the trigger output.
        for line in result.stdout.splitlines():
            if line.startswith("Trigger succeeded! Check dashboard for event details."):
                continue
            if "evt_test_" in line:
                # Best-effort extraction; format: "Setting up fixture ... evt_test_XXX"
                for token in line.split():
                    if token.startswith("evt_test_"):
                        return token.rstrip(".,;:'\"")
        # Fallback: query recent events for this customer's metadata.
        events = await asyncio.to_thread(
            self._stripe.Event.list,
            limit=5,
            type=event_type,
        )
        for event in events.auto_paging_iter():
            obj = event.data.object
            if getattr(obj, "metadata", None) and obj.metadata.get("musematic_test") == "true":
                return event.id
        raise RuntimeError(f"could not extract event id from stripe trigger output")

    async def resend_webhook(self, *, event_id: str) -> None:
        """Replay an already-issued Stripe event for the J32 idempotency test.

        The event MUST be from the SAME test run — replays past Stripe's
        7-day window are rejected with WebhookReplayWindowExceededError.
        """
        cli = self._ensure_stripe_cli()
        try:
            await asyncio.to_thread(
                subprocess.run,
                [cli, "events", "resend", event_id, "--api-key", self._api_key],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            if "older than" in output.lower() or "outside" in output.lower():
                raise WebhookReplayWindowExceededError(
                    f"event {event_id} is outside Stripe's 7-day replay window"
                ) from exc
            raise

    # -------------------- cleanup --------------------

    async def purge_test_customers(self) -> int:
        """Delete every Stripe test-mode customer carrying
        ``metadata.musematic_test=true``. Returns the count purged.
        """
        purged = 0
        customers = await asyncio.to_thread(
            self._stripe.Customer.search,
            query="metadata['musematic_test']:'true'",
            limit=100,
        )
        for customer in customers.auto_paging_iter():
            await asyncio.to_thread(self._stripe.Customer.delete, customer.id)
            purged += 1
        return purged


@pytest.fixture
async def stripe_client() -> AsyncIterator[StripeTestModeClient]:
    """Pytest fixture exposing a Stripe test-mode client.

    Reads ``STRIPE_TEST_API_KEY`` / ``STRIPE_TEST_WEBHOOK_SECRET`` from
    the environment (CI sets these from Vault before invoking pytest).
    Refuses to yield if the resolved key isn't a test-mode key.
    """
    client = StripeTestModeClient.from_environment()
    try:
        yield client
    finally:
        # Best-effort cleanup; ignore any one customer that resists deletion.
        try:
            await client.purge_test_customers()
        except Exception:  # pragma: no cover — cleanup must not mask the test failure
            pass
