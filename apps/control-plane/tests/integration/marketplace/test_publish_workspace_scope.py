"""UPD-049 T023 — workspace publish (no review).

Spec coverage: see specs/099-marketplace-scope/spec.md FR-004 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

POST /api/v1/registry/agents/{id}/publish with scope='workspace' transitions review_status to 'published' immediately, no row appears in the review queue, marketplace.published Kafka event emitted, audit-chain entry recorded.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T023 requires a live PostgreSQL fixture with migration 108 "
        "applied + Kafka + UPD-042 alert stub. Wire in the integration-test "
        "profile."
    ),
)


def test_t023_placeholder() -> None:
    pytest.fail(
        "Replace with the live-DB integration test described in the module "
        "docstring."
    )
