from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID


class CostGovernanceService:
    def __init__(
        self,
        *,
        attribution_service: Any,
        chargeback_service: Any,
        budget_service: Any,
        forecast_service: Any,
        anomaly_service: Any,
        repository: Any,
    ) -> None:
        self.attribution_service = attribution_service
        self.chargeback_service = chargeback_service
        self.budget_service = budget_service
        self.forecast_service = forecast_service
        self.anomaly_service = anomaly_service
        self.repository = repository

    async def get_workspace_cost_summary(
        self,
        workspace_id: UUID,
        period_type: str = "monthly",
        period_start: datetime | None = None,
    ) -> dict[str, Any]:
        start = period_start or datetime.now(UTC) - timedelta(days=30)
        end = datetime.now(UTC)
        rows = await self.repository.aggregate_attributions(workspace_id, ["day"], start, end)
        total_cost_cents = sum(float(row.get("total_cost_cents") or 0) for row in rows)
        execution_count = len(rows)
        return {
            "total_cost_usd": round(total_cost_cents / 100, 4),
            "period_start": start,
            "period_end": end,
            "execution_count": execution_count,
            "avg_daily_cost_usd": round((total_cost_cents / 100) / max(len(rows), 1), 4),
            "period_type": period_type,
        }

    async def evaluate_thresholds(self, workspace_id: UUID | None = None) -> list[UUID]:
        if workspace_id is not None:
            return cast(list[UUID], await self.budget_service.evaluate_thresholds(workspace_id))
        crossed: list[UUID] = []
        for candidate in await self.repository.list_workspace_ids_with_costs():
            crossed.extend(await self.budget_service.evaluate_thresholds(candidate))
        return crossed

    async def handle_workspace_archived(self, workspace_id: UUID) -> None:
        # Cost rows are retained by default; this hook documents the ownership point.
        del workspace_id
