from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.dependencies import get_current_user
from platform.common.exceptions import ValidationError
from platform.fleet_learning.adaptation import FleetAdaptationEngineService
from platform.fleet_learning.dependencies import (
    get_adaptation_service,
    get_performance_service,
    get_personality_service,
    get_transfer_service,
)
from platform.fleet_learning.models import TransferRequestStatus
from platform.fleet_learning.performance import FleetPerformanceProfileService
from platform.fleet_learning.personality import FleetPersonalityProfileService
from platform.fleet_learning.schemas import (
    CrossFleetTransferCreate,
    CrossFleetTransferListResponse,
    CrossFleetTransferResponse,
    FleetAdaptationLogListResponse,
    FleetAdaptationLogResponse,
    FleetAdaptationRuleCreate,
    FleetAdaptationRuleListResponse,
    FleetAdaptationRuleResponse,
    FleetPerformanceProfileListResponse,
    FleetPerformanceProfileQuery,
    FleetPerformanceProfileResponse,
    FleetPersonalityProfileCreate,
    FleetPersonalityProfileResponse,
    TransferRejectRequest,
)
from platform.fleet_learning.transfer import CrossFleetTransferService
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter(prefix="/api/v1/fleets", tags=["fleet-learning"])


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


@router.get("/{fleet_id}/performance-profile", response_model=FleetPerformanceProfileResponse)
async def get_performance_profile(
    fleet_id: UUID,
    request: Request,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    performance_service: FleetPerformanceProfileService = Depends(get_performance_service),
) -> FleetPerformanceProfileResponse:
    query = FleetPerformanceProfileQuery(
        start=start or (datetime.now(UTC) - timedelta(days=1)),
        end=end or datetime.now(UTC),
    )
    return await performance_service.get_profile(
        fleet_id, _workspace_id(request, current_user), query
    )


@router.post("/{fleet_id}/performance-profile/compute", status_code=status.HTTP_202_ACCEPTED)
async def compute_performance_profile(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    performance_service: FleetPerformanceProfileService = Depends(get_performance_service),
) -> dict[str, str]:
    workspace_id = _workspace_id(request, current_user)
    await performance_service.compute_profile(
        fleet_id,
        workspace_id,
        datetime.now(UTC) - timedelta(days=1),
        datetime.now(UTC),
    )
    return {"message": "computation started"}


@router.get(
    "/{fleet_id}/performance-profile/history", response_model=FleetPerformanceProfileListResponse
)
async def get_performance_profile_history(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    performance_service: FleetPerformanceProfileService = Depends(get_performance_service),
) -> FleetPerformanceProfileListResponse:
    items = await performance_service.get_profile_history(
        fleet_id, _workspace_id(request, current_user)
    )
    return FleetPerformanceProfileListResponse(items=items, total=len(items))


@router.get("/{fleet_id}/adaptation-rules", response_model=FleetAdaptationRuleListResponse)
async def list_adaptation_rules(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    adaptation_service: FleetAdaptationEngineService = Depends(get_adaptation_service),
) -> FleetAdaptationRuleListResponse:
    items = await adaptation_service.list_rules(fleet_id, _workspace_id(request, current_user))
    return FleetAdaptationRuleListResponse(items=items, total=len(items))


