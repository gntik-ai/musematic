"""T082 — integration test scaffold for the Stripe webhook ingress.

Skip-marked. Requires ``make dev-up`` + the Stripe CLI listener forwarding
to the kind cluster's webhook endpoint (see quickstart.md § dev cluster
Stripe test mode).

When unskipped, this test:

1. Bootstraps a workspace with a Stripe customer record (Stripe test mode).
2. Calls ``stripe trigger customer.subscription.created`` from the Stripe CLI.
3. Asserts the FastAPI handler accepted the signed event (HTTP 200 +
   ``billing.subscription.created`` Kafka event observed).
4. Replays the same event id and asserts the second delivery returns
   ``already_processed`` without re-running side effects.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Integration test — requires make dev-up + Stripe CLI listener "
        "(BILLING_STRIPE_MODE=test). Tracked under specs/105-billing-payment-"
        "provider/tasks.md T082."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
