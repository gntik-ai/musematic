"""Enterprise `/setup` router for UPD-048 FR-010 through FR-016."""

from __future__ import annotations

from datetime import UTC, datetime
from platform.accounts.first_admin_invite import TenantFirstAdminInviteService
from platform.accounts.metrics import Counter
from platform.accounts.models import SignupSource, User, UserStatus
from platform.accounts.repository import AccountsRepository
from platform.accounts.schemas import (
    CreateInvitationRequest,
    OnboardingInvitationEntry,
    SetupStepCredentials,
    SetupStepInvitations,
    SetupStepMfaVerify,
    SetupStepTos,
    SetupStepWorkspace,
    TenantFirstAdminInviteValidationResponse,
)
from platform.audit.dependencies import build_audit_chain_service
from platform.auth.dependencies import get_auth_service
from platform.auth.schemas import RoleType
from platform.auth.service import AuthService, assert_role_mfa_requirement
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.events.producer import EventProducer
from platform.common.exceptions import ValidationError
from platform.workspaces.repository import WorkspacesRepository
from platform.workspaces.schemas import CreateWorkspaceRequest
from platform.workspaces.service import WorkspacesService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/setup", tags=["setup"])

accounts_setup_mfa_skip_attempt_total = Counter(
    "accounts_setup_mfa_skip_attempt_total",
    "Attempts to call tenant-admin setup steps before MFA enrollment.",
)


@router.get("/validate-token", response_model=TenantFirstAdminInviteValidationResponse)
@router.post("/validate-token", response_model=TenantFirstAdminInviteValidationResponse)
async def validate_token(
    response: Response,
    request: Request,
    token: str = Query(min_length=1),
    session: AsyncSession = Depends(database.get_session),
) -> TenantFirstAdminInviteValidationResponse:
    result = await _invite_service(request, session).validate(token)
    response.set_cookie(
        "setup_session",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )
    return result


@router.post("/step/tos")
async def step_tos(
    payload: SetupStepTos,
    request: Request,
    setup_session: str = Cookie(default=""),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, str]:
    await _invite_service(request, session).record_step(
        setup_session,
        "tos",
        payload.model_dump(mode="json"),
    )
    return {"next_step": "credentials"}


