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

pytestmark = pytest.mark.integration_live


def test_t024_placeholder() -> None:
    pytest.skip("Awaiting live-DB body wire-up — see module docstring.")
