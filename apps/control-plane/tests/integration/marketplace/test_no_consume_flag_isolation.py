"""UPD-049 T060 — Default-deny: Globex without flag sees no public agents.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

A Globex user (no consume flag) calls marketplace search and /registry/agents/<public_id> — search returns zero marketplace_scope='public_default_tenant' rows; direct GET returns 404 (existence is hidden, not 403).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t060_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
