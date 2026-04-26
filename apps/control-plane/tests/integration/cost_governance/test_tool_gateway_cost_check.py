from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.cost_governance.constants import BLOCK_REASON_COST_BUDGET
from platform.cost_governance.exceptions import OverrideAlreadyRedeemedError
from platform.cost_governance.services.budget_service import BudgetService
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.unit.cost_governance.test_concurrent_admit import AtomicRedis


@dataclass
class BudgetRow:
    workspace_id: UUID
    period_type: str = "monthly"
    budget_cents: int = 100
    hard_cap_enabled: bool = True
    admin_override_enabled: bool = True
    soft_alert_thresholds: list[int] = field(default_factory=lambda: [50, 80, 100])
    id: UUID = field(default_factory=uuid4)


class GatewayRepo:
    def __init__(self, budget: BudgetRow, spend: Decimal) -> None:
        self.budget = budget
        self.spend = spend
        self.override_hashes: set[str] = set()

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

    async def create_override_record(self, **kwargs: Any) -> object:
        self.override_hashes.add(str(kwargs["token_hash"]))
        return object()

    async def mark_override_redeemed(self, token_hash: str, redeemed_by: UUID | None) -> object:
        del token_hash, redeemed_by
        return object()


class GatewayRedis(AtomicRedis):
    async def eval(self, source: str, key_count: int, *args: str) -> Any:
        if len(args) == 3:
            token_key, redeemed_key, ttl = args
            if redeemed_key in self.values:
                return "already_redeemed"
            value = self.values.get(token_key)
            if value is None:
                return None
            self.values.pop(token_key, None)
            self.values[redeemed_key] = b"1"
            del ttl
            return value
        return await super().eval(source, key_count, *args)


@pytest.mark.asyncio
async def test_gateway_hard_cap_blocks_then_single_override_admits_next_start() -> None:
    workspace_id = uuid4()
    repo = GatewayRepo(BudgetRow(workspace_id=workspace_id), Decimal("99"))
    service = BudgetService(
        repository=repo,  # type: ignore[arg-type]
        redis_client=GatewayRedis(),  # type: ignore[arg-type]
        settings=PlatformSettings(feature_cost_hard_caps=True),
    )

    admitted = await service.check_budget_for_start(workspace_id, Decimal("1"))
    blocked = await service.check_budget_for_start(workspace_id, Decimal("1"))
    override = await service.issue_override(workspace_id, uuid4(), "incident response")
    overridden = await service.check_budget_for_start(
        workspace_id,
        Decimal("1"),
        override_token=override.token,
    )

    assert admitted.allowed is True
    assert blocked.allowed is False
    assert blocked.block_reason == BLOCK_REASON_COST_BUDGET
    assert blocked.override_endpoint == f"/api/v1/costs/workspaces/{workspace_id}/budget/override"
    assert overridden.allowed is True
    with pytest.raises(OverrideAlreadyRedeemedError):
        await service.check_budget_for_start(
            workspace_id,
            Decimal("1"),
            override_token=override.token,
        )
