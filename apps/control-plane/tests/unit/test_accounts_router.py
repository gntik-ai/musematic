from __future__ import annotations

from platform.accounts.models import InvitationStatus, UserStatus
from platform.accounts.router import (
    _require_admin,
    _require_superadmin,
    _role_names,
    accept_invitation,
    approve_user,
    archive_user,
    block_user,
    create_invitation,
    get_invitation_details,
    get_pending_approvals,
    list_invitations,
    reactivate_user,
    register,
    reject_user,
    resend_verification,
    reset_mfa,
    reset_password,
    revoke_invitation,
    suspend_user,
    unblock_user,
    unlock_user,
    verify_email,
)
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
    ReactivateUserRequest,
    RegisterRequest,
    RegisterResponse,
    RejectUserRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetMfaResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SuspendUserRequest,
    UnblockUserRequest,
    UnlockResponse,
    UserLifecycleResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from platform.auth.schemas import RoleType
from platform.common.exceptions import AuthorizationError, ValidationError
from uuid import uuid4

import pytest

from tests.auth_support import role_claim


class RouterServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.user_id = uuid4()
        self.invitation_id = uuid4()

    async def register(self, payload: RegisterRequest) -> RegisterResponse:
        self.calls.append(("register", (payload,)))
        return RegisterResponse()

    async def verify_email(self, payload: VerifyEmailRequest) -> VerifyEmailResponse:
        self.calls.append(("verify_email", (payload,)))
        return VerifyEmailResponse(user_id=self.user_id, status=UserStatus.active)

    async def resend_verification(
        self,
        payload: ResendVerificationRequest,
    ) -> ResendVerificationResponse:
        self.calls.append(("resend_verification", (payload,)))
        return ResendVerificationResponse()

    async def get_pending_approvals(self, page: int, page_size: int) -> PendingApprovalsResponse:
        self.calls.append(("get_pending_approvals", (page, page_size)))
        return PendingApprovalsResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            has_next=False,
            has_prev=False,
        )

    async def approve_user(self, user_id, actor_id, reason) -> UserLifecycleResponse:
        self.calls.append(("approve_user", (user_id, actor_id, reason)))
        return UserLifecycleResponse(user_id=user_id, status=UserStatus.active)

    async def reject_user(self, user_id, actor_id, reason) -> UserLifecycleResponse:
        self.calls.append(("reject_user", (user_id, actor_id, reason)))
        return UserLifecycleResponse(user_id=user_id, status=UserStatus.archived)

    async def create_invitation(
        self, payload: CreateInvitationRequest, actor_id
    ) -> InvitationResponse:
        self.calls.append(("create_invitation", (payload, actor_id)))
        return InvitationResponse(
            id=self.invitation_id,
            invitee_email=payload.email,
            roles=[role.value for role in payload.roles],
            workspace_ids=payload.workspace_ids,
            status=InvitationStatus.pending,
            expires_at=(payload.workspace_ids and [])
            or __import__("datetime").datetime.now(__import__("datetime").UTC),
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )

    async def list_invitations(
        self, actor_id, status, page, page_size
    ) -> PaginatedInvitationsResponse:
        self.calls.append(("list_invitations", (actor_id, status, page, page_size)))
        return PaginatedInvitationsResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            has_next=False,
            has_prev=False,
        )

    async def revoke_invitation(self, invitation_id, actor_id, *, is_superadmin: bool) -> None:
        self.calls.append(("revoke_invitation", (invitation_id, actor_id, is_superadmin)))

    async def get_invitation_details(self, token: str) -> InvitationDetailsResponse:
        self.calls.append(("get_invitation_details", (token,)))
        return InvitationDetailsResponse(
            invitee_email="invitee@example.com",
            inviter_display_name="Admin User",
            roles=["viewer"],
            message="Welcome",
            expires_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )

    async def accept_invitation(self, payload: AcceptInvitationRequest) -> AcceptInvitationResponse:
        self.calls.append(("accept_invitation", (payload,)))
        return AcceptInvitationResponse(
            user_id=self.user_id,
            email="invitee@example.com",
            status=UserStatus.active,
            display_name=payload.display_name,
        )

    async def suspend_user(self, user_id, actor_id, reason) -> UserLifecycleResponse:
        self.calls.append(("suspend_user", (user_id, actor_id, reason)))
        return UserLifecycleResponse(user_id=user_id, status=UserStatus.suspended)

    async def reactivate_user(self, user_id, actor_id, reason) -> UserLifecycleResponse:
        self.calls.append(("reactivate_user", (user_id, actor_id, reason)))
        return UserLifecycleResponse(user_id=user_id, status=UserStatus.active)

    async def block_user(self, user_id, actor_id, reason) -> UserLifecycleResponse:
        self.calls.append(("block_user", (user_id, actor_id, reason)))
        return UserLifecycleResponse(user_id=user_id, status=UserStatus.blocked)

    async def unblock_user(self, user_id, actor_id, reason) -> UserLifecycleResponse:
        self.calls.append(("unblock_user", (user_id, actor_id, reason)))
        return UserLifecycleResponse(user_id=user_id, status=UserStatus.active)

    async def archive_user(self, user_id, actor_id, reason) -> UserLifecycleResponse:
        self.calls.append(("archive_user", (user_id, actor_id, reason)))
        return UserLifecycleResponse(user_id=user_id, status=UserStatus.archived)

    async def reset_mfa(self, user_id, actor_id) -> ResetMfaResponse:
        self.calls.append(("reset_mfa", (user_id, actor_id)))
        return ResetMfaResponse(user_id=user_id, mfa_cleared=True)

    async def reset_password(self, user_id, actor_id, payload) -> ResetPasswordResponse:
        self.calls.append(("reset_password", (user_id, actor_id, payload)))
        return ResetPasswordResponse(user_id=user_id, password_reset_initiated=True)

    async def unlock_user(self, user_id, actor_id) -> UnlockResponse:
        self.calls.append(("unlock_user", (user_id, actor_id)))
        return UnlockResponse(user_id=user_id, unlocked=True)


