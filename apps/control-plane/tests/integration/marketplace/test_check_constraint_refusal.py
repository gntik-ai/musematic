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

pytestmark = pytest.mark.integration_live


def test_t049_placeholder() -> None:
    pytest.skip("Awaiting live-DB body wire-up — see module docstring.")
