"""UPD-049 T066 — Fork refused when at max_agents_per_workspace.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

When Acme is at its max_agents_per_workspace plan quota, fork returns HTTP 402 quota_exceeded; no fork row created; no Kafka event.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t066_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
