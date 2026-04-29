from __future__ import annotations

import json
from platform.common.config import PlatformSettings
from platform.incident_response.exceptions import RunbookConcurrentEditError
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
async def test_runbook_concurrent_edit_returns_current_version_and_audits_successes() -> None:
    repo = RunbookRepository()
    audit = AuditRecorder()
    service = RunbookService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        audit_chain_service=audit,
    )
    actor = uuid4()
    runbook = await service.create(_create_payload(), updated_by=actor)

    updated = await service.update(
        runbook.id,
        RunbookUpdateRequest(expected_version=1, title="Admin A update"),
        updated_by=actor,
    )
    with pytest.raises(RunbookConcurrentEditError) as exc_info:
        await service.update(
            runbook.id,
            RunbookUpdateRequest(expected_version=1, title="Admin B stale update"),
            updated_by=actor,
        )

    assert updated.version == 2
    assert exc_info.value.current_version == 2
    assert [payload["action"] for payload in audit.payloads] == [
        "runbook.created",
        "runbook.updated",
    ]
