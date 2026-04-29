from __future__ import annotations

from platform.accounts.dependencies import get_accounts_service
from platform.accounts.models import InvitationStatus
from platform.accounts.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    ApproveUserRequest,
    ArchiveUserRequest,
    BlockUserRequest,
    CreateInvitationRequest,
    InvitationDetailsResponse,
    InvitationResponse,
    PaginatedInvitationsResponse,
    PendingApprovalsResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    ReactivateUserRequest,
    RegisterRequest,
    RegisterResponse,
    RejectUserRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetMfaResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    RevokeInvitationResponse,
    SuspendUserRequest,
    UnblockUserRequest,
    UnlockResponse,
    UserLifecycleResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from platform.accounts.service import AccountsService
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError, ValidationError
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {str(item.get("role")) for item in roles if isinstance(item, dict)}


def _require_admin(current_user: dict[str, Any]) -> None:
    role_names = _role_names(current_user)
    if {"workspace_admin", "superadmin", "platform_admin"} & role_names:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Workspace admin role required")


def _require_superadmin(current_user: dict[str, Any]) -> None:
    if "superadmin" not in _role_names(current_user):
        raise AuthorizationError("PERMISSION_DENIED", "Superadmin role required")


@router.post("/register", response_model=RegisterResponse, status_code=202)
async def register(
    payload: RegisterRequest,
    request: Request,
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> RegisterResponse:
    source_ip = request.client.host if request.client is not None else "0.0.0.0"
    return await accounts_service.register(payload, source_ip=source_ip)


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> VerifyEmailResponse:
    return await accounts_service.verify_email(payload)


@router.post("/resend-verification", response_model=ResendVerificationResponse, status_code=202)
async def resend_verification(
    payload: ResendVerificationRequest,
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> ResendVerificationResponse:
    return await accounts_service.resend_verification(payload)


@router.patch("/me", response_model=ProfileUpdateResponse, status_code=200)
async def update_my_profile(
    payload: ProfileUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> ProfileUpdateResponse:
    return await accounts_service.update_profile(UUID(str(current_user["sub"])), payload)


@router.get("/me", response_model=ProfileUpdateResponse)
async def get_my_profile(
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> ProfileUpdateResponse:
    return await accounts_service.get_profile(UUID(str(current_user["sub"])))


@router.get("/pending-approvals", response_model=PendingApprovalsResponse)
async def get_pending_approvals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> PendingApprovalsResponse:
    _require_admin(current_user)
    return await accounts_service.get_pending_approvals(page, page_size)


@router.post("/{user_id}/approve", response_model=UserLifecycleResponse)
async def approve_user(
    user_id: UUID,
    payload: ApproveUserRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> UserLifecycleResponse:
    _require_admin(current_user)
    return await accounts_service.approve_user(
        user_id, UUID(str(current_user["sub"])), payload.reason
    )


@router.post("/{user_id}/reject", response_model=UserLifecycleResponse)
async def reject_user(
    user_id: UUID,
    payload: RejectUserRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> UserLifecycleResponse:
    _require_admin(current_user)
    return await accounts_service.reject_user(
        user_id, UUID(str(current_user["sub"])), payload.reason
    )


@router.post("/invitations", response_model=InvitationResponse, status_code=201)
async def create_invitation(
    payload: CreateInvitationRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> InvitationResponse:
    _require_admin(current_user)
    return await accounts_service.create_invitation(payload, UUID(str(current_user["sub"])))


@router.get("/invitations", response_model=PaginatedInvitationsResponse)
async def list_invitations(
    status: InvitationStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> PaginatedInvitationsResponse:
    _require_admin(current_user)
    return await accounts_service.list_invitations(
        UUID(str(current_user["sub"])), status, page, page_size
    )


@router.delete(
    "/invitations/{invitation_id}",
    response_model=RevokeInvitationResponse,
    status_code=200,
    include_in_schema=False,
)
@router.delete(
    "/invitations/{invitation_id}/revoke",
    response_model=RevokeInvitationResponse,
    status_code=200,
)
async def revoke_invitation(
    invitation_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> RevokeInvitationResponse:
    _require_admin(current_user)
    await accounts_service.revoke_invitation(
        invitation_id,
        UUID(str(current_user["sub"])),
        is_superadmin="superadmin" in _role_names(current_user),
    )
    return RevokeInvitationResponse(
        invitation_id=invitation_id,
        status=InvitationStatus.revoked,
    )


@router.get("/invitations/{token}", response_model=InvitationDetailsResponse)
async def get_invitation_details(
    token: str,
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> InvitationDetailsResponse:
    return await accounts_service.get_invitation_details(token)


@router.post(
    "/invitations/{token}/accept", response_model=AcceptInvitationResponse, status_code=201
)
async def accept_invitation(
    token: str,
    payload: AcceptInvitationRequest,
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> AcceptInvitationResponse:
    if payload.token != token:
        raise ValidationError("TOKEN_MISMATCH", "Invitation token mismatch")
    return await accounts_service.accept_invitation(payload)


@router.post("/{user_id}/suspend", response_model=UserLifecycleResponse)
async def suspend_user(
    user_id: UUID,
    payload: SuspendUserRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> UserLifecycleResponse:
    _require_admin(current_user)
    return await accounts_service.suspend_user(
        user_id, UUID(str(current_user["sub"])), payload.reason
    )


@router.post("/{user_id}/reactivate", response_model=UserLifecycleResponse)
async def reactivate_user(
    user_id: UUID,
    payload: ReactivateUserRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> UserLifecycleResponse:
    _require_admin(current_user)
    return await accounts_service.reactivate_user(
        user_id, UUID(str(current_user["sub"])), payload.reason
    )


@router.post("/{user_id}/block", response_model=UserLifecycleResponse)
async def block_user(
    user_id: UUID,
    payload: BlockUserRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> UserLifecycleResponse:
    _require_superadmin(current_user)
    return await accounts_service.block_user(
        user_id, UUID(str(current_user["sub"])), payload.reason
    )


@router.post("/{user_id}/unblock", response_model=UserLifecycleResponse)
async def unblock_user(
    user_id: UUID,
    payload: UnblockUserRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> UserLifecycleResponse:
    _require_superadmin(current_user)
    return await accounts_service.unblock_user(
        user_id, UUID(str(current_user["sub"])), payload.reason
    )


@router.post("/{user_id}/archive", response_model=UserLifecycleResponse)
async def archive_user(
    user_id: UUID,
    payload: ArchiveUserRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> UserLifecycleResponse:
    _require_superadmin(current_user)
    return await accounts_service.archive_user(
        user_id, UUID(str(current_user["sub"])), payload.reason
    )


@router.post("/{user_id}/reset-mfa", response_model=ResetMfaResponse)
async def reset_mfa(
    user_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> ResetMfaResponse:
    _require_admin(current_user)
    return await accounts_service.reset_mfa(user_id, UUID(str(current_user["sub"])))


@router.post("/{user_id}/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    user_id: UUID,
    payload: ResetPasswordRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> ResetPasswordResponse:
    _require_admin(current_user)
    return await accounts_service.reset_password(user_id, UUID(str(current_user["sub"])), payload)


@router.post("/{user_id}/unlock", response_model=UnlockResponse)
async def unlock_user(
    user_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> UnlockResponse:
    _require_admin(current_user)
    return await accounts_service.unlock_user(user_id, UUID(str(current_user["sub"])))
