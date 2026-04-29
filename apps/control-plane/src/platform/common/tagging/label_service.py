from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from platform.audit.service import AuditChainService
from platform.common.tagging.constants import (
    ENTITY_TYPES,
    LABEL_KEY_PATTERN,
    MAX_LABEL_VALUE_LEN,
    MAX_LABELS_PER_ENTITY,
    RESERVED_LABEL_PREFIXES,
)
from platform.common.tagging.events import (
    AUDIT_EVENT_SOURCE,
    LABEL_DETACHED_EVENT,
    LABEL_UPSERTED_EVENT,
)
from platform.common.tagging.exceptions import (
    EntityNotFoundForTagError,
    EntityTypeNotRegisteredError,
    InvalidLabelKeyError,
    LabelAttachLimitExceededError,
    LabelValueTooLongError,
    ReservedLabelNamespaceError,
)
from platform.common.tagging.repository import TaggingRepository
from platform.common.tagging.schemas import LabelResponse
from typing import Any
from uuid import UUID, uuid4

EntityAccessCheck = Callable[[str, UUID, Any, str], Awaitable[bool]]


class LabelService:
    def __init__(
        self,
        repository: TaggingRepository,
        *,
        audit_chain: AuditChainService | None = None,
        entity_access_check: EntityAccessCheck | None = None,
        max_labels_per_entity: int = MAX_LABELS_PER_ENTITY,
    ) -> None:
        self.repository = repository
        self.audit_chain = audit_chain
        self.entity_access_check = entity_access_check
        self.max_labels_per_entity = max_labels_per_entity

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
        self._validate_entity_type(entity_type)
        normalized_key = self._validate_key(key)
        normalized_value = self._validate_value(value)
        await self._ensure_entity_access(entity_type, entity_id, requester, "mutate")
        self.validate_reserved_namespace(normalized_key, requester, allow_reserved=allow_reserved)
        existing = await self.repository.get_label(entity_type, entity_id, normalized_key)
        if existing is None:
            count = await self.repository.count_labels_for_entity(entity_type, entity_id)
            if count >= self.max_labels_per_entity:
                raise LabelAttachLimitExceededError(self.max_labels_per_entity)
        row, _old_value = await self.repository.upsert_label(
            entity_type,
            entity_id,
            normalized_key,
            normalized_value,
            self._requester_id(requester),
        )
        await self._audit(
            LABEL_UPSERTED_EVENT,
            entity_type=entity_type,
            entity_id=entity_id,
            key=normalized_key,
            old_value=_old_value,
            new_value=normalized_value,
            actor_id=self._requester_id(requester),
        )
        return self._label_response(row)

    async def detach(
        self,
        *,
        entity_type: str,
        entity_id: UUID,
        key: str,
        requester: Any,
    ) -> None:
        self._validate_entity_type(entity_type)
        normalized_key = self._validate_key(key)
        await self._ensure_entity_access(entity_type, entity_id, requester, "mutate")
        await self.repository.delete_label(entity_type, entity_id, normalized_key)
        await self._audit(
            LABEL_DETACHED_EVENT,
            entity_type=entity_type,
            entity_id=entity_id,
            key=normalized_key,
            actor_id=self._requester_id(requester),
        )

    async def list_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        requester: Any,
    ) -> list[LabelResponse]:
        self._validate_entity_type(entity_type)
        await self._ensure_entity_access(entity_type, entity_id, requester, "view")
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
        self._validate_entity_type(entity_type)
        for key in label_filters:
            self._validate_key(key)
        return await self.repository.filter_entities_by_labels(
            entity_type,
            label_filters,
            visible_entity_ids,
            cursor=cursor,
            limit=limit,
        )

    async def list_keys(self, *, prefix: str = "", limit: int = 50) -> list[str]:
        normalized = prefix.strip()
        if normalized and not LABEL_KEY_PATTERN.match(normalized):
            raise InvalidLabelKeyError(prefix)
        return await self.repository.list_label_keys(prefix=normalized, limit=limit)

    async def list_values(self, *, key: str, prefix: str = "", limit: int = 50) -> list[str]:
        normalized_key = self._validate_key(key)
        return await self.repository.list_label_values(
            key=normalized_key,
            prefix=prefix.strip(),
            limit=limit,
        )

    async def cascade_on_entity_deletion(self, entity_type: str, entity_id: UUID) -> None:
        self._validate_entity_type(entity_type)
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

    async def _ensure_entity_access(
        self,
        entity_type: str,
        entity_id: UUID,
        requester: Any,
        action: str,
    ) -> None:
        if self.entity_access_check is None:
            return
        allowed = await self.entity_access_check(entity_type, entity_id, requester, action)
        if not allowed:
            raise EntityNotFoundForTagError(entity_type, entity_id)

    @staticmethod
    def _validate_entity_type(entity_type: str) -> None:
        if entity_type not in ENTITY_TYPES:
            raise EntityTypeNotRegisteredError(entity_type)

    @staticmethod
    def _validate_key(key: str) -> str:
        normalized = key.strip()
        if LABEL_KEY_PATTERN.fullmatch(normalized) is None:
            raise InvalidLabelKeyError(key)
        return normalized

    @staticmethod
    def _validate_value(value: str) -> str:
        normalized = value.strip()
        if len(normalized) > MAX_LABEL_VALUE_LEN:
            raise LabelValueTooLongError(MAX_LABEL_VALUE_LEN)
        return normalized

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

    async def _audit(self, action: str, **payload: Any) -> None:
        if self.audit_chain is None:
            return
        canonical = {"action": action, **payload}
        encoded = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        await self.audit_chain.append(uuid4(), AUDIT_EVENT_SOURCE, encoded)

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
