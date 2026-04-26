from __future__ import annotations

from platform.incident_response.schemas import PostMortemResponse
from platform.incident_response.services.incident_service import IncidentService
from platform.incident_response.services.integration_service import IntegrationService
from platform.incident_response.services.post_mortem_service import PostMortemService
from platform.incident_response.services.runbook_service import RunbookService
from platform.incident_response.services.timeline_assembler import TimelineAssembler
from uuid import UUID


class IncidentResponseService:
    def __init__(
        self,
        *,
        incident_service: IncidentService,
        integration_service: IntegrationService,
        runbook_service: RunbookService,
        post_mortem_service: PostMortemService,
        timeline_assembler: TimelineAssembler,
    ) -> None:
        self.incident_service = incident_service
        self.integration_service = integration_service
        self.runbook_service = runbook_service
        self.post_mortem_service = post_mortem_service
        self.timeline_assembler = timeline_assembler

    async def handle_workspace_archived(self, workspace_id: UUID) -> None:
        # Incident-response records are intentionally durable across archival.
        del workspace_id

    async def find_post_mortems_for_execution(
        self,
        execution_id: UUID,
    ) -> list[PostMortemResponse]:
        return await self.post_mortem_service.find_for_execution(execution_id)

    async def find_post_mortems_for_certification(
        self,
        certification_id: UUID,
    ) -> list[PostMortemResponse]:
        return await self.post_mortem_service.find_for_certification(certification_id)
