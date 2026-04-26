from __future__ import annotations

from platform.common.tagging.constants import (
    LABEL_KEY_PATTERN,
    MAX_LABEL_VALUE_LEN,
    RESERVED_LABEL_PREFIXES,
)
from platform.common.tagging.exceptions import (
    InvalidLabelKeyError,
    LabelValueTooLongError,
    ReservedLabelNamespaceError,
)
from platform.common.tagging.repository import TaggingRepository
from platform.common.tagging.schemas import LabelResponse
from typing import Any
from uuid import UUID


class LabelService:
    def __init__(self, repository: TaggingRepository) -> None:
        self.repository = repository

    async def attach(
        self,
        *,
        entity_type: str,
        entity_id: UUID,
        key: str,
        value: str,
        requester: Any,
        allow_reserved: bool = False,
    ) -> LabelResponse:
        self.validate_reserved_namespace(key, requester, allow_reserved=allow_reserved)
        if LABEL_KEY_PATTERN.fullmatch(key) is None:
            raise InvalidLabelKeyError(key)
        if len(value) > MAX_LABEL_VALUE_LEN:
            raise LabelValueTooLongError(MAX_LABEL_VALUE_LEN)
        row, _old_value = await self.repository.upsert_label(
            entity_type,
            entity_id,
            key,
            value,
            self._requester_id(requester),
        )
        return self._label_response(row)

    async def detach(self, *, entity_type: str, entity_id: UUID, key: str) -> None:
        await self.repository.delete_label(entity_type, entity_id, key)

    async def list_for_entity(self, entity_type: str, entity_id: UUID) -> list[LabelResponse]:
        rows = await self.repository.list_labels_for_entity(entity_type, entity_id)
        return [self._label_response(row) for row in rows]

    async def filter_query(
        self,
        entity_type: str,
        label_filters: dict[str, str],
        visible_entity_ids: set[UUID],
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[UUID]:
        return await self.repository.filter_entities_by_labels(
            entity_type,
            label_filters,
            visible_entity_ids,
            cursor=cursor,
            limit=limit,
        )

    async def cascade_on_entity_deletion(self, entity_type: str, entity_id: UUID) -> None:
        await self.repository.cascade_on_entity_deletion(entity_type, entity_id)

    def validate_reserved_namespace(
        self,
        key: str,
        requester: Any,
        *,
        allow_reserved: bool = False,
    ) -> None:
        if not key.startswith(RESERVED_LABEL_PREFIXES):
            return
        if allow_reserved or self._is_superadmin_or_service_account(requester):
            return
        raise ReservedLabelNamespaceError(key)

    @staticmethod
    def _is_superadmin_or_service_account(requester: Any) -> bool:
        if not isinstance(requester, dict):
            return False
        if requester.get("service_account") is True:
            return True
        roles = requester.get("roles", [])
        return isinstance(roles, list) and any(
            role == "superadmin" or (isinstance(role, dict) and role.get("role") == "superadmin")
            for role in roles
        )

    @staticmethod
    def _requester_id(requester: Any) -> UUID | None:
        if isinstance(requester, dict):
            raw = requester.get("sub") or requester.get("user_id")
            return UUID(str(raw)) if raw is not None else None
        raw_id = getattr(requester, "id", None)
        return UUID(str(raw_id)) if raw_id is not None else None

    @staticmethod
    def _label_response(row: Any) -> LabelResponse:
        return LabelResponse(
            key=row.label_key,
            value=row.label_value,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
            is_reserved=row.label_key.startswith(RESERVED_LABEL_PREFIXES),
        )