def _admin_user() -> dict[str, object]:
    return {
        "sub": str(uuid4()),
        "roles": [role_claim("workspace_admin")],
    }


def _superadmin_user() -> dict[str, object]:
    return {
        "sub": str(uuid4()),
        "roles": [role_claim("superadmin")],
    }


def test_role_helpers_enforce_expected_permissions() -> None:
    admin_user = {"roles": [role_claim("workspace_admin"), {"role": "viewer"}]}
    superadmin_user = {"roles": [role_claim("superadmin")]}

    assert _role_names(admin_user) == {"workspace_admin", "viewer"}
    assert _require_admin(admin_user) is None
    assert _require_superadmin(superadmin_user) is None

    with pytest.raises(AuthorizationError):
        _require_admin({"roles": [role_claim("viewer")]})

    with pytest.raises(AuthorizationError):
        _require_superadmin(admin_user)


@pytest.mark.asyncio
async def test_public_routes_delegate_to_service() -> None:
    service = RouterServiceStub()
    register_payload = RegisterRequest(
        email="user@example.com",
        display_name="Jane Smith",
        password="StrongP@ssw0rd!",
    )
    verify_payload = VerifyEmailRequest(token="verify-token")
    resend_payload = ResendVerificationRequest(email="user@example.com")
    accept_payload = AcceptInvitationRequest(
        token="invite-token",
        display_name="Invitee User",
        password="StrongP@ssw0rd!",
    )

    register_response = await register(register_payload, accounts_service=service)
    verify_response = await verify_email(verify_payload, accounts_service=service)
    resend_response = await resend_verification(resend_payload, accounts_service=service)
    details_response = await get_invitation_details("invite-token", accounts_service=service)
    accept_response = await accept_invitation(
        "invite-token",
        accept_payload,
        accounts_service=service,
    )

    assert register_response == RegisterResponse()
    assert verify_response.status == UserStatus.active
    assert resend_response == ResendVerificationResponse()
    assert details_response.invitee_email == "invitee@example.com"
    assert accept_response.display_name == "Invitee User"

    with pytest.raises(ValidationError):
        await accept_invitation(
            "path-token",
            accept_payload.model_copy(update={"token": "body-token"}),
            accounts_service=service,
        )


