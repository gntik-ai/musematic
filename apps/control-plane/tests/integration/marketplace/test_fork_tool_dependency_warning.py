"""UPD-049 T067 — Fork surfaces missing tool dependencies.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

Source agent depends on tools not registered in consumer's tenant; fork succeeds (201); response includes tool_dependencies_missing array naming the unregistered tools; existing tools NOT in the array.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t067_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
