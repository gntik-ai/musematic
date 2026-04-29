from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.incident_response.schemas import IncidentSeverity, IncidentSignal
from platform.incident_response.services.incident_service import IncidentService
from platform.incident_response.services.providers.base import ProviderError
from uuid import uuid4

import pytest

from tests.integration.incident_response.support import (
    MemoryIncidentRepository,
    MemoryRedis,
    RecordingProducer,
    RecordingProvider,
    enabled_pagerduty,
)


@pytest.mark.asyncio
async def test_provider_unreachable_queues_retry_then_delivers() -> None:
    provider = RecordingProvider()
    provider.error = ProviderError("provider unavailable", provider="pagerduty", retryable=True)
    settings = PlatformSettings()
    settings.incident_response.delivery_retry_initial_seconds = 1
    repo = MemoryIncidentRepository([enabled_pagerduty({"warning": "P3"})])
    service = IncidentService(
        repository=repo,  # type: ignore[arg-type]
        settings=settings,
        redis_client=MemoryRedis(),  # type: ignore[arg-type]
        producer=RecordingProducer(),  # type: ignore[arg-type]
        provider_clients={"pagerduty": provider},
    )

    await service.create_from_signal(
        IncidentSignal(
            alert_rule_class="budget_threshold_crossed",
            severity=IncidentSeverity.warning,
            title="Budget threshold crossed",
            description="Workspace crossed the configured budget threshold.",
            condition_fingerprint="budget:workspace:primary",
            related_event_ids=[uuid4()],
            runbook_scenario="s3_quota_breach",
        )
    )
    await _drain(service)

    alert = next(iter(repo.alerts.values()))
    assert alert.delivery_status == "pending"
    assert alert.attempt_count == 1
    assert alert.next_retry_at is not None

    provider.error = None
    await service.retry_due_alerts(datetime.now(UTC) + timedelta(seconds=5))

    assert alert.delivery_status == "delivered"
    assert alert.provider_reference is not None
    assert alert.attempt_count == 2


async def _drain(service: IncidentService) -> None:
    while service._background_tasks:
        await asyncio.gather(*list(service._background_tasks))
