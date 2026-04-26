from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from platform.cost_governance.services.forecast_service import ForecastService
from typing import Any
from uuid import UUID, uuid4

import pytest


@dataclass
class ForecastRow:
    workspace_id: UUID
    period_start: datetime
    period_end: datetime
    forecast_cents: Decimal | None
    confidence_interval: dict[str, Any]
    currency: str
    id: UUID = field(default_factory=uuid4)
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class Repo:
    def __init__(self) -> None:
        self.rows: list[ForecastRow] = []

    async def insert_forecast(self, **kwargs: Any) -> ForecastRow:
        row = ForecastRow(**kwargs)
        self.rows.append(row)
        return row

    async def get_latest_forecast(self, workspace_id: UUID) -> ForecastRow | None:
        rows = [row for row in self.rows if row.workspace_id == workspace_id]
        return rows[-1] if rows else None

    async def aggregate_attributions(
        self,
        workspace_id: UUID,
        group_by: list[str],
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Decimal]]:
        del workspace_id, group_by, since, until
        return [{"total_cost_cents": Decimal("5")} for _ in range(4)]


class History:
    def __init__(self, values: list[Decimal]) -> None:
        self.values = values

    async def query_workspace_history(
        self,
        workspace_id: UUID,
        periods: int,
    ) -> list[dict[str, Decimal]]:
        del workspace_id, periods
        return [{"total_cost_cents": value} for value in self.values]


@pytest.mark.asyncio
async def test_insufficient_history_returns_low_confidence_without_value() -> None:
    repo = Repo()
    service = ForecastService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=History([Decimal("10"), Decimal("11")]),  # type: ignore[arg-type]
        minimum_history_periods=4,
        default_currency="USD",
    )

    response = await service.compute_forecast(uuid4())

    assert response.forecast_cents is None
    assert response.confidence_interval["status"] == "insufficient_history"


@pytest.mark.asyncio
async def test_steady_history_forecast_matches_expected() -> None:
    service = ForecastService(
        repository=Repo(),  # type: ignore[arg-type]
        clickhouse_repository=History([Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10")]),  # type: ignore[arg-type]
        minimum_history_periods=4,
        default_currency="USD",
    )

    response = await service.compute_forecast(uuid4())

    assert response.forecast_cents == Decimal("300.0000")
    assert response.confidence_interval["status"] == "ok"
    assert response.confidence_interval["low_cents"] == "300.0000"


@pytest.mark.asyncio
async def test_single_extreme_outlier_is_trimmed_and_volatility_widens_range() -> None:
    service = ForecastService(
        repository=Repo(),  # type: ignore[arg-type]
        clickhouse_repository=History(
            [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10"), Decimal("100")]
        ),  # type: ignore[arg-type]
        minimum_history_periods=4,
        default_currency="USD",
    )

    response = await service.compute_forecast(uuid4())

    assert response.forecast_cents == Decimal("300.0000")
    assert Decimal(response.confidence_interval["high_cents"]) >= response.forecast_cents


@pytest.mark.asyncio
async def test_forecast_fallback_history_and_latest_none() -> None:
    repo = Repo()
    service = ForecastService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=None,
        minimum_history_periods=4,
        default_currency="USD",
    )
    workspace_id = uuid4()

    assert await service.get_latest_forecast(workspace_id) is None
    response = await service.compute_forecast(workspace_id)
    latest = await service.get_latest_forecast(workspace_id)

    assert response.forecast_cents == Decimal("150.0000")
    assert latest is not None
    assert latest.freshness_seconds >= 0
