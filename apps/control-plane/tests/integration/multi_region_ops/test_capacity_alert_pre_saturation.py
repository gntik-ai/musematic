from __future__ import annotations

from platform.multi_region_ops.services.capacity_service import CapacityService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.integration.multi_region_ops.support import (
    FakeAnalyticsService,
    FakeForecastService,
    RecordingIncidentService,
    RecordingIncidentTrigger,
    build_services,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_capacity_alert_fires_with_resolving_recommendation_link() -> None:
    workspace_id = uuid4()
    services = build_services(seeded_repository())
    signals = await services["capacity"].evaluate_saturation(workspace_id=workspace_id)

    assert services["incident_trigger"].signals
    signal = services["incident_trigger"].signals[0]
    assert signal.severity.value == "warning"
    assert signals[0].recommendation is not None
    assert signals[0].recommendation.link in {"/operator?panel=capacity", "/operator/regions/"}

    incident_service = RecordingIncidentService()

    class ClearedForecast(FakeForecastService):
        async def get_latest_forecast(self, workspace_id):
            return SimpleNamespace(
                workspace_id=workspace_id,
                forecast_cents=None,
                confidence_interval={"status": "ok", "points": 12},
            )

    clearing = CapacityService(
        settings=services["settings"],
        cost_governance_service=SimpleNamespace(forecast_service=ClearedForecast()),
        analytics_service=FakeAnalyticsService(),
        incident_trigger=RecordingIncidentTrigger(),
        incident_service=incident_service,  # type: ignore[arg-type]
    )
    await clearing.evaluate_saturation(workspace_id=workspace_id)

    assert incident_service.resolved
