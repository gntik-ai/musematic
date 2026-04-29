from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AdminListResponse(BaseModel):
    resource: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    tenant_id: UUID | None = None
    total: int = 0


class AdminDetailResponse(BaseModel):
    resource: str
    id: str
    data: dict[str, Any] = Field(default_factory=dict)


class AdminActionResponse(BaseModel):
    action: str
    resource: str
    accepted: bool = True
    preview: bool = False
    affected_count: int = 0
    message: str | None = None
    bulk_action_id: UUID | None = None
    change_preview: dict[str, Any] | None = None


def tenant_id_from_user(current_user: dict[str, Any]) -> UUID | None:
    raw_tenant_id = current_user.get("tenant_id")
    if raw_tenant_id is None:
        return None
    try:
        return UUID(str(raw_tenant_id))
    except ValueError:
        return None


def empty_list(resource: str, current_user: dict[str, Any]) -> AdminListResponse:
    return AdminListResponse(resource=resource, tenant_id=tenant_id_from_user(current_user))


def empty_detail(resource: str, resource_id: str) -> AdminDetailResponse:
    return AdminDetailResponse(resource=resource, id=resource_id)


def accepted(
    action: str,
    resource: str,
    *,
    preview: bool = False,
    affected_count: int = 0,
    message: str | None = None,
    bulk_action_id: UUID | None = None,
    change_preview: dict[str, Any] | None = None,
) -> AdminActionResponse:
    return AdminActionResponse(
        action=action,
        resource=resource,
        preview=preview,
        affected_count=affected_count,
        message=message,
        bulk_action_id=bulk_action_id,
        change_preview=change_preview,
    )
