from __future__ import annotations

import json
from datetime import timedelta
from platform.common.config import PlatformSettings
from platform.incident_response.schemas import TimelineSourceCoverage
from platform.incident_response.services.post_mortem_service import PostMortemService
from uuid import uuid4

import pytest

from tests.integration.incident_response.support import MemoryIncidentRepository, RecordingAudit
from tests.unit.incident_response.support import make_incident


@pytest.mark.asyncio
async def test_post_mortem_distribution_surfaces_partial_failure_and_audits_shape_only() -> None:
    incident = make_incident(status="resolved")
    incident.resolved_at = incident.triggered_at + timedelta(minutes=5)
    repo = MemoryIncidentRepository()
    repo.incidents[incident.id] = incident
    audit = RecordingAudit()
    service = PostMortemService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        timeline_assembler=EmptyAssembler(),  # type: ignore[arg-type]
        alert_service=NotificationStub(failing="bad@example.com"),
        audit_chain_service=audit,
    )
    post_mortem = await service.start(incident.id, by_user_id=uuid4())

    distributed = await service.distribute(
        post_mortem.id,
        ["one@example.com", "bad@example.com", "two@example.com"],
    )

    assert distributed.status == "distributed"
    assert distributed.distribution_list == [
        {"recipient": "one@example.com", "outcome": "delivered"},
        {"recipient": "bad@example.com", "outcome": "failed:inactive recipient"},
        {"recipient": "two@example.com", "outcome": "delivered"},
    ]
    audit_payloads = [json.loads(entry[2]) for entry in audit.entries]
    distribution_audit = audit_payloads[-1]
    assert distribution_audit["action"] == "post_mortem.distributed"
    assert distribution_audit["recipient_count"] == 3
    assert distribution_audit["failed_count"] == 1
    assert "bad@example.com" not in json.dumps(distribution_audit)


class EmptyAssembler:
    async def assemble(self, **kwargs: object) -> tuple[list[object], TimelineSourceCoverage]:
        del kwargs
        return [], TimelineSourceCoverage()


class NotificationStub:
    def __init__(self, *, failing: str) -> None:
        self.failing = failing

    async def send_post_mortem(self, *, recipient: str) -> None:
        if recipient == self.failing:
            raise RuntimeError("inactive recipient")
