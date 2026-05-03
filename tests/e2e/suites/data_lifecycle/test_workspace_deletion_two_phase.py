"""Workspace deletion two-phase E2E — T040 E2E scaffold.

Skip-marked. Activates against a kind cluster brought up by ``make dev-up``.
The journey covers the full user path through the API + Kafka events
+ audit chain + downstream stores.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "E2E suite — requires make dev-up kind cluster. "
        "Tracked under specs/104-data-lifecycle/tasks.md T040."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
