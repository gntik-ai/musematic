from __future__ import annotations

from datetime import timedelta

import pytest

from tests.integration.multi_region_ops.support import (
    build_services,
    make_plan,
    now,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_stale_failover_plan_remains_visible() -> None:
    repository = seeded_repository()
    services = build_services(repository)
    stale = make_plan(tested_at=now() - timedelta(days=120))
    repository.plans[stale.id] = stale

    plans = await services["failover"].list_plans()

    assert plans == [stale]
    assert services["failover"].is_stale(stale) is True
