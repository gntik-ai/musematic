from __future__ import annotations

import json
from platform.common.config import PlatformSettings
from platform.incident_response.schemas import RunbookUpdateRequest
from platform.incident_response.services.runbook_service import RunbookService
from uuid import uuid4

import pytest

from tests.unit.incident_response.test_runbook_service import RunbookRepository, _create_payload


class AuditRecorder:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def append(self, event_id: object, source: str, canonical_payload: bytes) -> None:
        del event_id
        assert source == "incident_response.runbooks"
        self.payloads.append(json.loads(canonical_payload))


@pytest.mark.asyncio
async def test_runbook_mutations_emit_audit_without_runbook_content_text() -> None:
    repo = RunbookRepository()
    audit = AuditRecorder()
    service = RunbookService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        audit_chain_service=audit,
    )
    actor = uuid4()

    created = await service.create(_create_payload(), updated_by=actor)
    await service.update(
        created.id,
        RunbookUpdateRequest(expected_version=1, title="Updated Kafka lag"),
        updated_by=actor,
    )
    await service.retire(created.id, updated_by=actor)

    assert [payload["action"] for payload in audit.payloads] == [
        "runbook.created",
        "runbook.updated",
        "runbook.retired",
    ]
    for payload in audit.payloads:
        assert payload["runbook_id"] == str(created.id)
        assert payload["updated_by"] == str(actor)
        assert "version" in payload
        assert "Consumers are behind" not in json.dumps(payload)
