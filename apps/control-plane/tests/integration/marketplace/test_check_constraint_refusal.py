"""UPD-049 T049 — DB CHECK refuses direct INSERT.

Spec coverage: see specs/099-marketplace-scope/spec.md FR-012 and
specs/099-marketplace-scope/quickstart.md scenarios.

This stub is a placeholder pending the live-DB integration test fixture
that the orchestrator's integration-test profile must wire (PostgreSQL
with migration 108 applied + Kafka consumer + UPD-042 AlertService stub).

When wired, this test MUST verify:

Direct INSERT into registry_agent_profiles via the platform-staff session with marketplace_scope='public_default_tenant' AND tenant_id=<acme_tenant_uuid> raises CheckViolation referencing registry_agent_profiles_public_only_default_tenant.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T049 requires a live PostgreSQL fixture with migration 108 "
        "applied + Kafka + UPD-042 alert stub. Wire in the integration-test "
        "profile."
    ),
)


def test_t049_placeholder() -> None:
    pytest.fail(
        "Replace with the live-DB integration test described in the module "
        "docstring."
    )
