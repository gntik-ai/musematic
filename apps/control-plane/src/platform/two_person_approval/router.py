from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from platform.two_person_approval.dependencies import get_two_person_approval_service
from platform.two_person_approval.schemas import (
    ApproveChallengeResponse,
    ChallengeResponse,
    ConsumeChallengeResponse,
    CreateChallengeRequest,
)
from platform.two_person_approval.service import TwoPersonApprovalService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

router = APIRouter(prefix="/2pa", tags=["two-person-approval"])


def _requester_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _require_platform_admin(current_user: dict[str, Any]) -> None:
    roles = current_user.get("roles", [])
    role_names = {str(item.get("role")) for item in roles if isinstance(item, dict)}
    if {"platform_admin", "superadmin"} & role_names:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Platform admin role required")


@router.post(
    "/challenges",
    response_model=ChallengeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_challenge(
    payload: CreateChallengeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    two_pa_service: TwoPersonApprovalService = Depends(get_two_person_approval_service),
) -> ChallengeResponse:
    return await two_pa_service.create_challenge(
        initiator_id=_requester_id(current_user),
        action_type=payload.action_type,
        action_payload=payload.action_payload,
        ttl_seconds=payload.ttl_seconds,
    )


@router.get("/challenges/{challenge_id}", response_model=ChallengeResponse)
async def get_challenge(
    challenge_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    two_pa_service: TwoPersonApprovalService = Depends(get_two_person_approval_service),
) -> ChallengeResponse:
    del current_user
    return await two_pa_service.get_challenge(challenge_id)


@router.post("/challenges/{challenge_id}/approve", response_model=ApproveChallengeResponse)
async def approve_challenge(
    challenge_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    two_pa_service: TwoPersonApprovalService = Depends(get_two_person_approval_service),
) -> ApproveChallengeResponse:
    _require_platform_admin(current_user)
    response = await two_pa_service.approve_challenge(
        challenge_id=challenge_id,
        co_signer_id=_requester_id(current_user),
    )
    return ApproveChallengeResponse(**response.model_dump())


@router.post("/challenges/{challenge_id}/consume", response_model=ConsumeChallengeResponse)
async def consume_challenge(
    challenge_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    two_pa_service: TwoPersonApprovalService = Depends(get_two_person_approval_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> ConsumeChallengeResponse:
    response, payload = await two_pa_service.consume_challenge(
        challenge_id=challenge_id,
        requester_id=_requester_id(current_user),
    )
    action_result: dict[str, Any] = {}
    if response.action_type == "workspace_transfer_ownership":
        workspace = await workspaces_service.commit_ownership_transfer_payload(
            payload,
            _requester_id(current_user),
        )
        action_result = {"workspace": workspace.model_dump(mode="json")}
    return ConsumeChallengeResponse(
        id=response.id,
        action_type=response.action_type,
        status=response.status,
        action_result=action_result,
    )
