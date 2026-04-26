from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.cost_governance.clickhouse_repository import ClickHouseCostRepository
from platform.cost_governance.events import (
    CostForecastUpdatedPayload,
    CostGovernanceEventType,
    publish_cost_governance_event,
)
from platform.cost_governance.repository import CostGovernanceRepository
from platform.cost_governance.schemas import CostForecastResponse
from statistics import mean, pstdev
from typing import Any
from uuid import UUID, uuid4


class ForecastService:
    def __init__(
        self,
        *,
        repository: CostGovernanceRepository,
        clickhouse_repository: ClickHouseCostRepository | None,
        minimum_history_periods: int,
        default_currency: str,
        kafka_producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.clickhouse_repository = clickhouse_repository
        self.minimum_history_periods = minimum_history_periods
        self.default_currency = default_currency
        self.kafka_producer = kafka_producer

    async def compute_forecast(self, workspace_id: UUID) -> CostForecastResponse:
        period_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = (
            period_start.replace(year=period_start.year + 1, month=1)
            if period_start.month == 12
            else period_start.replace(month=period_start.month + 1)
        )
        history = await self._history(workspace_id)
        if len(history) < self.minimum_history_periods:
            row = await self.repository.insert_forecast(
                workspace_id=workspace_id,
                period_start=period_start,
                period_end=period_end,
                forecast_cents=None,
                confidence_interval={"status": "insufficient_history", "points": len(history)},
                currency=self.default_currency,
            )
            return CostForecastResponse.model_validate(row)
        values = [Decimal(str(item["total_cost_cents"])) for item in history]
        trimmed = _trim_outliers(values)
        avg = Decimal(str(mean([float(item) for item in trimmed])))
        volatility = Decimal(
            str(pstdev([float(item) for item in trimmed]) if len(trimmed) > 1 else 0)
        )
        forecast = (avg * Decimal(30)).quantize(Decimal("0.0001"))
        low = max(Decimal("0"), forecast - (volatility * Decimal(30)))
        high = forecast + (volatility * Decimal(30))
        row = await self.repository.insert_forecast(
            workspace_id=workspace_id,
            period_start=period_start,
            period_end=period_end,
            forecast_cents=forecast,
            confidence_interval={
                "status": "ok",
                "low_cents": str(low.quantize(Decimal("0.0001"))),
                "high_cents": str(high.quantize(Decimal("0.0001"))),
                "points": len(values),
            },
            currency=self.default_currency,
        )
        await publish_cost_governance_event(
            self.kafka_producer,
            CostGovernanceEventType.forecast_updated,
            CostForecastUpdatedPayload(
                forecast_id=row.id,
                workspace_id=workspace_id,
                period_start=row.period_start,
                period_end=row.period_end,
                forecast_cents=row.forecast_cents,
                computed_at=row.computed_at,
            ),
            CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4()),
        )
        return CostForecastResponse.model_validate(row)

    async def get_latest_forecast(self, workspace_id: UUID) -> CostForecastResponse | None:
        row = await self.repository.get_latest_forecast(workspace_id)
        if row is None:
            return None
        response = CostForecastResponse.model_validate(row)
        response.freshness_seconds = int((datetime.now(UTC) - row.computed_at).total_seconds())
        return response

    async def _history(self, workspace_id: UUID) -> list[dict[str, Any]]:
        if self.clickhouse_repository is not None:
            return await self.clickhouse_repository.query_workspace_history(
                workspace_id,
                max(self.minimum_history_periods, 30),
            )
        end = datetime.now(UTC)
        start = end - timedelta(days=30)
        rows = await self.repository.aggregate_attributions(workspace_id, ["day"], start, end)
        return rows


def _trim_outliers(values: list[Decimal]) -> list[Decimal]:
    if len(values) < 5:
        return values
    ordered = sorted(values)
    return ordered[1:-1]
