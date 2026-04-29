from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from platform.audit.service import AuditChainService
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.common.tagging.constants import ENTITY_TYPES
from platform.common.tagging.events import (
    AUDIT_EVENT_SOURCE,
    SAVED_VIEW_CREATED_EVENT,
    SAVED_VIEW_DELETED_EVENT,
    SAVED_VIEW_ORPHAN_MARKED_EVENT,
    SAVED_VIEW_ORPHAN_TRANSFERRED_EVENT,
    SAVED_VIEW_SHARED_EVENT,
    SAVED_VIEW_UNSHARED_EVENT,
    SAVED_VIEW_UPDATED_EVENT,
)
from platform.common.tagging.exceptions import (
    EntityTypeNotRegisteredError,
    SavedViewNameTakenError,
    SavedViewNotFoundError,
)
from platform.common.tagging.repository import TaggingRepository
from platform.common.tagging.schemas import SavedViewResponse
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy.exc import IntegrityError

WorkspaceMembershipCheck = Callable[[UUID, Any], Awaitable[bool]]
WorkspaceSuperadminProvider = Callable[[UUID], Awaitable[UUID | None]]
FilterValidator = Callable[[str, dict[str, Any]], dict[str, Any]]

_log = structlog.get_logger(__name__)

_COMMON_FILTER_KEYS = {
    "tags",
    "labels",
    "label",
    "sort",
    "page",
    "page_size",
    "limit",
    "offset",
    "columns",
    "display",
}
_ENTITY_FILTER_KEYS: dict[str, set[str]] = {
    "workspace": {"status", "name", "owner_id"},
    "agent": {"keyword", "status", "maturity_min", "fqn_pattern", "namespace"},
    "fleet": {"status", "name", "topology_type"},
    "workflow": {"status", "name"},
    "policy": {"scope_type", "status", "workspace_id"},
    "certification": {"agent_id", "agent_fqn", "status"},
    "evaluation_run": {"eval_set_id", "agent_fqn", "status"},
}


