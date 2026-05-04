"""T046 — E2E test for grace-window payment recovery."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "E2E test — requires kind cluster + Stripe test mode. Tracked under "
        "specs/105-billing-payment-provider/tasks.md T046."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
