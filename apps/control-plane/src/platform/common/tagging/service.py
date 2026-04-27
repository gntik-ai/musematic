from __future__ import annotations

from platform.common.tagging.label_service import LabelService
from platform.common.tagging.saved_view_service import SavedViewService
from platform.common.tagging.tag_service import TagService
from uuid import UUID


class TaggingService:
    def __init__(
        self,
        tag_service: TagService,
        label_service: LabelService,
        saved_view_service: SavedViewService,
    ) -> None:
        self.tags = tag_service
        self.labels = label_service
        self.saved_views = saved_view_service

    async def cascade_on_entity_deletion(self, entity_type: str, entity_id: UUID) -> None:
        await self.tags.cascade_on_entity_deletion(entity_type, entity_id)

    async def handle_workspace_archived(self, workspace_id: UUID) -> None:
        del workspace_id

