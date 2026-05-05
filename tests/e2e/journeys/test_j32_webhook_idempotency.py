"""J32 — Stripe Webhook Idempotency journey (UPD-052 / spec 105 T098).

Sends the same Stripe event id twice (via ``stripe events resend``) and
asserts only one set of side effects. Validates research R3's two-layer
idempotency strategy under real concurrent retries.

Skip-marked until the kind cluster Stripe forwarder is wired in CI.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j32,
    pytest.mark.timeout(480),
    pytest.mark.skip(
        reason=(
            "J32 Webhook Idempotency journey — body lands during UPD-054 US2 "
            "(specs/107-saas-e2e-journeys/tasks.md T021). Requires kind cluster "
            "+ Stripe CLI listener."
        )
    ),
]


def test_j32_webhook_idempotency() -> None:
    """Placeholder so pytest collection sees J32 in the journey suite."""