@router.post(
    "/{fleet_id}/adaptation-rules",
    response_model=FleetAdaptationRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_adaptation_rule(
    fleet_id: UUID,
    payload: FleetAdaptationRuleCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    adaptation_service: FleetAdaptationEngineService = Depends(get_adaptation_service),
) -> FleetAdaptationRuleResponse:
    return await adaptation_service.create_rule(
        fleet_id, _workspace_id(request, current_user), payload
    )


@router.put("/{fleet_id}/adaptation-rules/{rule_id}", response_model=FleetAdaptationRuleResponse)
async def update_adaptation_rule(
    fleet_id: UUID,
    rule_id: UUID,
    payload: FleetAdaptationRuleCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    adaptation_service: FleetAdaptationEngineService = Depends(get_adaptation_service),
) -> FleetAdaptationRuleResponse:
    return await adaptation_service.update_rule(
        fleet_id,
        rule_id,
        _workspace_id(request, current_user),
        payload,
    )


@router.delete("/{fleet_id}/adaptation-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_adaptation_rule(
    fleet_id: UUID,
    rule_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    adaptation_service: FleetAdaptationEngineService = Depends(get_adaptation_service),
) -> Response:
    await adaptation_service.deactivate_rule(
        fleet_id,
        rule_id,
        _workspace_id(request, current_user),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{fleet_id}/adaptation-log", response_model=FleetAdaptationLogListResponse)
async def list_adaptation_log(
    fleet_id: UUID,
    request: Request,
    is_reverted: bool | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    adaptation_service: FleetAdaptationEngineService = Depends(get_adaptation_service),
) -> FleetAdaptationLogListResponse:
    items = await adaptation_service.list_log(
        fleet_id,
        _workspace_id(request, current_user),
        is_reverted=is_reverted,
    )
    return FleetAdaptationLogListResponse(items=items, total=len(items))


@router.post(
    "/{fleet_id}/adaptation-log/{log_id}/revert", response_model=FleetAdaptationLogResponse
)
async def revert_adaptation(
    fleet_id: UUID,
    log_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    adaptation_service: FleetAdaptationEngineService = Depends(get_adaptation_service),
) -> FleetAdaptationLogResponse:
    del fleet_id
    return await adaptation_service.revert_adaptation(log_id, _workspace_id(request, current_user))


@router.post(
    "/{fleet_id}/transfers",
    response_model=CrossFleetTransferResponse,
    status_code=status.HTTP_201_CREATED,
)
async def propose_transfer(
    fleet_id: UUID,
    payload: CrossFleetTransferCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    transfer_service: CrossFleetTransferService = Depends(get_transfer_service),
) -> CrossFleetTransferResponse:
    workspace_id = _workspace_id(request, current_user)
    return await transfer_service.propose(fleet_id, workspace_id, payload, _actor_id(current_user))


@router.get("/{fleet_id}/transfers", response_model=CrossFleetTransferListResponse)
async def list_transfers(
    fleet_id: UUID,
    request: Request,
    role: Literal["source", "target"] | None = Query(default=None),
    status_filter: TransferRequestStatus | None = Query(default=None, alias="status"),
    current_user: dict[str, Any] = Depends(get_current_user),
    transfer_service: CrossFleetTransferService = Depends(get_transfer_service),
) -> CrossFleetTransferListResponse:
    items = await transfer_service.list_for_fleet(
        fleet_id,
        _workspace_id(request, current_user),
        role=role,
        status=status_filter,
    )
    return CrossFleetTransferListResponse(items=items, total=len(items))


@router.get("/transfers/{transfer_id}", response_model=CrossFleetTransferResponse)
async def get_transfer(
    transfer_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    transfer_service: CrossFleetTransferService = Depends(get_transfer_service),
) -> CrossFleetTransferResponse:
    return await transfer_service.get(transfer_id, _workspace_id(request, current_user))


@router.post("/transfers/{transfer_id}/approve", response_model=CrossFleetTransferResponse)
async def approve_transfer(
    transfer_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    transfer_service: CrossFleetTransferService = Depends(get_transfer_service),
) -> CrossFleetTransferResponse:
    return await transfer_service.approve(
        transfer_id,
        _workspace_id(request, current_user),
        _actor_id(current_user),
    )


@router.post("/transfers/{transfer_id}/reject", response_model=CrossFleetTransferResponse)
async def reject_transfer(
    transfer_id: UUID,
    payload: TransferRejectRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    transfer_service: CrossFleetTransferService = Depends(get_transfer_service),
) -> CrossFleetTransferResponse:
    return await transfer_service.reject(transfer_id, _workspace_id(request, current_user), payload)


@router.post("/transfers/{transfer_id}/apply", response_model=CrossFleetTransferResponse)
async def apply_transfer(
    transfer_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    transfer_service: CrossFleetTransferService = Depends(get_transfer_service),
) -> CrossFleetTransferResponse:
    return await transfer_service.apply(transfer_id, _workspace_id(request, current_user))


@router.post("/transfers/{transfer_id}/revert", response_model=CrossFleetTransferResponse)
async def revert_transfer(
    transfer_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    transfer_service: CrossFleetTransferService = Depends(get_transfer_service),
) -> CrossFleetTransferResponse:
    return await transfer_service.revert(transfer_id, _workspace_id(request, current_user))


@router.get("/{fleet_id}/personality-profile", response_model=FleetPersonalityProfileResponse)
async def get_personality_profile(
    fleet_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    personality_service: FleetPersonalityProfileService = Depends(get_personality_service),
) -> FleetPersonalityProfileResponse:
    return await personality_service.get(fleet_id, _workspace_id(request, current_user))


@router.put("/{fleet_id}/personality-profile", response_model=FleetPersonalityProfileResponse)
async def update_personality_profile(
    fleet_id: UUID,
    payload: FleetPersonalityProfileCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    personality_service: FleetPersonalityProfileService = Depends(get_personality_service),
) -> FleetPersonalityProfileResponse:
    return await personality_service.update(fleet_id, _workspace_id(request, current_user), payload)
