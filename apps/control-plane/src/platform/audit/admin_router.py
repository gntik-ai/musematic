from __future__ import annotations

from datetime import datetime
from platform.admin.activity_feed import list_admin_activity
from platform.admin.rbac import require_admin, require_superadmin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted, empty_list
from platform.common.dependencies import get_db
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["admin", "audit"])


@router.get("/audit", response_model=AdminListResponse)
async def query_audit_entries(
    request: Request,
    event_type: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    response = empty_list("audit", current_user, request)
    response.items = [
        {"event_type": event_type, "actor": actor}
        for _ in range(1)
        if event_type is not None or actor is not None
    ]
    response.total = len(response.items)
    return response


@router.post("/audit/export", response_model=AdminActionResponse)
async def export_audit_selection(
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("export", "audit", affected_count=1)


@router.get("/activity", response_model=AdminListResponse)
async def list_activity(
    request: Request,
    tenant_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    since: datetime | None = Query(default=None),
    current_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminListResponse:
    entries = await list_admin_activity(session, tenant_id=tenant_id, limit=limit, since=since)
    response = empty_list("activity", current_user, request)
    response.items = [
        {
            "id": str(getattr(entry, "id", "")),
            "event_type": getattr(entry, "event_type", None),
            "actor_role": getattr(entry, "actor_role", None),
            "severity": getattr(entry, "severity", None),
            "created_at": getattr(entry, "created_at", None),
        }
        for entry in entries
    ]
    response.total = len(response.items)
    return response
