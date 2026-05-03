"""UPD-049 T027 — claim semantics.

Spec coverage: see specs/099-marketplace-scope/spec.md FR-014/015 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

Claim is idempotent for the same reviewer (re-claiming returns 200); a different reviewer attempting to claim a held row receives 409 review_already_claimed; release returns the row to the unclaimed pool; re-claim by anyone after release succeeds.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t027_placeholder() -> None:
    pytest.skip("Awaiting live-DB body wire-up — see module docstring.")
