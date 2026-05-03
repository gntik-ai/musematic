"""UPD-049 T026 — review queue listing.

Spec coverage: see specs/099-marketplace-scope/spec.md FR-013 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

GET /api/v1/admin/marketplace-review/queue returns only review_status='pending_review' rows; cursor pagination correct; FIFO sort (oldest first); claimed_by + unclaimed filters work.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t026_placeholder() -> None:
    pytest.skip("Awaiting live-DB body wire-up — see module docstring.")
