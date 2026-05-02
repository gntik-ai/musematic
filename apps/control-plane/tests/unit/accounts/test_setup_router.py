from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.accounts import setup_router
from platform.accounts.models import SignupSource, User, UserStatus
from platform.accounts.schemas import (
    OnboardingInvitationEntry,
    SetupStepCredentials,
    SetupStepInvitations,
    SetupStepMfaVerify,
    SetupStepTos,
    SetupStepWorkspace,
    TenantFirstAdminInviteValidationResponse,
)
from platform.auth.schemas import RoleType
from platform.common.exceptions import ValidationError
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import Response


class _Session:
    def __init__(self, user: object | None = None) -> None:
        self.user = user
        self.flushed = 0

    async def flush(self) -> None:
        self.flushed += 1

    async def get(self, _model: type[object], _id: UUID) -> object | None:
        return self.user


class _InviteService:
    def __init__(self, invitation: object) -> None:
        self.invitation = invitation
        self.steps: list[tuple[str, dict[str, object], UUID | None]] = []
        self.consumed: list[UUID] = []

    async def validate(self, token: str) -> TenantFirstAdminInviteValidationResponse:
        assert token == "setup-token"
        return TenantFirstAdminInviteValidationResponse(
            tenant_id=uuid4(),
            tenant_slug="acme",
            tenant_display_name="Acme",
            target_email="admin@example.com",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )

    async def record_step(
        self,
        token: str,
        step: str,
        payload: dict[str, object],
        *,
        user_id: UUID | None = None,
    ) -> object:
        assert token == "setup-token"
        self.steps.append((step, payload, user_id))
        return self.invitation

    async def _active_by_token(self, token: str) -> object:
        assert token == "setup-token"
        return self.invitation

    async def consume(self, token: str, user_id: UUID) -> object:
        assert token == "setup-token"
        self.consumed.append(user_id)
        return self.invitation


class _AuthService:
    def __init__(self) -> None:
        self.repository = SimpleNamespace()
        self.confirmed: list[tuple[UUID, str]] = []

    async def enroll_mfa(self, user_id: UUID, email: str) -> object:
        return SimpleNamespace(secret=f"secret-{user_id}", provisioning_uri=f"otpauth://{email}")

    async def confirm_mfa(self, user_id: UUID, totp_code: str) -> None:
        self.confirmed.append((user_id, totp_code))

    async def regenerate_mfa_recovery_codes(self, _user_id: UUID, _totp_code: str) -> object:
        return SimpleNamespace(recovery_codes=["rc1", "rc2"])


class _WorkspacesService:
    async def create_workspace(self, user_id: UUID, payload: object) -> object:
        return SimpleNamespace(id=uuid4(), owner_id=user_id, name=payload.name)


def _request() -> object:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(clients={"redis": object()}, settings=None),
        ),
    )


@pytest.mark.asyncio
async def test_setup_router_handlers_drive_setup_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    user = SimpleNamespace(id=uuid4(), email="admin@example.com")
    invitation = SimpleNamespace(
        target_email="admin@example.com",
        setup_step_state={"user_id": str(user.id)},
    )
    service = _InviteService(invitation)
    auth = _AuthService()
    session = _Session(user)
    monkeypatch.setattr(setup_router, "_invite_service", lambda _request, _session: service)
    monkeypatch.setattr(
        setup_router,
        "_workspaces_service",
        lambda _request, _session: _WorkspacesService(),
    )

    async def setup_user(_invitation: object, _session: object) -> object:
        return user

    monkeypatch.setattr(setup_router, "_setup_user", setup_user)

    async def require_setup_mfa(required_user: object, required_auth: object) -> None:
        assert required_user is user
        assert required_auth is auth

    monkeypatch.setattr(setup_router, "_require_setup_mfa", require_setup_mfa)

    response = Response()
    validated = await setup_router.validate_token(
        response,
        _request(),
        "setup-token",
        session,  # type: ignore[arg-type]
    )
    assert validated.target_email == "admin@example.com"
    assert "setup_session" in response.headers["set-cookie"]

    assert await setup_router.step_tos(
        SetupStepTos(tos_version="v1", accepted_at_ts=datetime.now(UTC)),
        _request(),
        "setup-token",
        session,  # type: ignore[arg-type]
    ) == {"next_step": "credentials"}

    enrollment = await setup_router.step_mfa_start(
        _request(),
        "setup-token",
        session,  # type: ignore[arg-type]
        auth,  # type: ignore[arg-type]
    )
    assert enrollment["recovery_codes_to_generate_count"] == 10

    verified = await setup_router.step_mfa_verify(
        SetupStepMfaVerify(totp_code="123456"),
        _request(),
        "setup-token",
        session,  # type: ignore[arg-type]
        auth,  # type: ignore[arg-type]
    )
    assert verified == {"next_step": "workspace", "recovery_codes": ["rc1", "rc2"]}

    workspace = await setup_router.step_workspace(
        SetupStepWorkspace(name="Launch"),
        _request(),
        "setup-token",
        session,  # type: ignore[arg-type]
        auth,  # type: ignore[arg-type]
    )
    assert workspace["next_step"] == "invitations"

    complete_response = Response()
    complete = await setup_router.complete_setup(
        complete_response,
        _request(),
        "setup-token",
        session,  # type: ignore[arg-type]
        auth,  # type: ignore[arg-type]
    )
    assert complete == {"redirect_to": "/admin/dashboard"}
    assert service.consumed == [user.id]


