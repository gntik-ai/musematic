from __future__ import annotations

from uuid import uuid4

import pytest

from tests.integration.multi_region_ops.support import build_services, seeded_repository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_capacity_overview_marks_insufficient_history() -> None:
    services = build_services(seeded_repository(), insufficient_history=True)

    signals = await services["capacity"].get_capacity_overview(workspace_id=uuid4())

    assert signals
    assert {signal.confidence.value for signal in signals} == {"insufficient_history"}
    assert all(signal.recommendation is None for signal in signals)