@pytest.mark.asyncio
async def test_admin_routes_delegate_to_service() -> None:
    service = RouterServiceStub()
    current_user = _admin_user()
    user_id = uuid4()

    approvals = await get_pending_approvals(
        page=1,
        page_size=20,
        current_user=current_user,
        accounts_service=service,
    )
    approved = await approve_user(
        user_id,
        ApproveUserRequest(reason="approved"),
        current_user=current_user,
        accounts_service=service,
    )
    rejected = await reject_user(
        user_id,
        RejectUserRequest(reason="rejected"),
        current_user=current_user,
        accounts_service=service,
    )
    invitation = await create_invitation(
        CreateInvitationRequest(email="invitee@example.com", roles=[RoleType.VIEWER]),
        current_user=current_user,
        accounts_service=service,
    )
    invitations = await list_invitations(
        status=InvitationStatus.pending,
        page=1,
        page_size=20,
        current_user=current_user,
        accounts_service=service,
    )
    revoked = await revoke_invitation(
        service.invitation_id,
        current_user=current_user,
        accounts_service=service,
    )
    suspended = await suspend_user(
        user_id,
        SuspendUserRequest(reason="investigation"),
        current_user=current_user,
        accounts_service=service,
    )
    reactivated = await reactivate_user(
        user_id,
        ReactivateUserRequest(reason="resolved"),
        current_user=current_user,
        accounts_service=service,
    )
    reset_mfa_response = await reset_mfa(
        user_id,
        current_user=current_user,
        accounts_service=service,
    )
    reset_password_response = await reset_password(
        user_id,
        ResetPasswordRequest(force_change_on_login=True),
        current_user=current_user,
        accounts_service=service,
    )
    unlocked = await unlock_user(
        user_id,
        current_user=current_user,
        accounts_service=service,
    )

    assert approvals.total == 0
    assert approved.status == UserStatus.active
    assert rejected.status == UserStatus.archived
    assert invitation.invitee_email == "invitee@example.com"
    assert invitations.total == 0
    assert revoked.invitation_id == service.invitation_id
    assert revoked.status == InvitationStatus.revoked
    assert suspended.status == UserStatus.suspended
    assert reactivated.status == UserStatus.active
    assert reset_mfa_response.mfa_cleared is True
    assert reset_password_response.password_reset_initiated is True
    assert unlocked.unlocked is True

    with pytest.raises(AuthorizationError):
        await approve_user(
            user_id,
            ApproveUserRequest(reason=None),
            current_user={"sub": str(uuid4()), "roles": [role_claim("viewer")]},
            accounts_service=service,
        )


@pytest.mark.asyncio
async def test_superadmin_routes_require_superadmin_role() -> None:
    service = RouterServiceStub()
    superadmin = _superadmin_user()
    admin = _admin_user()
    user_id = uuid4()

    blocked = await block_user(
        user_id,
        BlockUserRequest(reason="policy violation"),
        current_user=superadmin,
        accounts_service=service,
    )
    unblocked = await unblock_user(
        user_id,
        UnblockUserRequest(reason="appeal approved"),
        current_user=superadmin,
        accounts_service=service,
    )
    archived = await archive_user(
        user_id,
        ArchiveUserRequest(reason="closure"),
        current_user=superadmin,
        accounts_service=service,
    )

    assert blocked.status == UserStatus.blocked
    assert unblocked.status == UserStatus.active
    assert archived.status == UserStatus.archived

    with pytest.raises(AuthorizationError):
        await block_user(
            user_id,
            BlockUserRequest(reason="policy violation"),
            current_user=admin,
            accounts_service=service,
        )
