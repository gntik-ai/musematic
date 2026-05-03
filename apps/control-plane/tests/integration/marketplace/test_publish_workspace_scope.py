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

pytestmark = pytest.mark.integration_live


def test_t023_placeholder() -> None:
    pytest.skip("Awaiting live-DB body wire-up — see module docstring.")
