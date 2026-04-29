from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.common.tagging.repository import _sorted_uuids
from platform.common.tagging.router import (
    admin_labels_router,
    labels_router,
    saved_views_router,
    tags_router,
)
from platform.common.tagging.schemas import SavedViewResponse
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI

NOW = datetime(2026, 4, 29, tzinfo=UTC)


class RecordingAudit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def append(
        self,
        audit_event_id: UUID | None,
        audit_event_source: str,
        canonical_payload: bytes,
    ) -> None:
        self.entries.append(
            {
                "audit_event_id": str(audit_event_id),
                "audit_event_source": audit_event_source,
                "payload": json.loads(canonical_payload.decode("utf-8")),
            }
        )


class InMemoryTaggingRepository:
    def __init__(self) -> None:
        self.tags: dict[tuple[str, UUID, str], SimpleNamespace] = {}
        self.labels: dict[tuple[str, UUID, str], SimpleNamespace] = {}
        self.saved_views: dict[UUID, SimpleNamespace] = {}
        self.cascades: list[tuple[str, UUID]] = []

    async def get_tag(
        self,
        entity_type: str,
        entity_id: UUID,
        tag: str,
    ) -> SimpleNamespace | None:
        return self.tags.get((entity_type, entity_id, tag))

    async def insert_tag(
        self,
        entity_type: str,
        entity_id: UUID,
        tag: str,
        created_by: UUID | None,
    ) -> SimpleNamespace:
        row = SimpleNamespace(
            id=uuid4(),
            entity_type=entity_type,
            entity_id=entity_id,
            tag=tag,
            created_by=created_by,
            created_at=NOW,
        )
        self.tags.setdefault((entity_type, entity_id, tag), row)
        return self.tags[(entity_type, entity_id, tag)]

    async def delete_tag(self, entity_type: str, entity_id: UUID, tag: str) -> bool:
        return self.tags.pop((entity_type, entity_id, tag), None) is not None

    async def list_tags_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
    ) -> list[SimpleNamespace]:
        return sorted(
            [
                row
                for (row_type, row_id, _tag), row in self.tags.items()
                if row_type == entity_type and row_id == entity_id
            ],
            key=lambda row: row.tag,
        )

    async def list_entities_by_tag(
        self,
        tag: str,
        visible_entity_ids_by_type: dict[str, set[UUID]],
        *,
        cursor: str | None,
        limit: int,
    ) -> list[tuple[str, UUID]]:
        offset = int(cursor or 0)
        matches = sorted(
            [
                (entity_type, entity_id)
                for (entity_type, entity_id, row_tag) in self.tags
                if row_tag == tag
                and entity_id in visible_entity_ids_by_type.get(entity_type, set())
            ],
            key=lambda item: (item[0], str(item[1])),
        )
        return matches[offset : offset + limit]

    async def filter_entities_by_tags(
        self,
        entity_type: str,
        tags: list[str],
        visible_entity_ids: set[UUID],
        *,
        cursor: str | None,
        limit: int,
    ) -> list[UUID]:
        offset = int(cursor or 0)
        wanted = set(tags)
        matches = [
            entity_id
            for entity_id in _sorted_uuids(visible_entity_ids)
            if wanted.issubset(
                {
                    tag
                    for (row_type, row_id, tag) in self.tags
                    if row_type == entity_type and row_id == entity_id
                }
            )
        ]
        return matches[offset : offset + limit]

    async def count_tags_for_entity(self, entity_type: str, entity_id: UUID) -> int:
        return len(
            [
                tag
                for row_type, row_id, tag in self.tags
                if row_type == entity_type and row_id == entity_id
            ]
        )

    async def get_label(
        self,
        entity_type: str,
        entity_id: UUID,
        key: str,
    ) -> SimpleNamespace | None:
        return self.labels.get((entity_type, entity_id, key))

    async def upsert_label(
        self,
        entity_type: str,
        entity_id: UUID,
        key: str,
        value: str,
        updated_by: UUID | None,
    ) -> tuple[SimpleNamespace, str | None]:
        existing = await self.get_label(entity_type, entity_id, key)
        old_value = existing.label_value if existing is not None else None
        row = existing or SimpleNamespace(
            id=uuid4(),
            entity_type=entity_type,
            entity_id=entity_id,
            label_key=key,
            created_by=updated_by,
            created_at=NOW,
            updated_at=NOW,
        )
        row.label_value = value
        row.updated_at = NOW
        self.labels[(entity_type, entity_id, key)] = row
        return row, old_value

    async def delete_label(self, entity_type: str, entity_id: UUID, key: str) -> bool:
        return self.labels.pop((entity_type, entity_id, key), None) is not None

    async def list_labels_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
    ) -> list[SimpleNamespace]:
        return sorted(
            [
                row
                for (row_type, row_id, _key), row in self.labels.items()
                if row_type == entity_type and row_id == entity_id
            ],
            key=lambda row: row.label_key,
        )

    async def filter_entities_by_labels(
        self,
        entity_type: str,
        label_filters: dict[str, str],
        visible_entity_ids: set[UUID],
        *,
        cursor: str | None,
        limit: int,
    ) -> list[UUID]:
        offset = int(cursor or 0)
        matches = [
            entity_id
            for entity_id in _sorted_uuids(visible_entity_ids)
            if all(
                self.labels.get((entity_type, entity_id, key)) is not None
                and self.labels[(entity_type, entity_id, key)].label_value == value
                for key, value in label_filters.items()
            )
        ]
        return matches[offset : offset + limit]

    async def list_label_keys(self, *, prefix: str = "", limit: int = 50) -> list[str]:
        keys = sorted(
            {key for _entity_type, _entity_id, key in self.labels if key.startswith(prefix)}
        )
        return keys[:limit]

    async def list_label_values(
        self,
        *,
        key: str,
        prefix: str = "",
        limit: int = 50,
    ) -> list[str]:
        values = sorted(
            {
                row.label_value
                for (_entity_type, _entity_id, label_key), row in self.labels.items()
                if label_key == key and row.label_value.startswith(prefix)
            }
        )
        return values[:limit]

    async def count_labels_for_entity(self, entity_type: str, entity_id: UUID) -> int:
        return len(
            [
                key
                for row_type, row_id, key in self.labels
                if row_type == entity_type and row_id == entity_id
            ]
        )

    async def cascade_on_entity_deletion(self, entity_type: str, entity_id: UUID) -> None:
        self.cascades.append((entity_type, entity_id))
        for key in list(self.tags):
            if key[0] == entity_type and key[1] == entity_id:
                self.tags.pop(key)
        for key in list(self.labels):
            if key[0] == entity_type and key[1] == entity_id:
                self.labels.pop(key)

    async def insert_saved_view(
        self,
        *,
        owner_id: UUID,
        workspace_id: UUID | None,
        name: str,
        entity_type: str,
        filters: dict[str, Any],
        shared: bool,
    ) -> SimpleNamespace:
        row = SimpleNamespace(
            id=uuid4(),
            owner_id=owner_id,
            workspace_id=workspace_id,
            name=name,
            entity_type=entity_type,
            filters=dict(filters),
            shared=shared,
            version=1,
            is_orphan_transferred=False,
            is_orphan=False,
            created_at=NOW,
            updated_at=NOW,
        )
        self.saved_views[row.id] = row
        return row

    async def get_saved_view(self, view_id: UUID) -> SimpleNamespace | None:
        return self.saved_views.get(view_id)

    async def list_personal_views(
        self,
        owner_id: UUID,
        entity_type: str,
        workspace_id: UUID | None = None,
    ) -> list[SimpleNamespace]:
        return [
            view
            for view in self.saved_views.values()
            if view.owner_id == owner_id
            and view.entity_type == entity_type
            and (workspace_id is None or view.workspace_id == workspace_id)
        ]

    async def list_shared_views(
        self,
        workspace_id: UUID,
        entity_type: str,
    ) -> list[SimpleNamespace]:
        return [
            view
            for view in self.saved_views.values()
            if view.workspace_id == workspace_id and view.entity_type == entity_type and view.shared
        ]

    async def update_saved_view(
        self,
        view_id: UUID,
        expected_version: int,
        **fields: Any,
    ) -> SimpleNamespace | None:
        view = self.saved_views.get(view_id)
        if view is None or view.version != expected_version:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(view, key, value)
        view.version += 1
        view.updated_at = NOW
        return view

    async def delete_saved_view(self, view_id: UUID) -> bool:
        return self.saved_views.pop(view_id, None) is not None

    async def transfer_saved_view_ownership(self, view_id: UUID, new_owner_id: UUID) -> None:
        view = self.saved_views[view_id]
        view.owner_id = new_owner_id
        view.is_orphan_transferred = True
        view.is_orphan = False
        view.updated_at = NOW

    async def mark_saved_view_orphan(self, view_id: UUID) -> None:
        view = self.saved_views[view_id]
        view.is_orphan = True
        view.updated_at = NOW

    async def list_views_owned_by_user_in_workspace(
        self,
        owner_id: UUID,
        workspace_id: UUID,
    ) -> list[SimpleNamespace]:
        return [
            view
            for view in self.saved_views.values()
            if view.owner_id == owner_id and view.workspace_id == workspace_id
        ]


