"""UPD-049 T025 — public publish full flow.

Spec coverage: see specs/099-marketplace-scope/spec.md FR-008/016 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

Default-tenant user submits with marketing metadata; review_status transitions to 'pending_review'; queue entry exists; super admin approves; review_status → 'published'; second default-tenant user sees the agent in marketplace search.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T025 requires a live PostgreSQL fixture with migration 108 "
        "applied + Kafka + UPD-042 alert stub. Wire in the integration-test "
        "profile."
    ),
)


def test_t025_placeholder() -> None:
    pytest.fail(
        "Replace with the live-DB integration test described in the module "
        "docstring."
    )
