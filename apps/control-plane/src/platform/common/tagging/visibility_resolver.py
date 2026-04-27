from __future__ import annotations

from collections.abc import Awaitable, Callable
from platform.common.exceptions import ValidationError
from platform.common.tagging.constants import ENTITY_TYPES
from platform.common.tagging.exceptions import EntityTypeNotRegisteredError
from typing import Any
from uuid import UUID

VisibleIdProvider = Callable[[Any], Awaitable[set[UUID]]]


class VisibilityResolver:
    def __init__(
        self,
        providers: dict[str, VisibleIdProvider] | None = None,
        *,
        max_visible_ids: int = 10_000,
    ) -> None:
        self.providers = providers or {}
        self.max_visible_ids = max_visible_ids

    async def resolve_visible_entity_ids(
        self,
        requester: Any,
        entity_types: list[str] | None = None,
    ) -> dict[str, set[UUID]]:
        requested = list(entity_types or ENTITY_TYPES)
        visible: dict[str, set[UUID]] = {}
        total = 0
        for entity_type in requested:
            if entity_type not in ENTITY_TYPES:
                raise EntityTypeNotRegisteredError(entity_type)
            provider = self.providers.get(entity_type)
            ids = set(await provider(requester)) if provider is not None else set()
            total += len(ids)
            if total > self.max_visible_ids:
                raise ValidationError(
                    "TAGGING_VISIBLE_ID_LIMIT_EXCEEDED",
                    "Too many visible entities for tag search; narrow your search.",
                    {"limit": self.max_visible_ids},
                )
            visible[entity_type] = ids
        return visible


async def resolve_visible_entity_ids(
    requester: Any,
    entity_types: list[str] | None = None,
) -> dict[str, set[UUID]]:
    return await VisibilityResolver().resolve_visible_entity_ids(requester, entity_types)

