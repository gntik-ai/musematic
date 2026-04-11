from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import ValidationError
from platform.registry.dependencies import get_registry_service
from platform.registry.models import LifecycleStatus
from platform.registry.schemas import (
    AgentDiscoveryParams,
    AgentListResponse,
    AgentPatch,
    AgentProfileResponse,
    AgentRevisionListResponse,
    AgentUploadResponse,
    LifecycleAuditListResponse,
    LifecycleTransitionRequest,
    MaturityUpdateRequest,
    NamespaceCreate,
    NamespaceListResponse,
    NamespaceResponse,
)
from platform.registry.service import RegistryService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile

router = APIRouter(prefix="/api/v1", tags=["registry"])


def _workspace_id(request: Request) -> UUID:
    raw_workspace_id = request.headers.get("X-Workspace-ID")
    if not raw_workspace_id:
        raise ValidationError("WORKSPACE_HEADER_REQUIRED", "Missing X-Workspace-ID header")
    try:
        return UUID(raw_workspace_id)
    except ValueError as exc:
        raise ValidationError("WORKSPACE_HEADER_INVALID", "Invalid X-Workspace-ID header") from exc


def _actor_id(current_user: dict[str, Any]) -> UUID | None:
    if current_user.get("agent_profile_id") or current_user.get("agent_id"):
        return None
    subject = current_user.get("sub")
    return UUID(str(subject)) if subject is not None else None


def _requesting_agent_id(current_user: dict[str, Any]) -> UUID | None:
    agent_id = current_user.get("agent_profile_id") or current_user.get("agent_id")
    return UUID(str(agent_id)) if agent_id is not None else None


@router.post("/namespaces", response_model=NamespaceResponse, status_code=201)
async def create_namespace(
    payload: NamespaceCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> NamespaceResponse:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("USER_ID_REQUIRED", "Namespace creation requires a human user")
    return await registry_service.create_namespace(_workspace_id(request), payload, actor_id)


@router.get("/namespaces", response_model=NamespaceListResponse)
async def list_namespaces(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> NamespaceListResponse:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("USER_ID_REQUIRED", "Namespace listing requires a human user")
    return await registry_service.list_namespaces(_workspace_id(request), actor_id)


@router.delete("/namespaces/{namespace_id}", status_code=204)
async def delete_namespace(
    namespace_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> Response:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("USER_ID_REQUIRED", "Namespace deletion requires a human user")
    await registry_service.delete_namespace(_workspace_id(request), namespace_id, actor_id)
    return Response(status_code=204)


@router.post("/agents/upload", response_model=AgentUploadResponse, status_code=201)
async def upload_agent(
    request: Request,
    response: Response,
    namespace_name: str = Form(...),
    package: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> AgentUploadResponse:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("USER_ID_REQUIRED", "Agent upload requires a human user")
    package_bytes = await package.read()
    upload_response = await registry_service.upload_agent(
        workspace_id=_workspace_id(request),
        namespace_name=namespace_name,
        package_bytes=package_bytes,
        filename=package.filename or "package.tar.gz",
        actor_id=actor_id,
    )
    response.status_code = 201 if upload_response.created else 200
    return upload_response


@router.get("/agents/resolve/{fqn:path}", response_model=AgentProfileResponse)
async def resolve_fqn(
    fqn: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> AgentProfileResponse:
    return await registry_service.resolve_fqn(
        fqn,
        workspace_id=_workspace_id(request),
        actor_id=_actor_id(current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )


@router.get("/agents", response_model=AgentListResponse)
async def list_agents(
    request: Request,
    status: LifecycleStatus = Query(default=LifecycleStatus.published),
    maturity_min: int = Query(default=0, ge=0, le=3),
    fqn_pattern: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> AgentListResponse:
    workspace_id = _workspace_id(request)
    params = AgentDiscoveryParams(
        workspace_id=workspace_id,
        status=status,
        maturity_min=maturity_min,
        fqn_pattern=fqn_pattern,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    return await registry_service.list_agents(
        params,
        actor_id=_actor_id(current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )


@router.get("/agents/{agent_id}", response_model=AgentProfileResponse)
async def get_agent(
    agent_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> AgentProfileResponse:
    return await registry_service.get_agent(
        _workspace_id(request),
        agent_id,
        actor_id=_actor_id(current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )


@router.patch("/agents/{agent_id}", response_model=AgentProfileResponse)
async def patch_agent(
    agent_id: UUID,
    payload: AgentPatch,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> AgentProfileResponse:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("USER_ID_REQUIRED", "Agent patch requires a human user")
    return await registry_service.patch_agent(
        _workspace_id(request),
        agent_id,
        payload,
        actor_id,
    )


@router.post("/agents/{agent_id}/transition", response_model=AgentProfileResponse)
async def transition_lifecycle(
    agent_id: UUID,
    payload: LifecycleTransitionRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> AgentProfileResponse:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("USER_ID_REQUIRED", "Lifecycle transition requires a human user")
    return await registry_service.transition_lifecycle(
        _workspace_id(request),
        agent_id,
        payload,
        actor_id,
    )


@router.post("/agents/{agent_id}/maturity", response_model=AgentProfileResponse)
async def update_maturity(
    agent_id: UUID,
    payload: MaturityUpdateRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> AgentProfileResponse:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("USER_ID_REQUIRED", "Maturity updates require a human user")
    return await registry_service.update_maturity(
        _workspace_id(request),
        agent_id,
        payload,
        actor_id,
    )


@router.get("/agents/{agent_id}/revisions", response_model=AgentRevisionListResponse)
async def list_revisions(
    agent_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> AgentRevisionListResponse:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("USER_ID_REQUIRED", "Revision listing requires a human user")
    revisions = await registry_service.list_revisions(
        _workspace_id(request),
        agent_id,
        actor_id,
    )
    return AgentRevisionListResponse(items=revisions, total=len(revisions))


@router.get("/agents/{agent_id}/lifecycle-audit", response_model=LifecycleAuditListResponse)
async def list_lifecycle_audit(
    agent_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    registry_service: RegistryService = Depends(get_registry_service),
) -> LifecycleAuditListResponse:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("USER_ID_REQUIRED", "Lifecycle audit requires a human user")
    return await registry_service.list_lifecycle_audit(_workspace_id(request), agent_id, actor_id)
