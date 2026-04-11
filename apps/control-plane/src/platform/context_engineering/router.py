from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import ValidationError
from platform.context_engineering.dependencies import get_context_engineering_service
from platform.context_engineering.models import AbTestStatus
from platform.context_engineering.schemas import (
    AbTestCreate,
    AbTestListResponse,
    AbTestResponse,
    AssemblyRecordListResponse,
    AssemblyRecordResponse,
    DriftAlertListResponse,
    ProfileAssignmentCreate,
    ProfileAssignmentResponse,
    ProfileCreate,
    ProfileListResponse,
    ProfileResponse,
)
from platform.context_engineering.service import ContextEngineeringService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

router = APIRouter(prefix="/api/v1/context-engineering", tags=["context-engineering"])


def _workspace_id(request: Request) -> UUID:
    raw_workspace_id = request.headers.get("X-Workspace-ID")
    if not raw_workspace_id:
        raise ValidationError("WORKSPACE_HEADER_REQUIRED", "Missing X-Workspace-ID header")
    try:
        return UUID(raw_workspace_id)
    except ValueError as exc:
        raise ValidationError("WORKSPACE_HEADER_INVALID", "Invalid X-Workspace-ID header") from exc


def _actor_id(current_user: dict[str, Any]) -> UUID:
    if current_user.get("agent_profile_id") or current_user.get("agent_id"):
        raise ValidationError("USER_ID_REQUIRED", "This endpoint requires a human user")
    subject = current_user.get("sub")
    if subject is None:
        raise ValidationError("USER_ID_REQUIRED", "This endpoint requires a human user")
    return UUID(str(subject))


@router.post("/profiles", response_model=ProfileResponse, status_code=201)
async def create_profile(
    payload: ProfileCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> ProfileResponse:
    return await service.create_profile(_workspace_id(request), payload, _actor_id(current_user))


@router.get("/profiles", response_model=ProfileListResponse)
async def list_profiles(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> ProfileListResponse:
    return await service.list_profiles(_workspace_id(request), _actor_id(current_user))


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> ProfileResponse:
    return await service.get_profile(_workspace_id(request), profile_id, _actor_id(current_user))


@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: UUID,
    payload: ProfileCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> ProfileResponse:
    return await service.update_profile(
        _workspace_id(request),
        profile_id,
        payload,
        _actor_id(current_user),
    )


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> Response:
    await service.delete_profile(_workspace_id(request), profile_id, _actor_id(current_user))
    return Response(status_code=204)


@router.post(
    "/profiles/{profile_id}/assign", response_model=ProfileAssignmentResponse, status_code=201
)
async def assign_profile(
    profile_id: UUID,
    payload: ProfileAssignmentCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> ProfileAssignmentResponse:
    return await service.assign_profile(
        _workspace_id(request),
        profile_id,
        payload,
        _actor_id(current_user),
    )


@router.get("/assembly-records", response_model=AssemblyRecordListResponse)
async def list_assembly_records(
    request: Request,
    agent_fqn: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> AssemblyRecordListResponse:
    return await service.list_assembly_records(
        _workspace_id(request),
        _actor_id(current_user),
        agent_fqn=agent_fqn,
        limit=limit,
        offset=offset,
    )


@router.get("/assembly-records/{record_id}", response_model=AssemblyRecordResponse)
async def get_assembly_record(
    record_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> AssemblyRecordResponse:
    return await service.get_assembly_record(
        _workspace_id(request),
        record_id,
        _actor_id(current_user),
    )


@router.get("/drift-alerts", response_model=DriftAlertListResponse)
async def list_drift_alerts(
    request: Request,
    resolved: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> DriftAlertListResponse:
    return await service.list_drift_alerts(
        _workspace_id(request),
        _actor_id(current_user),
        resolved=resolved,
        limit=limit,
        offset=offset,
    )


@router.post("/ab-tests", response_model=AbTestResponse, status_code=201)
async def create_ab_test(
    payload: AbTestCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> AbTestResponse:
    return await service.create_ab_test(_workspace_id(request), payload, _actor_id(current_user))


@router.get("/ab-tests", response_model=AbTestListResponse)
async def list_ab_tests(
    request: Request,
    status: AbTestStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> AbTestListResponse:
    return await service.list_ab_tests(
        _workspace_id(request),
        _actor_id(current_user),
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/ab-tests/{test_id}", response_model=AbTestResponse)
async def get_ab_test(
    test_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> AbTestResponse:
    return await service.get_ab_test(_workspace_id(request), test_id, _actor_id(current_user))


@router.post("/ab-tests/{test_id}/end", response_model=AbTestResponse)
async def end_ab_test(
    test_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ContextEngineeringService = Depends(get_context_engineering_service),
) -> AbTestResponse:
    return await service.end_ab_test(_workspace_id(request), test_id, _actor_id(current_user))
