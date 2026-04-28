from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from platform.mcp.dependencies import get_mcp_service
from platform.mcp.models import MCPServerStatus
from platform.mcp.schemas import (
    MCPExposedToolUpsertRequest,
    MCPServerPatch,
    MCPServerRegisterRequest,
)
from platform.mcp.service import MCPService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


def _require_operator(
    principal: dict[str, Any],
    request: Request | None = None,
) -> tuple[UUID, UUID]:
    roles = principal.get("roles")
    if not isinstance(roles, list):
        raise AuthorizationError("UNAUTHORIZED", "Operator role required")
    allowed = {
        "owner",
        "admin",
        "platform_admin",
        "platform_operator",
        "operator",
        "workspace_admin",
    }
    if not any(isinstance(role, dict) and role.get("role") in allowed for role in roles):
        raise AuthorizationError("UNAUTHORIZED", "Operator role required")
    workspace_id = principal.get("workspace_id")
    if workspace_id is None and request is not None:
        workspace_id = request.headers.get("X-Workspace-ID")
    subject = principal.get("sub")
    if not isinstance(workspace_id, str) or not isinstance(subject, str):
        raise AuthorizationError("UNAUTHORIZED", "Workspace context required")
    return UUID(workspace_id), UUID(subject)


@router.post("/servers", status_code=status.HTTP_201_CREATED)
async def register_server(
    payload: MCPServerRegisterRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> Any:
    workspace_id, subject = _require_operator(principal, request)
    return await mcp_service.register_server(workspace_id, payload, subject)


@router.get("/servers")
async def list_servers(
    request: Request,
    status: MCPServerStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: dict[str, Any] = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> Any:
    workspace_id, _subject = _require_operator(principal, request)
    return await mcp_service.list_servers(
        workspace_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/servers/{server_id}")
async def get_server(
    server_id: UUID,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> Any:
    workspace_id, _subject = _require_operator(principal, request)
    return await mcp_service.get_server(workspace_id, server_id)


@router.patch("/servers/{server_id}")
async def patch_server(
    server_id: UUID,
    payload: MCPServerPatch,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> Any:
    workspace_id, _subject = _require_operator(principal, request)
    return await mcp_service.update_server(workspace_id, server_id, payload)


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: UUID,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> Any:
    workspace_id, _subject = _require_operator(principal, request)
    return await mcp_service.deregister_server(workspace_id, server_id)


@router.get("/servers/{server_id}/catalog")
async def get_catalog(
    server_id: UUID,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> Any:
    workspace_id, _subject = _require_operator(principal, request)
    return await mcp_service.get_catalog(workspace_id, server_id)


@router.post("/servers/{server_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_server_catalog(
    server_id: UUID,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> Any:
    workspace_id, _subject = _require_operator(principal, request)
    return await mcp_service.force_refresh(workspace_id, server_id)


@router.get("/exposed-tools")
async def list_exposed_tools(
    request: Request,
    is_exposed: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: dict[str, Any] = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> Any:
    workspace_id, _subject = _require_operator(principal, request)
    return await mcp_service.list_exposed_tools(
        workspace_id,
        is_exposed=is_exposed,
        page=page,
        page_size=page_size,
    )


@router.put("/exposed-tools/{tool_fqn:path}")
async def upsert_exposed_tool(
    tool_fqn: str,
    payload: MCPExposedToolUpsertRequest,
    request: Request,
    principal: dict[str, Any] = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> Any:
    workspace_id, subject = _require_operator(principal, request)
    return await mcp_service.toggle_exposure(workspace_id, tool_fqn, payload, subject)
