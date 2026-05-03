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

pytestmark = pytest.mark.integration_live


def test_t025_placeholder() -> None:
    pytest.skip("Awaiting live-DB body wire-up — see module docstring.")
