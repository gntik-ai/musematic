"""T045 — E2E test for the day-7 grace expiry downgrade flow."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "E2E test — requires kind cluster + Stripe test mode + simulated "
        "wall-clock fast-forward. Tracked under specs/105-billing-payment-"
        "provider/tasks.md T045."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
