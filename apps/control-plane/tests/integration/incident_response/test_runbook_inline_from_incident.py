from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.incident_response.schemas import RunbookResponse, RunbookStatus
from platform.incident_response.services.incident_service import IncidentService
from uuid import uuid4

import pytest

from tests.integration.incident_response.support import (
    MemoryIncidentRepository,
    RecordingProducer,
    enabled_pagerduty,
)
from tests.unit.incident_response.support import make_incident


class RunbookLookup:
    def __init__(self, runbooks: dict[str, RunbookResponse]) -> None:
        self.runbooks = runbooks

    async def get_by_scenario(self, scenario: str) -> RunbookResponse | None:
        return self.runbooks.get(scenario)


@pytest.mark.asyncio
async def test_runbook_surfaces_inline_missing_and_unmapped_from_incident_detail() -> None:
    kafka_runbook = RunbookResponse(
        id=uuid4(),
        scenario="kafka_lag",
        title="Kafka lag",
        symptoms="Consumers are behind.",
        diagnostic_commands=[
            {"command": "kafka-consumer-groups.sh --describe", "description": "Check lag."}
        ],
        remediation_steps="Scale consumers.",
        escalation_path="Escalate to streaming on-call.",
        status=RunbookStatus.active,
        version=1,
        created_at=make_incident().triggered_at,
        updated_at=make_incident().triggered_at,
        updated_by=None,
        is_stale=False,
    )
    repo = MemoryIncidentRepository([enabled_pagerduty()])
    incident_with_runbook = make_incident(runbook_scenario="kafka_lag")
    incident_missing_runbook = make_incident(runbook_scenario="nonexistent")
    incident_unmapped = make_incident(runbook_scenario=None)
    repo.incidents = {
        incident_with_runbook.id: incident_with_runbook,
        incident_missing_runbook.id: incident_missing_runbook,
        incident_unmapped.id: incident_unmapped,
    }
    service = IncidentService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        redis_client=None,
        producer=RecordingProducer(),  # type: ignore[arg-type]
        provider_clients={},
        runbook_service=RunbookLookup({"kafka_lag": kafka_runbook}),  # type: ignore[arg-type]
    )

    detail = await service.get(incident_with_runbook.id)
    missing = await service.get(incident_missing_runbook.id)
    unmapped = await service.get(incident_unmapped.id)

    assert detail.runbook == kafka_runbook
    assert detail.runbook.symptoms
    assert detail.runbook.diagnostic_commands
    assert missing.runbook is None
    assert missing.runbook_authoring_link == "/operator/runbooks/new?scenario=nonexistent"
    assert unmapped.runbook_scenario_unmapped is True
    assert unmapped.runbook_authoring_link == "/operator/runbooks/new?scenario=new"
