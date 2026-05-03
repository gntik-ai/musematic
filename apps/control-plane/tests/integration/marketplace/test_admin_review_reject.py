"""UPD-049 T029 — reject transitions + notification.

Spec coverage: see specs/099-marketplace-scope/spec.md FR-017 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

Reject without reason returns 422; reject with reason transitions to 'rejected'; marketplace.rejected event emitted; submitter receives a UPD-042 alert with the rejection reason.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t029_placeholder() -> None:
    pytest.skip("Awaiting live-DB body wire-up — see module docstring.")
