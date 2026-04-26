from __future__ import annotations

from platform.common.tagging.constants import ENTITY_TYPES
from platform.common.tagging.exceptions import EntityTypeNotRegisteredError, SavedViewNotFoundError
from platform.common.tagging.repository import TaggingRepository
from platform.common.tagging.schemas import SavedViewResponse
from typing import Any
from uuid import UUID


class SavedViewService:
    def __init__(self, repository: TaggingRepository) -> None:
        self.repository = repository

    async def create(
        self,
        *,
        requester: Any,
        workspace_id: UUID | None,
        name: str,
        entity_type: str,
        filters: dict[str, Any],
        shared: bool,
    ) -> SavedViewResponse:
        self._validate_entity_type(entity_type)
        owner_id = self._requester_id(requester)
        if owner_id is None:
            raise SavedViewNotFoundError()
        row = await self.repository.insert_saved_view(
            owner_id=owner_id,
            workspace_id=workspace_id,
            name=name,
            entity_type=entity_type,
            filters=filters,
            shared=shared,
        )
        return self._response(row, requester)

    async def get(self, view_id: UUID, requester: Any) -> SavedViewResponse:
        row = await self.repository.get_saved_view(view_id)
        if row is None:
            raise SavedViewNotFoundError(view_id)
        return self._response(row, requester)

    async def list_for_user(
        self,
        requester: Any,
        entity_type: str,
        workspace_id: UUID | None,
    ) -> list[SavedViewResponse]:
        self._validate_entity_type(entity_type)
        owner_id = self._requester_id(requester)
        if owner_id is None:
            return []
        personal = await self.repository.list_personal_views(owner_id, entity_type, workspace_id)
        shared = (
            await self.repository.list_shared_views(workspace_id, entity_type)
            if workspace_id is not None
            else []
        )
        by_id = {view.id: view for view in [*personal, *shared]}
        return [self._response(view, requester) for view in by_id.values()]

    async def update(
        self,
        view_id: UUID,
        expected_version: int,
        requester: Any,
        **fields: Any,
    ) -> SavedViewResponse:
        row = await self.repository.update_saved_view(view_id, expected_version, **fields)
        if row is None:
            raise SavedViewNotFoundError(view_id)
        return self._response(row, requester)

    async def share(self, view_id: UUID, requester: Any) -> SavedViewResponse:
        view = await self.get(view_id, requester)
        return await self.update(view_id, view.version, requester, shared=True)

    async def unshare(self, view_id: UUID, requester: Any) -> SavedViewResponse:
        view = await self.get(view_id, requester)
        return await self.update(view_id, view.version, requester, shared=False)

    async def delete(self, view_id: UUID, requester: Any) -> None:
        del requester
        deleted = await self.repository.delete_saved_view(view_id)
        if not deleted:
            raise SavedViewNotFoundError(view_id)

    async def resolve_orphan_owner(self, workspace_id: UUID) -> None:
        del workspace_id

    @staticmethod
    def _validate_entity_type(entity_type: str) -> None:
        if entity_type not in ENTITY_TYPES:
            raise EntityTypeNotRegisteredError(entity_type)

    @staticmethod
    def _requester_id(requester: Any) -> UUID | None:
        if isinstance(requester, dict):
            raw = requester.get("sub") or requester.get("user_id")
            return UUID(str(raw)) if raw is not None else None
        raw_id = getattr(requester, "id", None)
        return UUID(str(raw_id)) if raw_id is not None else None

    def _response(self, row: Any, requester: Any) -> SavedViewResponse:
        requester_id = self._requester_id(requester)
        return SavedViewResponse(
            id=row.id,
            owner_id=row.owner_id,
            workspace_id=row.workspace_id,
            name=row.name,
            entity_type=row.entity_type,
            filters=dict(row.filters or {}),
            is_owner=row.owner_id == requester_id,
            is_shared=row.shared,
            is_orphan_transferred=row.is_orphan_transferred,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

