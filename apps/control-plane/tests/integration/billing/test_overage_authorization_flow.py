"""T036 — integration test for the overage authorize flow."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Integration test — requires make dev-up + Stripe test mode. Tracked "
        "under specs/105-billing-payment-provider/tasks.md T036."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
