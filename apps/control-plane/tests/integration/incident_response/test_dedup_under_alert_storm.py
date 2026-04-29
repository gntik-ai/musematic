from __future__ import annotations

import asyncio
from platform.common.config import PlatformSettings
from platform.incident_response.schemas import IncidentSeverity, IncidentSignal
from platform.incident_response.services.incident_service import IncidentService
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
async def test_dedup_under_alert_storm_pages_once_and_appends_all_events() -> None:
    provider = RecordingProvider()
    repo = MemoryIncidentRepository([enabled_pagerduty({"critical": "P1"})])
    service = IncidentService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        redis_client=MemoryRedis(),  # type: ignore[arg-type]
        producer=RecordingProducer(),  # type: ignore[arg-type]
        provider_clients={"pagerduty": provider},
    )
    event_ids = [uuid4() for _ in range(200)]

    for event_id in event_ids:
        await service.create_from_signal(
            IncidentSignal(
                alert_rule_class="kafka_lag",
                severity=IncidentSeverity.critical,
                title="Kafka lag",
                description="Lag storm",
                condition_fingerprint="kafka_lag:workspace:primary",
                related_event_ids=[event_id],
                runbook_scenario="kafka_lag",
            )
        )
    await _drain(service)

    incident = next(iter(repo.incidents.values()))
    assert len(repo.incidents) == 1
    assert len(repo.alerts) == 1
    assert len(incident.related_event_ids) == 200
    assert provider.created == [
        {
            "integration": repo.integrations[0],
            "incident": incident,
            "mapped_severity": "P1",
        }
    ]


async def _drain(service: IncidentService) -> None:
    while service._background_tasks:
        await asyncio.gather(*list(service._background_tasks))
