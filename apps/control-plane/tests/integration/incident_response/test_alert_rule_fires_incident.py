from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from platform.analytics.forecast import ForecastEngine
from platform.analytics.recommendation import RecommendationEngine
from platform.analytics.service import AnalyticsService
from platform.common.config import PlatformSettings
from platform.incident_response.services.incident_service import IncidentService
from platform.incident_response.trigger_interface import (
    ServiceIncidentTrigger,
    register_incident_trigger,
    reset_incident_trigger,
)
from uuid import uuid4

import pytest

from tests.analytics_support import AnalyticsRepositoryStub, WorkspacesServiceStub
from tests.integration.incident_response.support import (
    MemoryIncidentRepository,
    MemoryRedis,
    RecordingProducer,
    RecordingProvider,
    enabled_pagerduty,
)


@pytest.mark.asyncio
async def test_alert_rule_fires_incident_external_alert_event_and_provider_payload() -> None:
    workspace_id = uuid4()
    provider = RecordingProvider()
    incident_repo = MemoryIncidentRepository([enabled_pagerduty()])
    incident_producer = RecordingProducer()
    incident_service = IncidentService(
        repository=incident_repo,  # type: ignore[arg-type]
        settings=_settings(),
        redis_client=MemoryRedis(),  # type: ignore[arg-type]
        producer=incident_producer,  # type: ignore[arg-type]
        provider_clients={"pagerduty": provider},
    )
    register_incident_trigger(ServiceIncidentTrigger(incident_service))
    try:
        analytics = AnalyticsService(
            repo=AnalyticsRepositoryStub(
                kpi_rows=[
                    {
                        "period": datetime.now(UTC),
                        "total_cost_usd": 60.0,
                        "execution_count": 3,
                        "avg_duration_ms": 10.0,
                        "avg_quality_score": 0.8,
                        "cost_per_quality": 75.0,
                    }
                ],
                workspace_ids=[workspace_id],
            ),
            cost_model_repo=object(),  # type: ignore[arg-type]
            workspaces_service=WorkspacesServiceStub([workspace_id]),  # type: ignore[arg-type]
            settings=_settings(),
            kafka_producer=RecordingProducer(),  # type: ignore[arg-type]
            recommendation_engine=RecommendationEngine(),
            forecast_engine=ForecastEngine(),
        )

        assert await analytics.check_budget_thresholds() == [workspace_id]
        await _drain(incident_service)
    finally:
        reset_incident_trigger()

    assert len(incident_repo.incidents) == 1
    assert len(incident_repo.alerts) == 1
    assert next(iter(incident_repo.alerts.values())).delivery_status == "delivered"
    assert incident_producer.events[0]["event_type"] == "incident.triggered"
    assert provider.created[0]["mapped_severity"] == "P3"
    assert provider.created[0]["incident"].condition_fingerprint.endswith(str(workspace_id))


def _settings() -> PlatformSettings:
    settings = PlatformSettings(ANALYTICS_BUDGET_THRESHOLD_USD=25.0)
    settings.incident_response.alert_rule_class_to_scenario["budget_threshold_crossed"] = (
        "s3_quota_breach"
    )
    return settings


async def _drain(service: IncidentService) -> None:
    while service._background_tasks:
        await asyncio.gather(*list(service._background_tasks))
