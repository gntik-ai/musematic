"""T065 — E2E test for reactivation during cancellation_pending."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "E2E test — requires kind cluster + Stripe test mode. Tracked under "
        "specs/105-billing-payment-provider/tasks.md T065."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
