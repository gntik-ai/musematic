"""UPD-049 T064 — Fork into tenant scope happy path.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

Acme user POSTs /api/v1/registry/agents/<source>/fork with target_scope=tenant; new agent profile created in Acme with marketplace_scope=tenant, review_status=draft, forked_from_agent_id set to source.id; source unchanged; marketplace.forked event emitted; audit-chain entry on Acme's tenant.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T064 requires the live PostgreSQL + Kafka + AlertService fixture "
        "from the integration-test profile."
    ),
)


def test_t064_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
