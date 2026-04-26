from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.cost_governance.services.budget_service import BudgetService, period_bounds
from uuid import UUID, uuid4

import pytest


@dataclass
class BudgetRow:
    workspace_id: UUID
    period_type: str
    budget_cents: int
    hard_cap_enabled: bool = True
    admin_override_enabled: bool = True
    soft_alert_thresholds: list[int] = field(default_factory=lambda: [50, 80, 100])
    id: UUID = field(default_factory=uuid4)


class Repo:
    def __init__(self, budget: BudgetRow, spend: Decimal) -> None:
        self.budget = budget
        self.spend = spend

    async def get_active_budget(self, workspace_id: UUID, period_type: str) -> BudgetRow | None:
        if workspace_id == self.budget.workspace_id and period_type == self.budget.period_type:
            return self.budget
        return None

    async def period_spend(
        self,
        workspace_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        del workspace_id, period_start, period_end
        return self.spend


class AtomicRedis:
    def __init__(self) -> None:
        self.client = self
        self.values: dict[str, bytes] = {}
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        return None

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        del ttl
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def script_load(self, source: str) -> str:
        del source
        return "sha-budget"

    async def evalsha(self, sha: str, key_count: int, *args: str) -> list[str | int]:
        del sha, key_count
        return await self.eval("", 1, *args)

    async def eval(self, source: str, key_count: int, *args: str) -> list[str | int]:
        del source, key_count
        key, increment, limit, ttl = args
        del ttl
        async with self.lock:
            current = Decimal(self.values.get(key, b"0").decode())
            projected = current + Decimal(increment)
            if projected > Decimal(limit):
                return [0, str(current)]
            self.values[key] = str(projected).encode()
            return [1, str(projected)]


@pytest.mark.asyncio
async def test_concurrent_starts_never_admit_more_than_budget_allows() -> None:
    workspace_id = uuid4()
    budget = BudgetRow(workspace_id=workspace_id, period_type="monthly", budget_cents=100)
    redis = AtomicRedis()
    service = BudgetService(
        repository=Repo(budget, Decimal("80")),  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
        settings=PlatformSettings(feature_cost_hard_caps=True),
    )
    period_start, _period_end = period_bounds("monthly")
    redis.values[service._counter_key(workspace_id, "monthly", period_start)] = b"80"

    async def admit() -> bool:
        result = await service.check_budget_for_start(workspace_id, Decimal("2"))
        return result.allowed

    outcomes = await asyncio.gather(*[admit() for _ in range(20)])

    assert sum(outcomes) == 10
    assert outcomes.count(False) == 10
