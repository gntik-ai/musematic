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

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T027 requires a live PostgreSQL fixture with migration 108 "
        "applied + Kafka + UPD-042 alert stub. Wire in the integration-test "
        "profile."
    ),
)


def test_t027_placeholder() -> None:
    pytest.fail(
        "Replace with the live-DB integration test described in the module "
        "docstring."
    )