@router.post("/step/credentials")
async def step_credentials(
    payload: SetupStepCredentials,
    request: Request,
    setup_session: str = Cookie(default=""),
    session: AsyncSession = Depends(database.get_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    invitation = await _invite_service(request, session).record_step(
        setup_session,
        "credentials",
        payload.model_dump(mode="json", exclude={"password", "oauth_token"}),
    )
    user = await _ensure_setup_user(invitation.target_email, payload, session, auth_service)
    invitation.setup_step_state = {
        **(invitation.setup_step_state or {}),
        "user_id": str(user.id),
    }
    await session.flush()
    return {"next_step": "mfa"}


@router.post("/step/mfa/start")
async def step_mfa_start(
    request: Request,
    setup_session: str = Cookie(default=""),
    session: AsyncSession = Depends(database.get_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, object]:
    invitation = await _invite_service(request, session)._active_by_token(setup_session)
    user = await _setup_user(invitation, session)
    enrollment = await auth_service.enroll_mfa(user.id, user.email)
    return {
        "totp_secret": enrollment.secret,
        "provisioning_uri": enrollment.provisioning_uri,
        "recovery_codes_to_generate_count": 10,
    }


@router.post("/step/mfa/verify")
async def step_mfa_verify(
    payload: SetupStepMfaVerify,
    request: Request,
    setup_session: str = Cookie(default=""),
    session: AsyncSession = Depends(database.get_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, object]:
    service = _invite_service(request, session)
    invitation = await service._active_by_token(setup_session)
    user = await _setup_user(invitation, session)
    await auth_service.confirm_mfa(user.id, payload.totp_code)
    recovery = await auth_service.regenerate_mfa_recovery_codes(user.id, payload.totp_code)
    await service.record_step(setup_session, "mfa", {}, user_id=user.id)
    return {"next_step": "workspace", "recovery_codes": recovery.recovery_codes}


@router.post("/step/workspace")
async def step_workspace(
    payload: SetupStepWorkspace,
    request: Request,
    setup_session: str = Cookie(default=""),
    session: AsyncSession = Depends(database.get_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, object]:
    service = _invite_service(request, session)
    invitation = await service._active_by_token(setup_session)
    user = await _setup_user(invitation, session)
    await _require_setup_mfa(user, auth_service)
    workspace = await _workspaces_service(request, session).create_workspace(
        user.id,
        CreateWorkspaceRequest(name=payload.name, description=None),
    )
    await service.record_step(
        setup_session,
        "workspace",
        {"workspace_id": str(workspace.id), "name": payload.name},
        user_id=user.id,
    )
    return {"next_step": "invitations", "workspace_id": workspace.id}


@router.post("/step/invitations")
async def step_invitations(
    payload: SetupStepInvitations,
    request: Request,
    setup_session: str = Cookie(default=""),
    session: AsyncSession = Depends(database.get_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, object]:
    from platform.accounts.service import AccountsService

    service = _invite_service(request, session)
    invitation = await service._active_by_token(setup_session)
    user = await _setup_user(invitation, session)
    await _require_setup_mfa(user, auth_service)
    accounts = AccountsService(
        repo=AccountsRepository(session),
        redis=request.app.state.clients["redis"],
        kafka_producer=_producer(request),
        auth_service=auth_service,
        settings=_settings(request),
    )
    sent = 0
    for invite in payload.invitations:
        await accounts.create_invitation(_invitation_request(invite), user.id)
        sent += 1
    await service.record_step(
        setup_session,
        "invitations",
        {"invitations_sent": sent},
        user_id=user.id,
    )
    return {"next_step": "done", "invitations_sent": sent}


@router.post("/complete")
async def complete_setup(
    response: Response,
    request: Request,
    setup_session: str = Cookie(default=""),
    session: AsyncSession = Depends(database.get_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    service = _invite_service(request, session)
    invitation = await service._active_by_token(setup_session)
    user = await _setup_user(invitation, session)
    await _require_setup_mfa(user, auth_service)
    await service.consume(setup_session, user.id)
    response.delete_cookie("setup_session")
    return {"redirect_to": "/admin/dashboard"}


def _invite_service(request: Request, session: AsyncSession) -> TenantFirstAdminInviteService:
    settings = _settings(request)
    producer = _producer(request)
    return TenantFirstAdminInviteService(
        session=session,
        settings=settings,
        producer=producer,
        audit_chain=build_audit_chain_service(session, settings, producer),
        notification_client=getattr(request.app.state, "notifications_service", None),
    )


def _workspaces_service(request: Request, session: AsyncSession) -> WorkspacesService:
    return WorkspacesService(
        repo=WorkspacesRepository(session),
        settings=_settings(request),
        kafka_producer=_producer(request),
    )


async def _ensure_setup_user(
    email: str,
    payload: SetupStepCredentials,
    session: AsyncSession,
    auth_service: AuthService,
) -> User:
    repo = AccountsRepository(session)
    existing = await repo.get_user_by_email(email)
    if existing is None:
        user = await repo.create_user(
            email=email,
            display_name=email.split("@", 1)[0],
            status=UserStatus.active,
            signup_source=SignupSource.invitation,
        )
        user.activated_at = datetime.now(UTC)
    else:
        user = existing
    if payload.method == "password" and payload.password is not None:
        credential = await auth_service.repository.get_credential_by_user_id(user.id)
        if credential is None:
            await auth_service.create_user_credential(user.id, user.email, payload.password)
    await auth_service.assign_user_roles(user.id, ["tenant_admin"], None)
    return user


async def _setup_user(invitation: Any, session: AsyncSession) -> User:
    state = invitation.setup_step_state or {}
    raw_user_id = state.get("user_id")
    if raw_user_id is None:
        raise ValidationError("setup_step_out_of_order", "Credentials step must be completed first")
    user = await session.get(User, UUID(str(raw_user_id)))
    if user is None:
        raise ValidationError("setup_user_missing", "Setup user was not found")
    return user


async def _require_setup_mfa(user: User, auth_service: AuthService) -> None:
    try:
        await assert_role_mfa_requirement("tenant_admin", user, auth_service.repository)
    except Exception:
        accounts_setup_mfa_skip_attempt_total.inc()
        raise


def _invitation_request(invite: OnboardingInvitationEntry) -> CreateInvitationRequest:
    role = RoleType.WORKSPACE_ADMIN if invite.role.endswith("admin") else RoleType.VIEWER
    return CreateInvitationRequest(email=invite.email, roles=[role])


def _settings(request: Request) -> PlatformSettings:
    value = getattr(request.app.state, "settings", None)
    return value if isinstance(value, PlatformSettings) else default_settings


def _producer(request: Request) -> EventProducer | None:
    clients = getattr(request.app.state, "clients", {})
    producer = clients.get("kafka") if isinstance(clients, dict) else None
    return producer if isinstance(producer, EventProducer) else None
