"""UPD-049 T030 — rate limit refusal.

Spec coverage: see specs/099-marketplace-scope/spec.md FR-009 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

5 public submissions in 24 hours all succeed; the 6th returns HTTP 429 with code submission_rate_limit_exceeded and a Retry-After header; counter resets after the 24-hour sliding window passes.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T030 requires a live PostgreSQL fixture with migration 108 "
        "applied + Kafka + UPD-042 alert stub. Wire in the integration-test "
        "profile."
    ),
)


def test_t030_placeholder() -> None:
    pytest.fail(
        "Replace with the live-DB integration test described in the module "
        "docstring."
    )
