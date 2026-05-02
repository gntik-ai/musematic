"""UPD-049 T068 — Fork of invisible source returns 404.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

Globex user (no consume flag) attempts to fork a public agent ID; POST /fork returns 404 source_agent_not_visible; no fork row created.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,
    reason=(
        "T068 requires the live PostgreSQL + Kafka + AlertService fixture "
        "from the integration-test profile."
    ),
)


def test_t068_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
