"""Default tenant deletion refused — T057 cluster integration scaffold.

Default tenant deletion request returns 409 default_tenant_cannot_be_deleted.

Skip-marked. Activates when ``make dev-up`` provides the stack.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "cluster integration test — requires make dev-up. "
        "Tracked under specs/104-data-lifecycle/tasks.md T057."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
