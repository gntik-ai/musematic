from __future__ import annotations

from datetime import datetime
from platform.audit.dependencies import build_audit_chain_service
from platform.common.audit_hook import audit_chain_hook
from platform.common.dependencies import get_current_user, get_db
from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from platform.trust.models import ContentModerationEvent
from platform.trust.repository import TrustRepository
from platform.trust.schemas import ModerationEventResponse
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/moderation/events", tags=["trust-moderation-events"])


@router.get("", response_model=dict[str, Any])
async def list_events(
    request: Request,
    workspace_id: UUID | None = Query(default=None),
    agent_id: UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    action: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    scoped_workspace = _scope_workspace(request, current_user, workspace_id)
    items, total = await TrustRepository(session).list_moderation_events(
        {
            "workspace_id": scoped_workspace,
            "agent_id": agent_id,
            "action": action,
            "since": since,
            "until": until,
            "limit": limit,
        }
    )
    if category is not None:
        items = [item for item in items if category in (item.triggered_categories or [])]
        total = len(items)
    return {
        "items": [ModerationEventResponse.model_validate(item) for item in items],
        "total": total,
    }


@router.get("/aggregate", response_model=list[dict[str, Any]])
async def aggregate_events(
    request: Request,
    workspace_id: UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    group_by: str = Query(default="category,action"),
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    scoped_workspace = _scope_workspace(request, current_user, workspace_id)
    dimensions = [part.strip() for part in group_by.split(",") if part.strip()]
    invalid = set(dimensions) - {"category", "agent", "action", "day"}
    if invalid:
        raise ValidationError("INVALID_GROUP_BY", f"Unsupported dimensions: {sorted(invalid)}")
    return await TrustRepository(session).aggregate_moderation_events(
        {
            "workspace_id": scoped_workspace,
            "action": action,
            "since": since,
            "until": until,
            "limit": 5000,
        },
        dimensions,
    )


@router.get("/{event_id}", response_model=ModerationEventResponse)
async def get_event(
    event_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ModerationEventResponse:
    event = await TrustRepository(session).get_moderation_event(event_id)
    if event is None:
        raise NotFoundError("MODERATION_EVENT_NOT_FOUND", "Moderation event not found")
    _scope_workspace(request, current_user, event.workspace_id)
    await _append_event_access_audit(request, session, event, current_user)
    return ModerationEventResponse.model_validate(event)


def _scope_workspace(
    request: Request,
    current_user: dict[str, Any],
    requested_workspace: UUID | None,
) -> UUID | None:
    roles = _role_names(current_user)
    if roles & {"auditor", "platform_admin", "superadmin"}:
        return requested_workspace
    if "workspace_admin" not in roles:
        raise AuthorizationError("PERMISSION_DENIED", "Moderation events require admin role")
    own_workspace = request.headers.get("X-Workspace-ID") or current_user.get("workspace_id")
    if own_workspace in {None, ""}:
        raise ValidationError("WORKSPACE_REQUIRED", "Workspace context is required")
    own_uuid = UUID(str(own_workspace))
    if requested_workspace is not None and requested_workspace != own_uuid:
        raise AuthorizationError("PERMISSION_DENIED", "Cannot access another workspace")
    return own_uuid


def _role_names(current_user: dict[str, Any]) -> set[str]:
    return {
        str(item.get("role"))
        for item in current_user.get("roles", [])
        if isinstance(item, dict) and item.get("role") is not None
    }


async def _append_event_access_audit(
    request: Request,
    session: AsyncSession,
    event: ContentModerationEvent,
    current_user: dict[str, Any],
) -> None:
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not hasattr(settings, "audit") or not callable(
        getattr(session, "execute", None)
    ):
        return
    clients = getattr(request.app.state, "clients", {})
    audit_chain = build_audit_chain_service(
        session=session,
        settings=settings,
        producer=clients.get("kafka") if hasattr(clients, "get") else None,
    )
    await audit_chain_hook(
        audit_chain,
        None,
        "trust.content_moderation.event_access",
        {
            "event_id": event.id,
            "workspace_id": event.workspace_id,
            "agent_id": event.agent_id,
            "policy_id": event.policy_id,
            "action_taken": event.action_taken,
            "triggered_categories": event.triggered_categories,
            "actor_id": current_user.get("sub"),
            "accessed_at": datetime.now(event.created_at.tzinfo),
        },
    )
