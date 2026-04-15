from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.composition.dependencies import CompositionServiceDep
from platform.composition.schemas import (
    AgentBlueprintGenerateRequest,
    AgentBlueprintOverrideRequest,
    AgentBlueprintResponse,
    CompositionAuditListResponse,
    CompositionRequestListResponse,
    CompositionRequestResponse,
    CompositionValidationResponse,
    FleetBlueprintGenerateRequest,
    FleetBlueprintOverrideRequest,
    FleetBlueprintResponse,
)
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/api/v1/compositions", tags=["composition"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _workspace_id(
    current_user: dict[str, Any],
    workspace_id: UUID | None,
) -> UUID:
    if workspace_id is not None:
        return workspace_id
    value = current_user.get("workspace_id") or current_user.get("workspace")
    if value is None:
        raise ValueError("workspace_id query parameter is required")
    return UUID(str(value))


@router.post(
    "/agent-blueprint",
    response_model=AgentBlueprintResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_agent_blueprint(
    payload: AgentBlueprintGenerateRequest,
    service: CompositionServiceDep,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> AgentBlueprintResponse:
    """Generate an agent blueprint."""
    return await service.generate_agent_blueprint(payload, _actor_id(current_user))


@router.get("/agent-blueprints/{blueprint_id}", response_model=AgentBlueprintResponse)
async def get_agent_blueprint(
    blueprint_id: UUID,
    service: CompositionServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> AgentBlueprintResponse:
    """Return an agent blueprint."""
    return await service.get_agent_blueprint(
        blueprint_id,
        _workspace_id(current_user, workspace_id),
    )


@router.patch("/agent-blueprints/{blueprint_id}", response_model=AgentBlueprintResponse)
async def override_agent_blueprint(
    blueprint_id: UUID,
    payload: AgentBlueprintOverrideRequest,
    service: CompositionServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> AgentBlueprintResponse:
    """Create a new agent blueprint version with overrides."""
    return await service.override_agent_blueprint(
        blueprint_id,
        payload,
        _actor_id(current_user),
        _workspace_id(current_user, workspace_id),
    )


@router.post(
    "/agent-blueprints/{blueprint_id}/validate",
    response_model=CompositionValidationResponse,
)
async def validate_agent_blueprint(
    blueprint_id: UUID,
    service: CompositionServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CompositionValidationResponse:
    """Validate an agent blueprint."""
    return await service.validate_agent_blueprint(
        blueprint_id,
        _workspace_id(current_user, workspace_id),
        _actor_id(current_user),
    )


@router.post(
    "/fleet-blueprint",
    response_model=FleetBlueprintResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_fleet_blueprint(
    payload: FleetBlueprintGenerateRequest,
    service: CompositionServiceDep,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> FleetBlueprintResponse:
    """Generate a fleet blueprint."""
    return await service.generate_fleet_blueprint(payload, _actor_id(current_user))


@router.get("/fleet-blueprints/{blueprint_id}", response_model=FleetBlueprintResponse)
async def get_fleet_blueprint(
    blueprint_id: UUID,
    service: CompositionServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> FleetBlueprintResponse:
    """Return a fleet blueprint."""
    return await service.get_fleet_blueprint(
        blueprint_id,
        _workspace_id(current_user, workspace_id),
    )


@router.patch("/fleet-blueprints/{blueprint_id}", response_model=FleetBlueprintResponse)
async def override_fleet_blueprint(
    blueprint_id: UUID,
    payload: FleetBlueprintOverrideRequest,
    service: CompositionServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> FleetBlueprintResponse:
    """Create a new fleet blueprint version with overrides."""
    return await service.override_fleet_blueprint(
        blueprint_id,
        payload,
        _actor_id(current_user),
        _workspace_id(current_user, workspace_id),
    )


@router.post(
    "/fleet-blueprints/{blueprint_id}/validate",
    response_model=CompositionValidationResponse,
)
async def validate_fleet_blueprint(
    blueprint_id: UUID,
    service: CompositionServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CompositionValidationResponse:
    """Validate a fleet blueprint."""
    return await service.validate_fleet_blueprint(
        blueprint_id,
        _workspace_id(current_user, workspace_id),
        _actor_id(current_user),
    )


@router.get("/requests/{request_id}/audit", response_model=CompositionAuditListResponse)
async def list_audit_entries(
    request_id: UUID,
    service: CompositionServiceDep,
    workspace_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CompositionAuditListResponse:
    """List audit entries for a composition request."""
    return await service.list_audit_entries(
        request_id,
        _workspace_id(current_user, workspace_id),
        event_type=event_type,
        cursor=cursor,
        limit=limit,
    )


@router.get("/requests/{request_id}", response_model=CompositionRequestResponse)
async def get_request(
    request_id: UUID,
    service: CompositionServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CompositionRequestResponse:
    """Return a composition request."""
    return await service.get_request(request_id, _workspace_id(current_user, workspace_id))


@router.get("/requests", response_model=CompositionRequestListResponse)
async def list_requests(
    service: CompositionServiceDep,
    workspace_id: UUID | None = Query(default=None),
    request_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CompositionRequestListResponse:
    """List composition requests."""
    return await service.list_requests(
        _workspace_id(current_user, workspace_id),
        request_type=request_type,
        status=status_filter,
        cursor=cursor,
        limit=limit,
    )
