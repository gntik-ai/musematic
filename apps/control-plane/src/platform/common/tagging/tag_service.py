from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from platform.audit.service import AuditChainService
from platform.common.tagging.constants import ENTITY_TYPES, MAX_TAGS_PER_ENTITY, TAG_PATTERN
from platform.common.tagging.events import (
    AUDIT_EVENT_SOURCE,
    TAG_ATTACHED_EVENT,
    TAG_DETACHED_EVENT,
)
from platform.common.tagging.exceptions import (
    EntityNotFoundForTagError,
    EntityTypeNotRegisteredError,
    InvalidTagError,
    TagAttachLimitExceededError,
)
from platform.common.tagging.repository import TaggingRepository
from platform.common.tagging.schemas import CrossEntityTagSearchResponse, TagResponse
from platform.common.tagging.visibility_resolver import VisibilityResolver
from typing import Any
from uuid import UUID, uuid4

EntityAccessCheck = Callable[[str, UUID, Any, str], Awaitable[bool]]


class TagService:
    def __init__(
        self,
        repository: TaggingRepository,
        *,
        audit_chain: AuditChainService | None = None,
        visibility_resolver: VisibilityResolver | None = None,
        entity_access_check: EntityAccessCheck | None = None,
        max_tags_per_entity: int = MAX_TAGS_PER_ENTITY,
    ) -> None:
        self.repository = repository
        self.audit_chain = audit_chain
        self.visibility_resolver = visibility_resolver or VisibilityResolver()
        self.entity_access_check = entity_access_check
        self.max_tags_per_entity = max_tags_per_entity

    async def attach(
        self,
        *,
        entity_type: str,
        entity_id: UUID,
        tag: str,
        requester: Any,
    ) -> TagResponse:
        normalized = self._validate_tag(entity_type, tag)
        await self._ensure_entity_access(entity_type, entity_id, requester, "mutate")
        existing = await self.repository.get_tag(entity_type, entity_id, normalized)
        if existing is not None:
            return self._tag_response(existing)
        count = await self.repository.count_tags_for_entity(entity_type, entity_id)
        if count >= self.max_tags_per_entity:
            raise TagAttachLimitExceededError(self.max_tags_per_entity)
        row = await self.repository.insert_tag(
            entity_type,
            entity_id,
            normalized,
            self._requester_id(requester),
        )
        await self._audit(
            TAG_ATTACHED_EVENT,
            entity_type=entity_type,
            entity_id=entity_id,
            tag=normalized,
            actor_id=self._requester_id(requester),
        )
        return self._tag_response(row)

    async def detach(
        self,
        *,
        entity_type: str,
        entity_id: UUID,
        tag: str,
        requester: Any,
    ) -> None:
        normalized = self._validate_tag(entity_type, tag)
        await self._ensure_entity_access(entity_type, entity_id, requester, "mutate")
        await self.repository.delete_tag(entity_type, entity_id, normalized)
        await self._audit(
            TAG_DETACHED_EVENT,
            entity_type=entity_type,
            entity_id=entity_id,
            tag=normalized,
            actor_id=self._requester_id(requester),
        )

    async def list_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        requester: Any,
    ) -> list[TagResponse]:
        self._validate_entity_type(entity_type)
        await self._ensure_entity_access(entity_type, entity_id, requester, "view")
        rows = await self.repository.list_tags_for_entity(entity_type, entity_id)
        return [self._tag_response(row) for row in rows]

    async def cross_entity_search(
        self,
        *,
        tag: str,
        requester: Any,
        entity_types: list[str] | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> CrossEntityTagSearchResponse:
        normalized = self._validate_tag("workspace", tag, validate_entity=False)
        visible = await self.visibility_resolver.resolve_visible_entity_ids(requester, entity_types)
        rows = await self.repository.list_entities_by_tag(
            normalized,
            visible,
            cursor=cursor,
            limit=limit + 1,
        )
        page = rows[:limit]
        grouped: dict[str, list[UUID]] = {entity_type: [] for entity_type in visible}
        for entity_type, entity_id in page:
            grouped.setdefault(entity_type, []).append(entity_id)
        next_cursor = None
        if len(rows) > limit:
            next_cursor = str(int(cursor or 0) + limit)
        return CrossEntityTagSearchResponse(
            tag=normalized,
            entities={key: value for key, value in grouped.items() if value},
            next_cursor=next_cursor,
        )

    async def filter_query(
        self,
        entity_type: str,
        tags: list[str],
        visible_entity_ids: set[UUID],
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[UUID]:
        self._validate_entity_type(entity_type)
        normalized = [
            self._validate_tag(entity_type, tag, validate_entity=False) for tag in tags
        ]
        return await self.repository.filter_entities_by_tags(
            entity_type,
            normalized,
            visible_entity_ids,
            cursor=cursor,
            limit=limit,
        )

    async def cascade_on_entity_deletion(self, entity_type: str, entity_id: UUID) -> None:
        self._validate_entity_type(entity_type)
        await self.repository.cascade_on_entity_deletion(entity_type, entity_id)

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

    def _validate_tag(
        self,
        entity_type: str,
        tag: str,
        *,
        validate_entity: bool = True,
    ) -> str:
        if validate_entity:
            self._validate_entity_type(entity_type)
        normalized = tag.strip()
        if (
            not normalized
            or len(normalized) > 128
            or TAG_PATTERN.fullmatch(normalized) is None
        ):
            raise InvalidTagError(tag)
        return normalized

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
    def _tag_response(row: Any) -> TagResponse:
        return TagResponse(tag=row.tag, created_by=row.created_by, created_at=row.created_at)