@pytest.mark.asyncio
async def test_step_credentials_invitations_and_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    user = SimpleNamespace(id=uuid4(), email="admin@example.com")
    invitation = SimpleNamespace(target_email="admin@example.com", setup_step_state={})
    service = _InviteService(invitation)
    auth = _AuthService()
    session = _Session(user)
    monkeypatch.setattr(setup_router, "_invite_service", lambda _request, _session: service)

    async def ensure_setup_user(
        email: str,
        payload: SetupStepCredentials,
        _session: object,
        _auth_service: object,
    ) -> object:
        assert email == "admin@example.com"
        assert payload.method == "password"
        return user

    monkeypatch.setattr(setup_router, "_ensure_setup_user", ensure_setup_user)
    assert await setup_router.step_credentials(
        SetupStepCredentials(method="password", password="SetupPass1!23"),
        _request(),
        "setup-token",
        session,  # type: ignore[arg-type]
        auth,  # type: ignore[arg-type]
    ) == {"next_step": "mfa"}
    assert invitation.setup_step_state == {"user_id": str(user.id)}

    created_invitations: list[object] = []

    class AccountsServiceStub:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def create_invitation(self, payload: object, inviter_id: UUID) -> None:
            assert inviter_id == user.id
            created_invitations.append(payload)

    import platform.accounts.service as accounts_service_module

    monkeypatch.setattr(accounts_service_module, "AccountsService", AccountsServiceStub)

    async def setup_user(_invitation: object, _session: object) -> object:
        return user

    monkeypatch.setattr(setup_router, "_setup_user", setup_user)

    async def require_setup_mfa(_user: object, _auth_service: object) -> None:
        return None

    monkeypatch.setattr(setup_router, "_require_setup_mfa", require_setup_mfa)
    result = await setup_router.step_invitations(
        SetupStepInvitations(
            invitations=[
                OnboardingInvitationEntry(email="admin2@example.com", role="workspace_admin"),
                OnboardingInvitationEntry(email="viewer@example.com", role="viewer"),
            ]
        ),
        _request(),
        "setup-token",
        session,  # type: ignore[arg-type]
        auth,  # type: ignore[arg-type]
    )
    assert result == {"next_step": "done", "invitations_sent": 2}
    assert [payload.roles for payload in created_invitations] == [
        [RoleType.WORKSPACE_ADMIN],
        [RoleType.VIEWER],
    ]


@pytest.mark.asyncio
async def test_setup_helpers_create_user_and_guard_mfa(monkeypatch: pytest.MonkeyPatch) -> None:
    created_user = User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="admin@example.com",
        display_name="admin",
        status=UserStatus.active,
        signup_source=SignupSource.invitation,
    )

    class AccountsRepositoryStub:
        def __init__(self, _session: object) -> None:
            self.created: list[dict[str, object]] = []

        async def get_user_by_email(self, _email: str) -> None:
            return None

        async def create_user(self, **kwargs: object) -> User:
            self.created.append(kwargs)
            return created_user

    class AuthRepositoryStub:
        async def get_credential_by_user_id(self, _user_id: UUID) -> None:
            return None

    class AuthServiceStub:
        def __init__(self) -> None:
            self.repository = AuthRepositoryStub()
            self.credentials: list[tuple[UUID, str, str]] = []
            self.roles: list[tuple[UUID, list[str], None]] = []

        async def create_user_credential(
            self,
            user_id: UUID,
            email: str,
            password: str,
        ) -> None:
            self.credentials.append((user_id, email, password))

        async def assign_user_roles(
            self,
            user_id: UUID,
            roles: list[str],
            workspace_id: None,
        ) -> None:
            self.roles.append((user_id, roles, workspace_id))

    monkeypatch.setattr(setup_router, "AccountsRepository", AccountsRepositoryStub)
    auth = AuthServiceStub()
    user = await setup_router._ensure_setup_user(
        "admin@example.com",
        SetupStepCredentials(method="password", password="SetupPass1!23"),
        object(),  # type: ignore[arg-type]
        auth,  # type: ignore[arg-type]
    )
    assert user is created_user
    assert created_user.activated_at is not None
    assert auth.credentials
    assert auth.roles == [(created_user.id, ["tenant_admin"], None)]

    with pytest.raises(ValidationError):
        await setup_router._setup_user(SimpleNamespace(setup_step_state={}), _Session())

    user_id = uuid4()
    with pytest.raises(ValidationError):
        await setup_router._setup_user(
            SimpleNamespace(setup_step_state={"user_id": str(user_id)}),
            _Session(None),
        )


@pytest.mark.asyncio
async def test_setup_router_service_factories_and_mfa_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    session = _Session()
    monkeypatch.setattr(setup_router, "build_audit_chain_service", lambda *_args: object())

    invite_service = setup_router._invite_service(request, session)  # type: ignore[arg-type]
    workspaces_service = setup_router._workspaces_service(request, session)  # type: ignore[arg-type]

    assert invite_service.notification_client is None
    assert workspaces_service.settings is setup_router.default_settings.workspaces

    async def reject_mfa(*_args: object) -> None:
        raise RuntimeError("mfa required")

    monkeypatch.setattr(setup_router, "assert_role_mfa_requirement", reject_mfa)
    with pytest.raises(RuntimeError, match="mfa required"):
        await setup_router._require_setup_mfa(
            SimpleNamespace(id=uuid4()),  # type: ignore[arg-type]
            _AuthService(),  # type: ignore[arg-type]
        )
