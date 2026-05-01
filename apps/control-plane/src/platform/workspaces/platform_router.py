from __future__ import annotations

import json
from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.events.producer import EventProducer
from platform.common.models.workspace import Workspace
from platform.tenants.platform_router import require_platform_staff
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/platform/workspaces", tags=["platform.workspaces"])


class PlatformWorkspaceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    owner_id: UUID


@router.get("/{workspace_id}", response_model=PlatformWorkspaceResponse)
async def get_platform_workspace(
    workspace_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(require_platform_staff),
    session: AsyncSession = Depends(database.get_platform_staff_session),
) -> PlatformWorkspaceResponse:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"})
    await _append_workspace_read_audit(request, session, current_user, workspace)
    await session.commit()
    return PlatformWorkspaceResponse(
        id=workspace.id,
        tenant_id=workspace.tenant_id,
        name=workspace.name,
        owner_id=workspace.owner_id,
    )


async def _append_workspace_read_audit(
    request: Request,
    session: AsyncSession,
    current_user: dict[str, Any],
    workspace: Workspace,
) -> None:
    settings = _settings(request)
    clients = getattr(request.app.state, "clients", {})
    producer = clients.get("kafka") if isinstance(clients, dict) else None
    payload: dict[str, object] = {
        "tenant_id": str(workspace.tenant_id),
        "workspace_id": str(workspace.id),
        "actor_user_id": str(current_user.get("sub") or current_user.get("id") or ""),
    }
    await AuditChainService(
        AuditChainRepository(session),
        settings,
        producer=producer if isinstance(producer, EventProducer) else None,
    ).append(
        uuid4(),
        "platform.tenants",
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        event_type="platform.tenants.workspace_read",
        actor_role="platform_staff",
        canonical_payload_json=payload,
        tenant_id=workspace.tenant_id,
    )


def _settings(request: Request) -> PlatformSettings:
    value = getattr(request.app.state, "settings", None)
    return value if isinstance(value, PlatformSettings) else default_settings