class SavedViewService:
    def __init__(
        self,
        repository: TaggingRepository,
        *,
        audit_chain: AuditChainService | None = None,
        workspace_membership_check: WorkspaceMembershipCheck | None = None,
        workspace_superadmin_provider: WorkspaceSuperadminProvider | None = None,
        filter_validator: FilterValidator | None = None,
    ) -> None:
        self.repository = repository
        self.audit_chain = audit_chain
        self.workspace_membership_check = workspace_membership_check
        self.workspace_superadmin_provider = workspace_superadmin_provider
        self.filter_validator = filter_validator or self._default_filter_validator

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
        if shared and workspace_id is None:
            raise ValidationError(
                "SAVED_VIEW_SHARE_REQUIRES_WORKSPACE",
                "Saved views must be workspace-scoped before they can be shared.",
            )
        if workspace_id is not None:
            await self._ensure_workspace_member(workspace_id, requester)
        normalized_filters = self.filter_validator(entity_type, filters)
        try:
            row = await self.repository.insert_saved_view(
                owner_id=owner_id,
                workspace_id=workspace_id,
                name=name,
                entity_type=entity_type,
                filters=normalized_filters,
                shared=shared,
            )
        except IntegrityError as exc:
            raise SavedViewNameTakenError(name) from exc
        await self._audit(
            SAVED_VIEW_CREATED_EVENT,
            view_id=row.id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            actor_id=owner_id,
        )
        return self._response(row, requester)

    async def get(self, view_id: UUID, requester: Any) -> SavedViewResponse:
        row = await self.repository.get_saved_view(view_id)
        if row is None or not await self._can_view(row, requester):
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
        if workspace_id is not None and not await self._is_workspace_member(
            workspace_id,
            requester,
        ):
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
        audit: bool = True,
        **fields: Any,
    ) -> SavedViewResponse:
        row = await self.repository.get_saved_view(view_id)
        if row is None or not self._is_owner(row, requester):
            raise SavedViewNotFoundError(view_id)
        if fields.get("filters") is not None:
            fields["filters"] = self.filter_validator(row.entity_type, fields["filters"])
        row = await self.repository.update_saved_view(view_id, expected_version, **fields)
        if row is None:
            raise SavedViewNotFoundError(view_id)
        if audit:
            await self._audit(
                SAVED_VIEW_UPDATED_EVENT,
                view_id=row.id,
                workspace_id=row.workspace_id,
                actor_id=self._requester_id(requester),
                fields=sorted(key for key, value in fields.items() if value is not None),
            )
        return self._response(row, requester)

    async def share(self, view_id: UUID, requester: Any) -> SavedViewResponse:
        view = await self.get(view_id, requester)
        if view.workspace_id is None:
            raise ValidationError(
                "SAVED_VIEW_SHARE_REQUIRES_WORKSPACE",
                "Saved views must be workspace-scoped before they can be shared.",
            )
        await self._ensure_workspace_member(view.workspace_id, requester)
        updated = await self.update(view_id, view.version, requester, audit=False, shared=True)
        await self._audit(
            SAVED_VIEW_SHARED_EVENT,
            view_id=updated.id,
            workspace_id=updated.workspace_id,
            actor_id=self._requester_id(requester),
        )
        return updated

    async def unshare(self, view_id: UUID, requester: Any) -> SavedViewResponse:
        view = await self.get(view_id, requester)
        updated = await self.update(view_id, view.version, requester, audit=False, shared=False)
        await self._audit(
            SAVED_VIEW_UNSHARED_EVENT,
            view_id=updated.id,
            workspace_id=updated.workspace_id,
            actor_id=self._requester_id(requester),
        )
        return updated

    async def delete(self, view_id: UUID, requester: Any) -> None:
        row = await self.repository.get_saved_view(view_id)
        if row is None or not await self._can_delete(row, requester):
            raise SavedViewNotFoundError(view_id)
        deleted = await self.repository.delete_saved_view(view_id)
        if not deleted:
            raise SavedViewNotFoundError(view_id)
        await self._audit(
            SAVED_VIEW_DELETED_EVENT,
            view_id=view_id,
            workspace_id=row.workspace_id,
            actor_id=self._requester_id(requester),
        )

    async def resolve_orphan_owner(
        self,
        workspace_id: UUID,
        former_owner_id: UUID | None = None,
    ) -> None:
        if former_owner_id is None:
            candidates = [
                view
                for entity_type in ENTITY_TYPES
                for view in await self.repository.list_shared_views(workspace_id, entity_type)
            ]
        else:
            candidates = await self.repository.list_views_owned_by_user_in_workspace(
                former_owner_id,
                workspace_id,
            )
        new_owner_id = (
            await self.workspace_superadmin_provider(workspace_id)
            if self.workspace_superadmin_provider is not None
            else None
        )
        for view in candidates:
            if not getattr(view, "shared", False):
                continue
            if await self._owner_is_still_member(view.owner_id, workspace_id):
                continue
            if new_owner_id is not None:
                await self.repository.transfer_saved_view_ownership(view.id, new_owner_id)
                await self._audit(
                    SAVED_VIEW_ORPHAN_TRANSFERRED_EVENT,
                    view_id=view.id,
                    workspace_id=workspace_id,
                    previous_owner_id=view.owner_id,
                    new_owner_id=new_owner_id,
                )
                _log.info(
                    "tagging.saved_view.orphan_transferred",
                    view_id=str(view.id),
                    workspace_id=str(workspace_id),
                    previous_owner_id=str(view.owner_id),
                    new_owner_id=str(new_owner_id),
                )
            else:
                marker = getattr(self.repository, "mark_saved_view_orphan", None)
                if callable(marker):
                    await marker(view.id)
                await self._audit(
                    SAVED_VIEW_ORPHAN_MARKED_EVENT,
                    view_id=view.id,
                    workspace_id=workspace_id,
                    previous_owner_id=view.owner_id,
                )
                _log.info(
                    "tagging.saved_view.orphan_marked",
                    view_id=str(view.id),
                    workspace_id=str(workspace_id),
                    previous_owner_id=str(view.owner_id),
                )

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

    async def _can_view(self, row: Any, requester: Any) -> bool:
        if self._is_owner(row, requester):
            return True
        return bool(
            getattr(row, "shared", False)
            and row.workspace_id is not None
            and await self._is_workspace_member(row.workspace_id, requester)
        )

    async def _can_delete(self, row: Any, requester: Any) -> bool:
        if self._is_owner(row, requester):
            return True
        if row.workspace_id is None:
            return False
        if self._is_superadmin(requester):
            return await self._is_workspace_member(row.workspace_id, requester)
        if self.workspace_superadmin_provider is None:
            return False
        requester_id = self._requester_id(requester)
        return (
            requester_id is not None
            and requester_id == await self.workspace_superadmin_provider(row.workspace_id)
        )

    def _is_owner(self, row: Any, requester: Any) -> bool:
        requester_id = self._requester_id(requester)
        return requester_id is not None and row.owner_id == requester_id

    async def _ensure_workspace_member(self, workspace_id: UUID, requester: Any) -> None:
        if not await self._is_workspace_member(workspace_id, requester):
            raise AuthorizationError(
                "SAVED_VIEW_WORKSPACE_MEMBERSHIP_REQUIRED",
                "Saved view operations require workspace membership.",
                {"workspace_id": str(workspace_id)},
            )

    async def _is_workspace_member(self, workspace_id: UUID, requester: Any) -> bool:
        if self.workspace_membership_check is None:
            return True
        return await self.workspace_membership_check(workspace_id, requester)

    async def _owner_is_still_member(self, owner_id: UUID, workspace_id: UUID) -> bool:
        return await self._is_workspace_member(workspace_id, {"sub": str(owner_id)})

    @staticmethod
    def _is_superadmin(requester: Any) -> bool:
        if not isinstance(requester, dict):
            return False
        roles = requester.get("roles", [])
        return isinstance(roles, list) and any(
            role == "superadmin" or (isinstance(role, dict) and role.get("role") == "superadmin")
            for role in roles
        )

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
            is_orphan=getattr(row, "is_orphan", False),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _default_filter_validator(entity_type: str, filters: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(filters, dict):
            raise ValidationError(
                "SAVED_VIEW_FILTERS_INVALID",
                "Saved view filters must be a JSON object.",
            )
        allowed = _COMMON_FILTER_KEYS | _ENTITY_FILTER_KEYS.get(entity_type, set())
        unknown = sorted(
            key for key in filters if key not in allowed and not key.startswith("label.")
        )
        if unknown:
            raise ValidationError(
                "SAVED_VIEW_FILTER_UNKNOWN",
                "Saved view filters contain unsupported parameters.",
                {"entity_type": entity_type, "unknown": unknown},
            )
        labels = filters.get("labels") or filters.get("label")
        if labels is not None and not isinstance(labels, dict):
            raise ValidationError(
                "SAVED_VIEW_FILTER_LABELS_INVALID",
                "Saved view label filters must be a key-value object.",
            )
        tags = filters.get("tags")
        if tags is not None and not (
            isinstance(tags, list) and all(isinstance(item, str) for item in tags)
        ):
            raise ValidationError(
                "SAVED_VIEW_FILTER_TAGS_INVALID",
                "Saved view tag filters must be a list of strings.",
            )
        return dict(filters)

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
