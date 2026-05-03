"""Article 28 evidence package — T093 cluster integration scaffold.

Generate the package, assert all 6 components present, manifest hashes match the actual content.

Skip-marked. Activates when ``make dev-up`` provides the stack.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "cluster integration test — requires make dev-up. "
        "Tracked under specs/104-data-lifecycle/tasks.md T093."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
