"""UPD-049 T048 — Enterprise public-publish refused at API.

Spec coverage: see specs/099-marketplace-scope/spec.md FR-011 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

Enterprise-tenant user POSTs to /publish with scope='public_default_tenant'; response is HTTP 403 with code public_scope_not_allowed_for_enterprise; no audit-chain entry; no rate-limit token consumed; review queue is unaffected.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T048 requires a live PostgreSQL fixture with migration 108 "
        "applied + Kafka + UPD-042 alert stub. Wire in the integration-test "
        "profile."
    ),
)


def test_t048_placeholder() -> None:
    pytest.fail(
        "Replace with the live-DB integration test described in the module "
        "docstring."
    )
