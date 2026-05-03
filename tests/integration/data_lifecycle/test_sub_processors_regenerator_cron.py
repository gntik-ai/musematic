"""Sub-processors regenerator cron — T071 cluster integration scaffold.

Edit triggers regenerator cron — ConfigMap snapshot updates + UPD-077 fanout to
verified subscribers.

Skip-marked. Activates when ``make dev-up`` provides the stack.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "cluster integration test — requires make dev-up. "
        "Tracked under specs/104-data-lifecycle/tasks.md T071."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
