from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.incident_response.exceptions import PostMortemOnOpenIncidentError
from platform.incident_response.schemas import TimelineSourceCoverage
from platform.incident_response.services.post_mortem_service import PostMortemService
from uuid import uuid4

import pytest

from tests.integration.incident_response.support import MemoryIncidentRepository
from tests.unit.incident_response.support import make_incident


@pytest.mark.asyncio
async def test_post_mortem_on_open_incident_rejected_then_idempotent_after_resolve() -> None:
    incident = make_incident(status="open")
    repo = MemoryIncidentRepository()
    repo.incidents[incident.id] = incident
    service = PostMortemService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        timeline_assembler=EmptyAssembler(),  # type: ignore[arg-type]
    )

    with pytest.raises(PostMortemOnOpenIncidentError):
        await service.start(incident.id, by_user_id=uuid4())

    incident.status = "resolved"
    incident.resolved_at = datetime.now(UTC)
    first = await service.start(incident.id, by_user_id=uuid4())
    second = await service.start(incident.id, by_user_id=uuid4())

    assert first.id == second.id
    assert repo.incidents[incident.id].post_mortem_id == first.id


class EmptyAssembler:
    async def assemble(self, **kwargs: object) -> tuple[list[object], TimelineSourceCoverage]:
        del kwargs
        return [], TimelineSourceCoverage()
