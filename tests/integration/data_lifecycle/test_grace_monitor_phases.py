"""GraceMonitor phase advance — T041 cluster integration scaffold.

Verify the cron advances phase_1 jobs whose grace_ends_at <= now() to phase_2 +
dispatches the workspace cascade.

Skip-marked. Activates when ``make dev-up`` provides the stack.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "cluster integration test — requires make dev-up. "
        "Tracked under specs/104-data-lifecycle/tasks.md T041."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