class ResolverStub:
    def __init__(self, visible: dict[str, set[UUID]]) -> None:
        self.visible = visible

    async def resolve_visible_entity_ids(
        self,
        requester: object,
        entity_types: list[str] | None = None,
    ) -> dict[str, set[UUID]]:
        del requester
        if entity_types is None:
            return self.visible
        return {entity_type: self.visible.get(entity_type, set()) for entity_type in entity_types}


def requester(user_id: UUID, roles: list[str] | None = None) -> dict[str, Any]:
    return {"sub": str(user_id), "roles": roles or []}


def saved_view_ids(responses: list[SavedViewResponse]) -> set[UUID]:
    return {item.id for item in responses}


def build_router_app(
    *,
    current_user: dict[str, Any],
    tag_service: Any | None = None,
    label_service: Any | None = None,
    saved_view_service: Any | None = None,
) -> FastAPI:
    from platform.common.tagging.dependencies import (
        get_label_service,
        get_saved_view_service,
        get_tag_service,
    )

    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(tags_router)
    app.include_router(labels_router)
    app.include_router(admin_labels_router)
    app.include_router(saved_views_router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    if tag_service is not None:
        app.dependency_overrides[get_tag_service] = lambda: tag_service
    if label_service is not None:
        app.dependency_overrides[get_label_service] = lambda: label_service
    if saved_view_service is not None:
        app.dependency_overrides[get_saved_view_service] = lambda: saved_view_service
    return app
