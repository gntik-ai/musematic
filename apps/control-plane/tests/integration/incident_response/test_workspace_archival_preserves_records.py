from __future__ import annotations

from datetime import timedelta
from platform.common.config import PlatformSettings
from platform.incident_response.schemas import TimelineSourceCoverage
from platform.incident_response.service import IncidentResponseService
from platform.incident_response.services.post_mortem_service import PostMortemService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.integration.incident_response.support import MemoryIncidentRepository
from tests.unit.incident_response.support import make_incident


@pytest.mark.asyncio
async def test_workspace_archival_preserves_incident_runbook_and_post_mortem_records() -> None:
    incident = make_incident(status="resolved")
    incident.resolved_at = incident.triggered_at + timedelta(minutes=5)
    repo = MemoryIncidentRepository()
    repo.incidents[incident.id] = incident
    post_mortems = PostMortemService(
        repository=repo,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        timeline_assembler=EmptyAssembler(),  # type: ignore[arg-type]
    )
    post_mortem = await post_mortems.start(incident.id, by_user_id=uuid4())
    facade = IncidentResponseService(
        incident_service=SimpleNamespace(
            get=lambda incident_id: _async(repo.incidents[incident_id])
        ),
        integration_service=SimpleNamespace(),
        runbook_service=SimpleNamespace(
            get_by_scenario=lambda scenario: _async({"scenario": scenario})
        ),
        post_mortem_service=post_mortems,
        timeline_assembler=SimpleNamespace(),
    )

    await facade.handle_workspace_archived(uuid4())

    assert repo.incidents[incident.id].id == incident.id
    assert (await post_mortems.get(post_mortem.id)).id == post_mortem.id
    assert (await post_mortems.get_by_incident(incident.id)).id == post_mortem.id


class EmptyAssembler:
    async def assemble(self, **kwargs: object) -> tuple[list[object], TimelineSourceCoverage]:
        del kwargs
        return [], TimelineSourceCoverage()


async def _async(value: object) -> object:
    return value
