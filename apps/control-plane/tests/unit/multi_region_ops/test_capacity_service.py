from __future__ import annotations

from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.multi_region_ops.services.capacity_service import (
    CapacityService,
    capacity_fingerprint,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest


class FakeForecastService:
    async def get_latest_forecast(self, workspace_id):
        return SimpleNamespace(
            workspace_id=workspace_id,
            forecast_cents=Decimal("1200.00"),
            confidence_interval={"status": "ok", "points": 6},
        )


class FakeCostGovernance:
    def __init__(self) -> None:
        self.forecast_service = FakeForecastService()


class FakeIncidentTrigger:
    def __init__(self) -> None:
        self.signals = []

    async def fire(self, signal):
        self.signals.append(signal)
        return SimpleNamespace(incident_id=uuid4())


@pytest.mark.asyncio
async def test_capacity_service_composes_forecast_and_routes_alert() -> None:
    trigger = FakeIncidentTrigger()
    service = CapacityService(
        settings=PlatformSettings(),
        cost_governance_service=FakeCostGovernance(),
        incident_trigger=trigger,
    )
    workspace_id = uuid4()

    signals = await service.evaluate_saturation(workspace_id=workspace_id)

    assert {signal.resource_class for signal in signals} >= {"compute", "model_tokens"}
    assert all(signal.projection["source"] == "cost_governance" for signal in signals)
    assert trigger.signals
    assert trigger.signals[0].condition_fingerprint == capacity_fingerprint(
        signals[0].resource_class,
        str(workspace_id),
    )
