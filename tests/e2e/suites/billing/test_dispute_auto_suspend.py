"""T093 — E2E test for charge.dispute.created auto-suspend."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "E2E test — requires kind cluster + Stripe test mode. Tracked under "
        "specs/105-billing-payment-provider/tasks.md T093."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
