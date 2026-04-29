from __future__ import annotations

from datetime import timedelta
from platform.common.config import PlatformSettings
from platform.incident_response.schemas import TimelineSourceCoverage
from platform.incident_response.services.post_mortem_service import PostMortemService
from uuid import uuid4

import pytest

from tests.integration.incident_response.support import MemoryIncidentRepository
from tests.unit.incident_response.support import make_incident


@pytest.mark.asyncio
async def test_post_mortem_bidirectional_execution_and_certification_links() -> None:
    ex1 = uuid4()
    ex2 = uuid4()
    cert1 = uuid4()
    incident = make_incident(status="resolved", related_executions=[ex1, ex2])
    incident.resolved_at = incident.triggered_at + timedelta(minutes=5)
    repo = MemoryIncidentRepository()
    repo.incidents[incident.id] = incident
    service = PostMortemService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        timeline_assembler=EmptyAssembler(),  # type: ignore[arg-type]
    )

    post_mortem = await service.start(incident.id, by_user_id=uuid4())
    linked = await service.link_certification(post_mortem.id, cert1)

    assert (await service.find_for_execution(ex1))[0].id == post_mortem.id
    assert (await service.find_for_certification(cert1))[0].id == post_mortem.id
    detail = await service.get(post_mortem.id)
    assert set(repo.incidents[incident.id].related_executions) == {ex1, ex2}
    assert linked.linked_certification_ids == [cert1]
    assert detail.linked_certification_ids == [cert1]


class EmptyAssembler:
    async def assemble(self, **kwargs: object) -> tuple[list[object], TimelineSourceCoverage]:
        del kwargs
        return [], TimelineSourceCoverage()
