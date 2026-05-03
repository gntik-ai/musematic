"""UPD-049 T028 — approve transitions.

Spec coverage: see specs/099-marketplace-scope/spec.md FR-016 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

Approve transitions pending_review → published; reviewed_at and reviewed_by_user_id are persisted; marketplace.approved followed by marketplace.published events are emitted; audit-chain entry recorded.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t028_placeholder() -> None:
    pytest.skip("Awaiting live-DB body wire-up — see module docstring.")
