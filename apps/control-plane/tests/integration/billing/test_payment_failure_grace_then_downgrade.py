"""T044 — integration test scaffold for the day-7 grace expiry downgrade.

Skip-marked. Requires ``make dev-up`` + APScheduler running in the worker
profile. The integration suite drives an ``invoice.payment_failed`` Stripe
event, fast-forwards wall clock by 8 days, and asserts the workspace plan
flipped to Free with the cleanup-flagging behaviour.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Integration test — requires make dev-up + worker profile + simulated "
        "wall-clock fast-forward. Tracked under specs/105-billing-payment-"
        "provider/tasks.md T044."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
