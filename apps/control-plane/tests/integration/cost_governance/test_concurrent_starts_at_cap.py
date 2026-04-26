from __future__ import annotations

import asyncio
from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.cost_governance.services.budget_service import BudgetService, period_bounds
from uuid import uuid4

import pytest

from tests.unit.cost_governance.test_concurrent_admit import AtomicRedis, BudgetRow, Repo


@pytest.mark.asyncio
async def test_fifty_concurrent_starts_admit_exactly_twenty_when_twenty_fit() -> None:
    workspace_id = uuid4()
    budget = BudgetRow(workspace_id=workspace_id, period_type="monthly", budget_cents=100)
    redis = AtomicRedis()
    service = BudgetService(
        repository=Repo(budget, Decimal("60")),  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
        settings=PlatformSettings(feature_cost_hard_caps=True),
    )
    period_start, _period_end = period_bounds("monthly")
    redis.values[service._counter_key(workspace_id, "monthly", period_start)] = b"60"

    async def start() -> bool:
        result = await service.check_budget_for_start(workspace_id, Decimal("2"))
        return result.allowed

    outcomes = await asyncio.gather(*[start() for _ in range(50)])

    assert sum(outcomes) == 20
    assert outcomes.count(False) == 30
    counter_key = service._counter_key(workspace_id, "monthly", period_start)
    assert Decimal(redis.values[counter_key].decode()) == Decimal("100")
