from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import ValidationError
from platform.common.tagging.filter_extension import parse_tag_label_filters
from platform.fleets.dependencies import (
    get_fleet_service,
    get_governance_service,
    get_health_service,
)
from platform.fleets.governance import FleetGovernanceChainService
from platform.fleets.health import FleetHealthProjectionService
from platform.fleets.models import FleetStatus
from platform.fleets.schemas import (
    FleetCreate,
    FleetGovernanceChainListResponse,
    FleetGovernanceChainResponse,
    FleetGovernanceChainUpdate,
    FleetHealthProjectionResponse,
    FleetListResponse,
    FleetMemberCreate,
    FleetMemberListResponse,
    FleetMemberResponse,
    FleetMemberRoleUpdate,
    FleetOrchestrationRulesCreate,
    FleetOrchestrationRulesListResponse,
    FleetOrchestrationRulesResponse,
    FleetPolicyBindingCreate,
    FleetPolicyBindingResponse,
    FleetResponse,
    FleetTopologyUpdateRequest,
    FleetTopologyVersionListResponse,
    FleetTopologyVersionResponse,
    FleetUpdate,
    ObserverAssignmentCreate,
    ObserverAssignmentResponse,
)
from platform.fleets.service import FleetService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter(prefix="/api/v1/fleets", tags=["fleets"])


def _workspace_id(request: Request, current_user: dict[str, Any]) -> UUID:
    explicit = current_user.get("workspace_id") or request.headers.get("X-Workspace-ID")
    if explicit is not None:
        return UUID(str(explicit))
    roles = current_user.get("roles")
    if isinstance(roles, list):
        for role in roles:
            if isinstance(role, dict) and role.get("workspace_id"):
                return UUID(str(role["workspace_id"]))
    raise ValidationError("WORKSPACE_REQUIRED", "workspace_id is required")


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


