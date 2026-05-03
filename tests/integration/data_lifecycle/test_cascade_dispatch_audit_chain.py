"""Cascade dispatch audit-chain integrity — T056 cluster integration scaffold.

Assert AuditChainService emits hash-linked entries for every cascade step +
chain verifies post-cascade.

Skip-marked. Activates when ``make dev-up`` provides the stack.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "cluster integration test — requires make dev-up. "
        "Tracked under specs/104-data-lifecycle/tasks.md T056."
    )
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
