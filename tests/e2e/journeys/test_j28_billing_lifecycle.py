"""J28 — Billing Lifecycle journey (UPD-052 / spec 105).

End-to-end test crossing the full billing lifecycle:

1. Free workspace owner upgrades to Pro via embedded card form (Stripe test mode).
2. Pro workspace consumes overage; authorize-overage flow runs.
3. ``invoice.payment_failed`` triggers grace; day-7 fast-forward downgrades
   the workspace to Free.
4. Audit chain integrity verified by ``tools/verify_audit_chain.py``.

Skip-marked until the kind cluster + Stripe test-mode forwarder + Stripe CLI
listener are wired into the e2e CI matrix.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j28,
    pytest.mark.timeout(480),
    pytest.mark.skip(
        reason=(
            "J28 Billing Lifecycle journey — body lands during UPD-054 US2 "
            "implementation (specs/107-saas-e2e-journeys/tasks.md T020). "
            "Requires kind cluster + Stripe CLI listener + Stripe test-mode keys."
        )
    ),
]


def test_j28_billing_lifecycle() -> None:
    """Placeholder so pytest collection sees J28 in the journey suite."""
