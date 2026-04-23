from __future__ import annotations

from collections.abc import Awaitable, Callable
from platform.a2a_gateway.client_service import A2AGatewayClientService
from platform.a2a_gateway.dependencies import (
    get_a2a_client_service,
    get_a2a_server_service,
    get_a2a_stream,
    get_mcp_server_service,
)
from platform.a2a_gateway.exceptions import (
    A2AAuthenticationError,
    A2AAuthorizationError,
    A2AError,
)
from platform.a2a_gateway.mcp_server import MCPServerService
from platform.a2a_gateway.schemas import (
    A2AExternalEndpointCreate,
    A2AExternalEndpointResponse,
    A2AFollowUpRequest,
    A2ATaskSubmitRequest,
)
from platform.a2a_gateway.server_service import A2AServerService
from platform.a2a_gateway.streaming import A2ASSEStream
from platform.auth.dependencies import get_auth_service
from platform.auth.service import AuthService
from platform.common.dependencies import get_db
from platform.mcp.exceptions import MCPError, MCPPolicyDeniedError
from platform.mcp.schemas import MCPInitializeRequest, MCPToolCallRequest
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


async def _authenticate_principal(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    header = request.headers.get("Authorization", "")
    token = request.query_params.get("token")
    if header.startswith("Bearer "):
        token = header.removeprefix("Bearer ").strip()
    if not token:
        raise A2AAuthenticationError()
    try:
        return await auth_service.validate_token(token)
    except Exception as exc:
        raise A2AAuthenticationError() from exc


def _is_operator(principal: dict[str, Any]) -> bool:
    roles = principal.get("roles")
    if not isinstance(roles, list):
        return False
    operator_roles = {"owner", "admin", "platform_operator", "operator"}
    return any(isinstance(role, dict) and role.get("role") in operator_roles for role in roles)


def _body(exc: A2AError) -> dict[str, Any]:
    payload = {"code": exc.code}
    payload.update(exc.details)
    return payload


def _mcp_error_body(exc: MCPError) -> dict[str, Any]:
    return {
        "code": -32603,
        "message": exc.message,
        "data": {"code": exc.code, **exc.details},
    }


async def _handle_mcp(action: Callable[[], Awaitable[Any]]) -> Any:
    try:
        return await action()
    except MCPError as exc:
        return JSONResponse(status_code=exc.status_code, content=_mcp_error_body(exc))


async def _handle(action: Callable[[], Awaitable[Any]]) -> Any:
    try:
        return await action()
    except A2AError as exc:
        return JSONResponse(status_code=exc.status_code, content=_body(exc))


@router.get("/.well-known/agent.json")
async def get_platform_agent_card(
    request: Request,
    server_service: A2AServerService = Depends(get_a2a_server_service),
) -> Any:
    base_url = str(request.base_url).rstrip("/")
    return await _handle(lambda: server_service.get_platform_agent_card(base_url=base_url))


@router.post("/api/v1/a2a/tasks", status_code=status.HTTP_202_ACCEPTED)
async def submit_task(
    payload: A2ATaskSubmitRequest,
    principal: dict[str, Any] = Depends(_authenticate_principal),
    server_service: A2AServerService = Depends(get_a2a_server_service),
) -> Any:
    return await _handle(lambda: server_service.submit_task(payload, principal=principal))


@router.get("/api/v1/a2a/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    principal: dict[str, Any] = Depends(_authenticate_principal),
    server_service: A2AServerService = Depends(get_a2a_server_service),
) -> Any:
    return await _handle(lambda: server_service.get_task_status(task_id, principal=principal))


@router.delete("/api/v1/a2a/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    principal: dict[str, Any] = Depends(_authenticate_principal),
    server_service: A2AServerService = Depends(get_a2a_server_service),
) -> Any:
    return await _handle(lambda: server_service.cancel_task(task_id, principal=principal))


@router.post(
    "/api/v1/a2a/tasks/{task_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_follow_up(
    task_id: str,
    payload: A2AFollowUpRequest,
    principal: dict[str, Any] = Depends(_authenticate_principal),
    server_service: A2AServerService = Depends(get_a2a_server_service),
) -> Any:
    return await _handle(
        lambda: server_service.submit_follow_up(task_id, payload, principal=principal)
    )


@router.get("/api/v1/a2a/tasks/{task_id}/stream")
async def stream_task(
    task_id: str,
    request: Request,
    principal: dict[str, Any] = Depends(_authenticate_principal),
    stream: A2ASSEStream = Depends(get_a2a_stream),
    server_service: A2AServerService = Depends(get_a2a_server_service),
) -> Any:
    existing = await _handle(lambda: server_service.get_task_status(task_id, principal=principal))
    if isinstance(existing, JSONResponse):
        return existing
    last_event_id = request.headers.get("Last-Event-ID")
    return StreamingResponse(
        stream.event_generator(task_id, last_event_id=last_event_id),
        media_type="text/event-stream",
    )


@router.get("/api/v1/a2a/external-endpoints")
async def list_external_endpoints(
    principal: dict[str, Any] = Depends(_authenticate_principal),
    client_service: A2AGatewayClientService = Depends(get_a2a_client_service),
) -> Any:
    async def _action() -> Any:
        if not _is_operator(principal):
            raise A2AAuthorizationError()
        workspace_id = principal.get("workspace_id")
        if not isinstance(workspace_id, str):
            raise A2AAuthorizationError()
        return await client_service.list_external_endpoints(UUID(workspace_id))

    return await _handle(_action)


@router.post(
    "/api/v1/a2a/external-endpoints",
    status_code=status.HTTP_201_CREATED,
)
async def register_external_endpoint(
    payload: A2AExternalEndpointCreate,
    principal: dict[str, Any] = Depends(_authenticate_principal),
    client_service: A2AGatewayClientService = Depends(get_a2a_client_service),
) -> Any:
    async def _action() -> Any:
        if not _is_operator(principal):
            raise A2AAuthorizationError()
        workspace_id = principal.get("workspace_id")
        subject = principal.get("sub")
        if not isinstance(workspace_id, str) or not isinstance(subject, str):
            raise A2AAuthorizationError()
        endpoint = await client_service.register_external_endpoint(
            workspace_id=UUID(workspace_id),
            payload=payload,
            created_by=UUID(subject),
        )
        return A2AExternalEndpointResponse.model_validate(endpoint)

    return await _handle(_action)


@router.delete("/api/v1/a2a/external-endpoints/{endpoint_id}")
async def delete_external_endpoint(
    endpoint_id: UUID,
    principal: dict[str, Any] = Depends(_authenticate_principal),
    client_service: A2AGatewayClientService = Depends(get_a2a_client_service),
) -> Any:
    async def _action() -> Any:
        if not _is_operator(principal):
            raise A2AAuthorizationError()
        workspace_id = principal.get("workspace_id")
        if not isinstance(workspace_id, str):
            raise A2AAuthorizationError()
        endpoint = await client_service.delete_external_endpoint(
            workspace_id=UUID(workspace_id),
            endpoint_id=endpoint_id,
        )
        return A2AExternalEndpointResponse.model_validate(endpoint)

    return await _handle(_action)


@router.post("/api/v1/mcp/protocol/initialize")
async def mcp_initialize(
    payload: MCPInitializeRequest,
    principal: dict[str, Any] = Depends(_authenticate_principal),
    server_service: MCPServerService = Depends(get_mcp_server_service),
) -> Any:
    return await _handle_mcp(lambda: server_service.handle_initialize(payload, principal))


def _mcp_workspace_id(principal: dict[str, Any]) -> UUID:
    workspace_id = principal.get("workspace_id")
    if not isinstance(workspace_id, str):
        raise MCPPolicyDeniedError("workspace_context_required")
    return UUID(workspace_id)


@router.post("/api/v1/mcp/protocol/tools/list")
async def mcp_tools_list(
    principal: dict[str, Any] = Depends(_authenticate_principal),
    server_service: MCPServerService = Depends(get_mcp_server_service),
) -> Any:
    workspace_id = _mcp_workspace_id(principal)
    return await _handle_mcp(lambda: server_service.handle_tools_list(principal, workspace_id))


@router.post("/api/v1/mcp/protocol/tools/call")
async def mcp_tools_call(
    payload: MCPToolCallRequest,
    principal: dict[str, Any] = Depends(_authenticate_principal),
    server_service: MCPServerService = Depends(get_mcp_server_service),
    session: AsyncSession = Depends(get_db),
) -> Any:
    workspace_id = _mcp_workspace_id(principal)
    return await _handle_mcp(
        lambda: server_service.handle_tools_call(
            payload,
            principal,
            workspace_id,
            session,
        )
    )
