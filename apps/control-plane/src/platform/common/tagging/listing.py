from __future__ import annotations

from platform.common.tagging.filter_extension import TagLabelFilterParams
from typing import Any
from uuid import UUID


async def resolve_filtered_entity_ids(
    *,
    entity_type: str,
    visible_entity_ids: set[UUID],
    filters: TagLabelFilterParams | None,
    tag_service: Any | None,
    label_service: Any | None,
    limit: int = 10_000,
) -> set[UUID] | None:
    if filters is None or (not filters.tags and not filters.labels):
        return None

    filtered = set(visible_entity_ids)
    if filters.tags:
        if tag_service is None:
            return set()
        tagged = await tag_service.filter_query(
            entity_type,
            filters.tags,
            filtered,
            limit=limit,
        )
        filtered &= set(tagged)

    if filters.labels:
        if label_service is None:
            return set()
        labelled = await label_service.filter_query(
            entity_type,
            filters.labels,
            filtered,
            limit=limit,
        )
        filtered &= set(labelled)

    return filtered
