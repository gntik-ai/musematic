"""UPD-049 T065 — Fork into workspace scope happy path.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

Acme user POSTs /fork with target_scope=workspace + target_workspace_id; fork lives in that workspace only; marketplace_scope=workspace.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t065_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
