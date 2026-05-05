"""J33 — Trial-to-Paid Conversion journey (UPD-052 / spec 105 T098).

Drives a workspace through a 7-day trial, observes the
``customer.subscription.trial_will_end`` notification, then asserts the
trial converts to active on day 7 and the first invoice is paid via the
on-file card.

Skip-marked until the kind cluster Stripe forwarder is wired in CI.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j33,
    pytest.mark.timeout(480),
    pytest.mark.skip(
        reason=(
            "J33 Trial-to-Paid Conversion journey — body lands during UPD-054 "
            "US2 (specs/107-saas-e2e-journeys/tasks.md T022). Requires kind "
            "cluster + Stripe test mode + Test Clock fast-forward."
        )
    ),
]


def test_j33_trial_to_paid_conversion() -> None:
    """Placeholder so pytest collection sees J33 in the journey suite."""
