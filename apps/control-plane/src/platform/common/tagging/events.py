from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

TAG_ATTACHED_EVENT = "tagging.tag.attached"
TAG_DETACHED_EVENT = "tagging.tag.detached"
LABEL_UPSERTED_EVENT = "tagging.label.upserted"
LABEL_DETACHED_EVENT = "tagging.label.detached"
SAVED_VIEW_CREATED_EVENT = "tagging.saved_view.created"
SAVED_VIEW_UPDATED_EVENT = "tagging.saved_view.updated"
SAVED_VIEW_SHARED_EVENT = "tagging.saved_view.shared"
SAVED_VIEW_UNSHARED_EVENT = "tagging.saved_view.unshared"
SAVED_VIEW_DELETED_EVENT = "tagging.saved_view.deleted"
SAVED_VIEW_ORPHAN_TRANSFERRED_EVENT = "tagging.saved_view.orphan_transferred"
SAVED_VIEW_ORPHAN_MARKED_EVENT = "tagging.saved_view.orphan_marked"
AUDIT_EVENT_SOURCE = "common_tagging"


@dataclass(frozen=True, slots=True)
class EntityTagAttachedPayload:
    entity_type: str
    entity_id: UUID
    tag: str
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class EntityTagDetachedPayload:
    entity_type: str
    entity_id: UUID
    tag: str
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class EntityLabelUpsertedPayload:
    entity_type: str
    entity_id: UUID
    key: str
    old_value: str | None
    new_value: str
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class EntityLabelDetachedPayload:
    entity_type: str
    entity_id: UUID
    key: str
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class SavedViewCreatedPayload:
    view_id: UUID
    workspace_id: UUID | None
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class SavedViewUpdatedPayload:
    view_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class SavedViewSharedPayload:
    view_id: UUID
    workspace_id: UUID | None
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class SavedViewUnsharedPayload:
    view_id: UUID
    workspace_id: UUID | None
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class SavedViewDeletedPayload:
    view_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class SavedViewOrphanTransferredPayload:
    view_id: UUID
    previous_owner_id: UUID
    new_owner_id: UUID
    workspace_id: UUID


@dataclass(frozen=True, slots=True)
class SavedViewOrphanMarkedPayload:
    view_id: UUID
    previous_owner_id: UUID
    workspace_id: UUID
