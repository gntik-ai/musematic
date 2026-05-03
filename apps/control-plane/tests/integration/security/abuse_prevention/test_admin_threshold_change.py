"""UPD-050 — test_admin_threshold_change (integration_live spec).

Body to be filled in once the orchestrator's `make integration-test` harness
runs against the live-DB+Kafka+Redis fixtures from feature 071. The
acceptance criteria for this scenario are documented in
`specs/103-abuse-prevention/spec.md` § Success Criteria and
`specs/103-abuse-prevention/quickstart.md`.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


async def test_admin_threshold_change_placeholder() -> None:
    pytest.skip(
        "Awaiting live-DB body wire-up — see module docstring."
    )
