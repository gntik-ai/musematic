"""J34 — Cancellation and Reactivation journey (UPD-052 / spec 105 T098).

Pro workspace cancels via the in-app cancel form, retains Pro features
through the period, reactivates before period-end, and confirms no
service interruption.

Skip-marked until the kind cluster Stripe forwarder is wired in CI.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "J34 Cancellation and Reactivation journey — requires kind cluster "
        "+ Stripe test mode. Tracked under specs/105-billing-payment-"
        "provider/tasks.md T098 / J34."
    )
)


def test_j34_cancellation_reactivation() -> None:
    """Placeholder so pytest collection sees J34 in the journey suite."""
