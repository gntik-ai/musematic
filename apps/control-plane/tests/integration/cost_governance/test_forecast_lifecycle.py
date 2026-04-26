from __future__ import annotations

from decimal import Decimal
from platform.cost_governance.services.forecast_service import ForecastService
from uuid import uuid4

import pytest

from tests.unit.cost_governance.test_forecast_service import History, Repo


@pytest.mark.asyncio
async def test_forecast_lifecycle_records_insufficient_then_fresh_forecast() -> None:
    workspace_id = uuid4()
    repo = Repo()
    insufficient = ForecastService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=History([Decimal("10")]),  # type: ignore[arg-type]
        minimum_history_periods=4,
        default_currency="USD",
    )
    low_confidence = await insufficient.compute_forecast(workspace_id)

    sufficient = ForecastService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=History(
            [Decimal("10"), Decimal("12"), Decimal("11"), Decimal("13")]
        ),  # type: ignore[arg-type]
        minimum_history_periods=4,
        default_currency="USD",
    )
    forecast = await sufficient.compute_forecast(workspace_id)
    latest = await sufficient.get_latest_forecast(workspace_id)

    assert low_confidence.confidence_interval["status"] == "insufficient_history"
    assert forecast.forecast_cents is not None
    assert latest is not None
    assert latest.freshness_seconds is not None
