"""UPD-049 T054 — PATCH /admin/tenants/{id} feature_flags routing.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

Super admin PATCH with feature_flags.consume_public_marketplace=true on Enterprise tenant succeeds; audit-chain entry written; tenants.feature_flag_changed Kafka event published; resolver cache invalidated. Setting on default tenant returns 422. Setting unknown flag returns 422. Round-trip: setting back to false reverts.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T054 requires the live PostgreSQL + Kafka + AlertService fixture "
        "from the integration-test profile."
    ),
)


def test_t054_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