@router.post("", response_model=FleetResponse, status_code=status.HTTP_201_CREATED)
async def create_fleet(
    payload: FleetCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetResponse:
    return await fleet_service.create_fleet(
        _workspace_id(request, current_user),
        payload,
        _actor_id(current_user),
    )


@router.get("", response_model=FleetListResponse)
async def list_fleets(
    request: Request,
    status_filter: FleetStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetListResponse:
    return await fleet_service.list_fleets(
        _workspace_id(request, current_user),
        status=status_filter,
        page=page,
        page_size=size,
        tag_label_filters=parse_tag_label_filters(request),
    )


@router.get("/{fleet_id}", response_model=FleetResponse)
async def get_fleet(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetResponse:
    return await fleet_service.get_fleet(fleet_id, _workspace_id(request, current_user))


@router.put("/{fleet_id}", response_model=FleetResponse)
async def update_fleet(
    fleet_id: UUID,
    payload: FleetUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetResponse:
    return await fleet_service.update_fleet(fleet_id, _workspace_id(request, current_user), payload)


@router.post("/{fleet_id}/archive", response_model=FleetResponse)
async def archive_fleet(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetResponse:
    return await fleet_service.archive_fleet(fleet_id, _workspace_id(request, current_user))


@router.get("/{fleet_id}/health", response_model=FleetHealthProjectionResponse)
async def get_fleet_health(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    health_service: FleetHealthProjectionService = Depends(get_health_service),
) -> FleetHealthProjectionResponse:
    return await health_service.get_health(fleet_id, _workspace_id(request, current_user))


@router.post(
    "/{fleet_id}/members", response_model=FleetMemberResponse, status_code=status.HTTP_201_CREATED
)
async def add_member(
    fleet_id: UUID,
    payload: FleetMemberCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetMemberResponse:
    return await fleet_service.add_member(fleet_id, _workspace_id(request, current_user), payload)


@router.get("/{fleet_id}/members", response_model=FleetMemberListResponse)
async def list_members(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetMemberListResponse:
    return await fleet_service.list_members(fleet_id, _workspace_id(request, current_user))


@router.delete("/{fleet_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    fleet_id: UUID,
    member_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> Response:
    await fleet_service.remove_member(fleet_id, member_id, _workspace_id(request, current_user))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{fleet_id}/members/{member_id}/role", response_model=FleetMemberResponse)
async def update_member_role(
    fleet_id: UUID,
    member_id: UUID,
    payload: FleetMemberRoleUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetMemberResponse:
    return await fleet_service.update_member_role(
        fleet_id,
        member_id,
        _workspace_id(request, current_user),
        payload.role,
    )


@router.put("/{fleet_id}/topology", response_model=FleetTopologyVersionResponse)
async def update_topology(
    fleet_id: UUID,
    payload: FleetTopologyUpdateRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetTopologyVersionResponse:
    return await fleet_service.update_topology(
        fleet_id, _workspace_id(request, current_user), payload
    )


@router.get("/{fleet_id}/topology/history", response_model=FleetTopologyVersionListResponse)
async def get_topology_history(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetTopologyVersionListResponse:
    return await fleet_service.get_topology_history(fleet_id, _workspace_id(request, current_user))


@router.post(
    "/{fleet_id}/policies",
    response_model=FleetPolicyBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bind_policy(
    fleet_id: UUID,
    payload: FleetPolicyBindingCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetPolicyBindingResponse:
    workspace_id = _workspace_id(request, current_user)
    return await fleet_service.bind_policy(
        fleet_id, workspace_id, payload.policy_id, _actor_id(current_user)
    )


@router.delete("/{fleet_id}/policies/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_policy(
    fleet_id: UUID,
    binding_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> Response:
    await fleet_service.unbind_policy(fleet_id, binding_id, _workspace_id(request, current_user))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{fleet_id}/observers",
    response_model=ObserverAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_observer(
    fleet_id: UUID,
    payload: ObserverAssignmentCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> ObserverAssignmentResponse:
    return await fleet_service.assign_observer(
        fleet_id,
        _workspace_id(request, current_user),
        payload.observer_fqn,
    )


@router.delete("/{fleet_id}/observers/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_observer(
    fleet_id: UUID,
    assignment_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> Response:
    await fleet_service.remove_observer(
        fleet_id, assignment_id, _workspace_id(request, current_user)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{fleet_id}/orchestration-rules", response_model=FleetOrchestrationRulesResponse)
async def get_orchestration_rules(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetOrchestrationRulesResponse:
    return await fleet_service.get_orchestration_rules(
        fleet_id, _workspace_id(request, current_user)
    )


@router.put("/{fleet_id}/orchestration-rules", response_model=FleetOrchestrationRulesResponse)
async def update_orchestration_rules(
    fleet_id: UUID,
    payload: FleetOrchestrationRulesCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetOrchestrationRulesResponse:
    return await fleet_service.update_orchestration_rules(
        fleet_id,
        _workspace_id(request, current_user),
        payload,
    )


@router.get(
    "/{fleet_id}/orchestration-rules/history", response_model=FleetOrchestrationRulesListResponse
)
async def get_orchestration_rules_history(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetOrchestrationRulesListResponse:
    return await fleet_service.get_rules_history(fleet_id, _workspace_id(request, current_user))


@router.get("/{fleet_id}/governance-chain", response_model=FleetGovernanceChainResponse)
async def get_governance_chain(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    governance_service: FleetGovernanceChainService = Depends(get_governance_service),
) -> FleetGovernanceChainResponse:
    return await governance_service.get_chain(fleet_id, _workspace_id(request, current_user))


@router.put("/{fleet_id}/governance-chain", response_model=FleetGovernanceChainResponse)
async def update_governance_chain(
    fleet_id: UUID,
    payload: FleetGovernanceChainUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    governance_service: FleetGovernanceChainService = Depends(get_governance_service),
) -> FleetGovernanceChainResponse:
    return await governance_service.update_chain(
        fleet_id, _workspace_id(request, current_user), payload
    )


@router.get("/{fleet_id}/governance-chain/history", response_model=FleetGovernanceChainListResponse)
async def get_governance_chain_history(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    governance_service: FleetGovernanceChainService = Depends(get_governance_service),
) -> FleetGovernanceChainListResponse:
    return await governance_service.get_chain_history(
        fleet_id, _workspace_id(request, current_user)
    )
