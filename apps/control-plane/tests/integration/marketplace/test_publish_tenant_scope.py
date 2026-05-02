"""UPD-049 T024 — tenant publish (no review).

Spec coverage: see specs/099-marketplace-scope/spec.md FR-004 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

POST /api/v1/registry/agents/{id}/publish with scope='tenant' transitions review_status to 'published' immediately, the agent is visible to all workspaces in the publishing tenant via RLS, no review queue entry.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T024 requires a live PostgreSQL fixture with migration 108 "
        "applied + Kafka + UPD-042 alert stub. Wire in the integration-test "
        "profile."
    ),
)


def test_t024_placeholder() -> None:
    pytest.fail(
        "Replace with the live-DB integration test described in the module "
        "docstring."
    )
