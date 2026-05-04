"""T083 — E2E webhook idempotency test (J32).

Skip-marked. Sends the same Stripe event id twice and asserts only one set
of side effects (one ``billing.subscription.created`` Kafka event, one
``processed_webhooks`` row, one local subscription row update).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "E2E test — requires kind cluster + Stripe test mode + Stripe CLI "
        "listener. Tracked under specs/105-billing-payment-provider/tasks.md "
        "T083 / J32."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
