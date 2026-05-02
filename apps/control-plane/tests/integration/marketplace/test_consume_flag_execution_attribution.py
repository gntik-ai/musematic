"""UPD-049 T056 — Public-agent execution attributed to consumer tenant.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

An Acme user runs a public agent; the resulting execution's tenant_id is Acme (consumer), not the default tenant; cost-attribution row owned by Acme's billing scope.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T056 requires the live PostgreSQL + Kafka + AlertService fixture "
        "from the integration-test profile."
    ),
)


def test_t056_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
