"""DPA upload + ClamAV integration — T082 cluster integration scaffold.

Clean upload, virus-positive (EICAR), scanner-unreachable failure modes against
a live ClamAV daemon.

Skip-marked. Activates when ``make dev-up`` provides the stack.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "cluster integration test — requires make dev-up. "
        "Tracked under specs/104-data-lifecycle/tasks.md T082."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
