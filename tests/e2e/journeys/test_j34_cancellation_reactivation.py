"""J34 — Cancellation and Reactivation journey (UPD-052 / spec 105 T098).

Pro workspace cancels via the in-app cancel form, retains Pro features
through the period, reactivates before period-end, and confirms no
service interruption.

Skip-marked until the kind cluster Stripe forwarder is wired in CI.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j34,
    pytest.mark.timeout(480),
    pytest.mark.skip(
        reason=(
            "J34 Cancellation and Reactivation journey — body lands during "
            "UPD-054 US2 (specs/107-saas-e2e-journeys/tasks.md T023). "
            "Requires kind cluster + Stripe test mode."
        )
    ),
]


def test_j34_cancellation_reactivation() -> None:
    """Placeholder so pytest collection sees J34 in the journey suite."""
