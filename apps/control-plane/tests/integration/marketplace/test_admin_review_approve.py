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

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T028 requires a live PostgreSQL fixture with migration 108 "
        "applied + Kafka + UPD-042 alert stub. Wire in the integration-test "
        "profile."
    ),
)


def test_t028_placeholder() -> None:
    pytest.fail(
        "Replace with the live-DB integration test described in the module "
        "docstring."
    )
