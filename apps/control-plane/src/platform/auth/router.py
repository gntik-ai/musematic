from __future__ import annotations

from platform.auth.dependencies import get_auth_service
from platform.auth.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutAllResponse,
    MessageResponse,
    MfaChallengeResponse,
    MfaConfirmRequest,
    MfaConfirmResponse,
    MfaEnrollResponse,
    MfaVerifyRequest,
    RefreshRequest,
    ServiceAccountCreateRequest,
    ServiceAccountCreateResponse,
    TokenPair,
)
from platform.auth.service import AuthService
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _request_context(request: Request) -> tuple[str, str]:
    client = request.client.host if request.client is not None else "0.0.0.0"
    device = request.headers.get("User-Agent", "")
    return client, device


def _roles(current_user: dict[str, Any]) -> list[dict[str, Any]]:
    roles = current_user.get("roles", [])
    return roles if isinstance(roles, list) else []


def _require_platform_admin(current_user: dict[str, Any]) -> None:
    role_names = {str(item.get("role")) for item in _roles(current_user) if isinstance(item, dict)}
    if "platform_admin" in role_names or "superadmin" in role_names:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Platform admin role required")


@router.post("/login", response_model=LoginResponse | MfaChallengeResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginResponse | MfaChallengeResponse:
    ip, device = _request_context(request)
    return await auth_service.login(payload.email, payload.password, ip, device)


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    payload: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    return await auth_service.refresh_token(payload.refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    await auth_service.logout(
        UUID(str(current_user["sub"])),
        UUID(str(current_user["session_id"])),
    )
    return MessageResponse(message="Session terminated")


@router.post("/logout-all", response_model=LogoutAllResponse)
async def logout_all(
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> LogoutAllResponse:
    sessions_revoked = await auth_service.logout_all(UUID(str(current_user["sub"])))
    return LogoutAllResponse(
        message="All sessions terminated",
        sessions_revoked=sessions_revoked,
    )


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def enroll_mfa(
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> MfaEnrollResponse:
    return await auth_service.enroll_mfa(
        UUID(str(current_user["sub"])),
        str(current_user["email"]),
    )


@router.post("/mfa/confirm", response_model=MfaConfirmResponse)
async def confirm_mfa(
    payload: MfaConfirmRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> MfaConfirmResponse:
    return await auth_service.confirm_mfa(UUID(str(current_user["sub"])), payload.totp_code)


@router.post("/mfa/verify", response_model=TokenPair)
async def verify_mfa(
    payload: MfaVerifyRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    return await auth_service.verify_mfa(payload.mfa_token, payload.totp_code)


@router.post("/service-accounts", response_model=ServiceAccountCreateResponse)
async def create_service_account(
    payload: ServiceAccountCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> ServiceAccountCreateResponse:
    _require_platform_admin(current_user)
    return await auth_service.create_service_account(
        name=payload.name,
        role=payload.role.value,
        workspace_id=payload.workspace_id,
    )


@router.post("/service-accounts/{sa_id}/rotate", response_model=MessageResponse)
async def rotate_service_account_key(
    sa_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    _require_platform_admin(current_user)
    new_key = await auth_service.rotate_api_key(sa_id)
    return MessageResponse(message=new_key)


@router.delete("/service-accounts/{sa_id}", response_model=MessageResponse)
async def revoke_service_account(
    sa_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    _require_platform_admin(current_user)
    await auth_service.revoke_service_account(sa_id)
    return MessageResponse(message="Service account revoked")
