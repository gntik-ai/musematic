"""UPD-049 T069 — Source update notifies fork owners.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

Source agent re-approved; marketplace.source_updated event published; MarketplaceFanoutConsumer queries forks and delivers one AlertService.create_admin_alert per fork owner with type marketplace.source_updated and a body stating the fork has NOT been auto-updated.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t069_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
