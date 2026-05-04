from __future__ import annotations

import json
import platform.accounts.service as service_module
from datetime import UTC, datetime, timedelta
from platform.accounts.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidOrExpiredTokenError,
    InvitationAlreadyConsumedError,
    InvitationExpiredError,
    InvitationNotFoundError,
    ProfileCompletionNotAllowedError,
    RateLimitError,
    SelfRegistrationDisabledError,
)
from platform.accounts.models import (
    ApprovalDecision,
    ApprovalRequest,
    EmailVerification,
    Invitation,
    InvitationStatus,
    SignupSource,
    User,
    UserStatus,
)
from platform.accounts.schemas import (
    AcceptInvitationRequest,
    CreateInvitationRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from platform.accounts.service import AccountsService
from platform.auth.schemas import RoleType
from platform.common.exceptions import AuthorizationError, NotFoundError
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


class NotificationClientStub:
    def __init__(self) -> None:
        self.verification_calls: list[dict[str, object]] = []
        self.invitation_calls: list[dict[str, object]] = []

    async def send_verification_email(self, **kwargs) -> None:
        self.verification_calls.append(kwargs)

    async def send_invitation_email(self, **kwargs) -> None:
        self.invitation_calls.append(kwargs)


class AuthServiceStub:
    def __init__(self) -> None:
        self.created_credentials: list[tuple[UUID, str, str]] = []
        self.assigned_roles: list[tuple[UUID, list[str], list[UUID] | None]] = []
        self.invalidated_sessions: list[UUID] = []
        self.reset_mfa_calls: list[UUID] = []
        self.password_reset_calls: list[tuple[UUID, bool]] = []
        self.clear_lockout_calls: list[UUID] = []
        self.repository = SimpleNamespace(
            get_platform_user=self.get_platform_user,
            get_mfa_enrollment=self.get_mfa_enrollment,
        )

    async def create_user_credential(self, user_id: UUID, email: str, password: str) -> None:
        self.created_credentials.append((user_id, email, password))

    async def assign_user_roles(
        self,
        user_id: UUID,
        roles: list[str],
        workspace_ids: list[UUID] | None = None,
    ) -> None:
        self.assigned_roles.append((user_id, roles, workspace_ids))

    async def invalidate_user_sessions(self, user_id: UUID) -> int:
        self.invalidated_sessions.append(user_id)
        return 1

    async def get_platform_user(self, user_id: UUID) -> object | None:
        del user_id
        return None

    async def get_mfa_enrollment(self, user_id: UUID) -> object | None:
        del user_id
        return None

    async def reset_mfa(self, user_id: UUID) -> bool:
        self.reset_mfa_calls.append(user_id)
        return True

    async def initiate_password_reset(
        self,
        user_id: UUID,
        force_change_on_login: bool = True,
    ) -> str:
        self.password_reset_calls.append((user_id, force_change_on_login))
        return "reset-token"

    async def clear_lockout(self, user_id: UUID) -> None:
        self.clear_lockout_calls.append(user_id)


class AccountsRepoStub:
    def __init__(self) -> None:
        self.users_by_id: dict[UUID, User] = {}
        self.users_by_email: dict[str, User] = {}
        self.verifications_by_id: dict[UUID, EmailVerification] = {}
        self.verifications_by_hash: dict[str, EmailVerification] = {}
        self.approvals: dict[UUID, ApprovalRequest] = {}
        self.invitations_by_id: dict[UUID, Invitation] = {}
        self.invitations_by_hash: dict[str, Invitation] = {}
        self.preferences: dict[UUID, SimpleNamespace] = {}
        self.workspace_limit: int | None = None

    async def create_user(
        self,
        email: str,
        display_name: str,
        status: UserStatus,
        signup_source: SignupSource,
        invitation_id: UUID | None = None,
    ) -> User:
        user = User(
            id=uuid4(),
            email=email.lower(),
            display_name=display_name,
            status=status,
            signup_source=signup_source,
            invitation_id=invitation_id,
        )
        user.created_at = datetime.now(UTC)
        user.updated_at = user.created_at
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user
        return user

    async def get_user_by_email(self, email: str) -> User | None:
        return self.users_by_email.get(email.lower())

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        return self.users_by_id.get(user_id)

    async def get_user_preferences(self, user_id: UUID) -> SimpleNamespace | None:
        return self.preferences.get(user_id)

    async def get_user_for_update(self, user_id: UUID) -> User | None:
        return self.users_by_id.get(user_id)

    async def update_user_profile(self, user_id: UUID, *, display_name: str) -> User:
        user = self.users_by_id[user_id]
        user.display_name = display_name
        return user

    async def upsert_user_preferences(
        self,
        user_id: UUID,
        *,
        locale: str | None,
        timezone: str | None,
    ) -> SimpleNamespace:
        preferences = SimpleNamespace(language=locale, timezone=timezone)
        self.preferences[user_id] = preferences
        return preferences

    async def get_user_workspace_limit(self, _user_id: UUID) -> int | None:
        return self.workspace_limit

    async def update_user_status(
        self, user_id: UUID, new_status: UserStatus, **kwargs: object
    ) -> User:
        user = self.users_by_id[user_id]
        user.status = new_status
        user.updated_at = datetime.now(UTC)
        for key, value in kwargs.items():
            setattr(user, key, value)
        return user

    async def create_email_verification(
        self,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> EmailVerification:
        verification = EmailVerification(
            id=uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            consumed=False,
        )
        verification.created_at = datetime.now(UTC)
        verification.updated_at = verification.created_at
        self.verifications_by_id[verification.id] = verification
        self.verifications_by_hash[verification.token_hash] = verification
        return verification

    async def get_active_verification_by_token_hash(
        self, token_hash: str
    ) -> EmailVerification | None:
        verification = self.verifications_by_hash.get(token_hash)
        if verification is None or verification.consumed:
            return None
        return verification

    async def consume_verification(self, verification_id: UUID) -> None:
        self.verifications_by_id[verification_id].consumed = True

    async def increment_resend_count(self, redis_client, user_id: UUID) -> int:
        client = await redis_client._get_client()
        key = f"resend_verify:{user_id}"
        count = int(await client.incr(key))
        if count == 1:
            await client.expire(key, 3600)
        return count

    async def create_approval_request(
        self, user_id: UUID, requested_at: datetime
    ) -> ApprovalRequest:
        approval = ApprovalRequest(id=uuid4(), user_id=user_id, requested_at=requested_at)
        approval.created_at = requested_at
        approval.updated_at = requested_at
        self.approvals[user_id] = approval
        return approval

    async def get_pending_approvals(self, page: int, page_size: int):
        items = []
        for user_id, approval in sorted(
            self.approvals.items(), key=lambda item: item[1].requested_at
        ):
            user = self.users_by_id[user_id]
            if user.status != UserStatus.pending_approval:
                continue
            items.append(
                {
                    "user_id": user.id,
                    "email": user.email,
                    "display_name": user.display_name,
                    "registered_at": user.created_at,
                    "email_verified_at": user.email_verified_at or approval.requested_at,
                }
            )
        start = (page - 1) * page_size
        page_items = items[start : start + page_size]
        return page_items, len(items)

    async def get_approval_request_for_update(self, user_id: UUID) -> ApprovalRequest | None:
        return self.approvals.get(user_id)

    async def create_invitation(
        self,
        inviter_id: UUID,
        invitee_email: str,
        token_hash: str,
        roles_json: str,
        workspace_ids_json: str | None,
        message: str | None,
        expires_at: datetime,
    ) -> Invitation:
        invitation = Invitation(
            id=uuid4(),
            inviter_id=inviter_id,
            invitee_email=invitee_email.lower(),
            token_hash=token_hash,
            roles_json=roles_json,
            workspace_ids_json=workspace_ids_json,
            invitee_message=message,
            status=InvitationStatus.pending,
            expires_at=expires_at,
        )
        invitation.created_at = datetime.now(UTC)
        invitation.updated_at = invitation.created_at
        self.invitations_by_id[invitation.id] = invitation
        self.invitations_by_hash[token_hash] = invitation
        return invitation

    async def get_invitation_by_token_hash(self, token_hash: str) -> Invitation | None:
        return self.invitations_by_hash.get(token_hash)

    async def consume_invitation(self, invitation_id: UUID, user_id: UUID) -> None:
        invitation = self.invitations_by_id[invitation_id]
        invitation.status = InvitationStatus.consumed
        invitation.consumed_by_user_id = user_id
        invitation.consumed_at = datetime.now(UTC)

    async def revoke_invitation(self, invitation_id: UUID, revoked_by: UUID) -> None:
        invitation = self.invitations_by_id[invitation_id]
        invitation.status = InvitationStatus.revoked
        invitation.revoked_by = revoked_by
        invitation.revoked_at = datetime.now(UTC)

    async def list_invitations_by_inviter(
        self,
        inviter_id: UUID,
        status_filter: InvitationStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Invitation], int]:
        items = [
            invitation
            for invitation in self.invitations_by_id.values()
            if invitation.inviter_id == inviter_id
            and (status_filter is None or invitation.status == status_filter)
        ]
        items.sort(key=lambda item: item.created_at, reverse=True)
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    async def get_invitation_by_id(self, invitation_id: UUID) -> Invitation | None:
        return self.invitations_by_id.get(invitation_id)

    @staticmethod
    def deserialize_roles(invitation: Invitation) -> list[str]:
        return [str(item) for item in json.loads(invitation.roles_json)]

    @staticmethod
    def deserialize_workspace_ids(invitation: Invitation) -> list[UUID] | None:
        if invitation.workspace_ids_json is None:
            return None
        return [UUID(str(item)) for item in json.loads(invitation.workspace_ids_json)]


def _build_service(
    auth_settings,
    *,
    signup_mode: str = "open",
    repo: AccountsRepoStub | None = None,
    redis_client: FakeAsyncRedisClient | None = None,
    producer: RecordingProducer | None = None,
    auth_service: AuthServiceStub | None = None,
    notification_client: NotificationClientStub | None = None,
) -> tuple[
    AccountsService, AccountsRepoStub, AuthServiceStub, RecordingProducer, NotificationClientStub
]:
    repository = repo or AccountsRepoStub()
    redis = redis_client or FakeAsyncRedisClient()
    kafka_producer = producer or RecordingProducer()
    auth = auth_service or AuthServiceStub()
    notifications = notification_client or NotificationClientStub()
    settings = auth_settings.model_copy(
        update={
            "accounts": auth_settings.accounts.model_copy(
                update={
                    "signup_mode": signup_mode,
                    "email_verify_ttl_hours": 24,
                    "invite_ttl_days": 7,
                    "resend_rate_limit": 3,
                }
            )
        }
    )
    return (
        AccountsService(
            repo=repository,
            redis=redis,
            kafka_producer=kafka_producer,
            auth_service=auth,
            settings=settings,
            notification_client=notifications,
        ),
        repository,
        auth,
        kafka_producer,
        notifications,
    )


async def _register_pending_user(
    service: AccountsService, repo: AccountsRepoStub, email: str = "user@example.com"
) -> str:
    await service.register(
        RegisterRequest(
            email=email,
            display_name="Jane Smith",
            password="StrongP@ssw0rd!",
        )
    )
    latest_call = service.notification_client.verification_calls[-1]
    token = str(latest_call["token"])
    verification = next(iter(repo.verifications_by_id.values()))
    assert verification.token_hash == AccountsService._hash_token(token)
    return token


@pytest.mark.asyncio
async def test_register_creates_user_verification_and_event(auth_settings) -> None:
    service, repo, auth_service, producer, notifications = _build_service(auth_settings)

    response = await service.register(
        RegisterRequest(
            email="USER@Example.COM",
            display_name="Jane Smith",
            password="StrongP@ssw0rd!",
        ),
        correlation_id=uuid4(),
    )

    user = next(iter(repo.users_by_id.values()))
    verification = next(iter(repo.verifications_by_id.values()))
    assert response.message.startswith("If this email is not already registered")
    assert user.email == "user@example.com"
    assert user.status == UserStatus.pending_verification
    assert auth_service.created_credentials == [(user.id, user.email, "StrongP@ssw0rd!")]
    assert verification.user_id == user.id
    assert len(verification.token_hash) == 64
    assert notifications.verification_calls[0]["email"] == user.email
    assert producer.events[0]["event_type"] == "accounts.user.registered"


@pytest.mark.asyncio
async def test_register_is_anti_enumeration_and_respects_signup_mode(auth_settings) -> None:
    service, repo, auth_service, producer, _ = _build_service(auth_settings)
    await repo.create_user(
        email="existing@example.com",
        display_name="Existing User",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )

    duplicate = await service.register(
        RegisterRequest(
            email="existing@example.com",
            display_name="Other Name",
            password="StrongP@ssw0rd!",
        )
    )
    invite_only_service, _, _, _, _ = _build_service(auth_settings, signup_mode="invite_only")

    assert duplicate.message.startswith("If this email is not already registered")
    assert auth_service.created_credentials == []
    assert producer.events == []

    with pytest.raises(SelfRegistrationDisabledError):
        await invite_only_service.register(
            RegisterRequest(
                email="new@example.com",
                display_name="New User",
                password="StrongP@ssw0rd!",
            )
        )


@pytest.mark.asyncio
async def test_verify_email_activates_open_signup_and_creates_approval_for_admin_mode(
    auth_settings,
) -> None:
    open_service, open_repo, _, open_producer, _ = _build_service(auth_settings, signup_mode="open")
    token = await _register_pending_user(open_service, open_repo)

    open_result = await open_service.verify_email(VerifyEmailRequest(token=token))

    open_user = next(iter(open_repo.users_by_id.values()))
    assert open_result.status == UserStatus.active
    assert open_user.email_verified_at is not None
    assert open_user.activated_at is not None
    assert [event["event_type"] for event in open_producer.events[-3:]] == [
        "accounts.user.email_verified",
        "accounts.user.activated",
        "accounts.signup.completed",
    ]

    approval_service, approval_repo, _, approval_producer, _ = _build_service(
        auth_settings,
        signup_mode="admin_approval",
    )
    approval_token = await _register_pending_user(
        approval_service, approval_repo, "approval@example.com"
    )

    approval_result = await approval_service.verify_email(VerifyEmailRequest(token=approval_token))

    approval_user = next(
        user for user in approval_repo.users_by_id.values() if user.email == "approval@example.com"
    )
    assert approval_result.status == UserStatus.pending_approval
    assert approval_user.activated_at is None
    assert approval_repo.approvals[approval_user.id].requested_at == approval_user.email_verified_at
    assert [event["event_type"] for event in approval_producer.events[-1:]] == [
        "accounts.user.email_verified"
    ]


@pytest.mark.asyncio
async def test_default_signup_completion_provisions_workspace_subscription_and_audit(
    auth_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repo, _, producer, _ = _build_service(auth_settings, signup_mode="open")
    repo.session = object()
    workspace_id = uuid4()
    subscription_id = uuid4()
    audit_entries: list[dict[str, object]] = []

    class WorkspacesServiceStub:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def create_default_workspace(
            self,
            user_id: UUID,
            display_name: str,
            *,
            correlation_ctx: object,
        ) -> object:
            assert user_id == user.id
            assert display_name == "Default User"
            assert correlation_ctx is correlation
            return SimpleNamespace(id=workspace_id)

    class SubscriptionServiceStub:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def provision_for_default_workspace(
            self,
            received_workspace_id: UUID,
            *,
            created_by_user_id: UUID,
        ) -> object:
            assert received_workspace_id == workspace_id
            assert created_by_user_id == user.id
            return SimpleNamespace(id=subscription_id)

    class AuditChainServiceStub:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def append(self, *_args: object, **kwargs: object) -> None:
            audit_entries.append(kwargs)

    monkeypatch.setattr(service_module, "WorkspacesService", WorkspacesServiceStub)
    monkeypatch.setattr(service_module, "WorkspacesRepository", lambda _session: object())
    monkeypatch.setattr(service_module, "SubscriptionService", SubscriptionServiceStub)
    monkeypatch.setattr(service_module, "SubscriptionsRepository", lambda _session: object())
    monkeypatch.setattr(service_module, "PlansRepository", lambda _session: object())
    monkeypatch.setattr(service_module, "AuditChainService", AuditChainServiceStub)
    monkeypatch.setattr(service_module, "AuditChainRepository", lambda _session: object())
    user = await repo.create_user(
        email="default@example.com",
        display_name="Default User",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    user.tenant_id = uuid4()
    correlation = AccountsService._correlation(uuid4())

    await service._complete_default_signup(user, correlation)

    assert producer.events[-1]["event_type"] == "accounts.signup.completed"
    assert producer.events[-1]["payload"]["workspace_id"] == str(workspace_id)
    assert producer.events[-1]["payload"]["subscription_id"] == str(subscription_id)
    assert audit_entries[-1]["event_type"] == "accounts.signup.completed"
    assert audit_entries[-1]["tenant_id"] == user.tenant_id

    class FailingWorkspacesServiceStub(WorkspacesServiceStub):
        async def create_default_workspace(
            self,
            user_id: UUID,
            display_name: str,
            *,
            correlation_ctx: object,
        ) -> object:
            raise RuntimeError("defer")

    monkeypatch.setattr(service_module, "WorkspacesService", FailingWorkspacesServiceStub)

    await service._complete_default_signup(user, correlation)

    assert producer.events[-1]["event_type"] == "accounts.signup.completed"
    assert producer.events[-1]["payload"]["workspace_id"] is None
    assert producer.events[-1]["payload"]["subscription_id"] is None


@pytest.mark.asyncio
async def test_verify_email_rejects_expired_or_consumed_token(auth_settings) -> None:
    service, repo, _, _, _ = _build_service(auth_settings)
    token = await _register_pending_user(service, repo)
    verification = next(iter(repo.verifications_by_id.values()))

    verification.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(InvalidOrExpiredTokenError):
        await service.verify_email(VerifyEmailRequest(token=token))

    verification.expires_at = datetime.now(UTC) + timedelta(hours=1)
    verification.consumed = True
    with pytest.raises(InvalidOrExpiredTokenError):
        await service.verify_email(VerifyEmailRequest(token=token))


@pytest.mark.asyncio
async def test_resend_verification_is_silent_for_unknown_accounts_and_rate_limits(
    auth_settings,
) -> None:
    service, repo, _, _, notifications = _build_service(auth_settings)

    silent = await service.resend_verification(
        ResendVerificationRequest(email="missing@example.com")
    )
    token = await _register_pending_user(service, repo)
    assert token

    for _ in range(2):
        await service.resend_verification(ResendVerificationRequest(email="user@example.com"))

    await service.resend_verification(ResendVerificationRequest(email="user@example.com"))

    with pytest.raises(RateLimitError) as exc_info:
        await service.resend_verification(ResendVerificationRequest(email="user@example.com"))

    assert silent.message.startswith("If a pending verification account exists")
    assert exc_info.value.details["retry_after"] == 3600
    assert len(notifications.verification_calls) == 4


@pytest.mark.asyncio
async def test_profile_completion_and_workspace_limit_paths(auth_settings) -> None:
    service, repo, _, producer, _ = _build_service(auth_settings)
    user = await repo.create_user(
        email="profile@example.com",
        display_name="Profile User",
        status=UserStatus.pending_profile_completion,
        signup_source=SignupSource.self_registration,
    )
    active_user = await repo.create_user(
        email="active-profile@example.com",
        display_name="Already Active",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )

    with pytest.raises(NotFoundError):
        await service.get_profile(uuid4())
    initial = await service.get_profile(user.id)
    with pytest.raises(ProfileCompletionNotAllowedError):
        await service.update_profile(
            active_user.id,
            ProfileUpdateRequest(
                display_name="Still Active",
                locale="en",
                timezone="UTC",
            ),
        )
    completed = await service.update_profile(
        user.id,
        ProfileUpdateRequest(
            display_name="Completed User",
            locale="en",
            timezone="Europe/Madrid",
        ),
    )
    repo.workspace_limit = 7

    assert initial.display_name == "Profile User"
    assert completed.status == UserStatus.active
    assert completed.display_name == "Completed User"
    assert completed.locale == "en"
    assert completed.timezone == "Europe/Madrid"
    assert repo.preferences[user.id].language == "en"
    assert await service.get_user_workspace_limit(user.id) == 7
    repo.workspace_limit = None
    assert await service.get_user_workspace_limit(user.id) == int(
        service.platform_settings.workspaces.default_limit
    )
    assert [event["event_type"] for event in producer.events[-2:]] == [
        "accounts.user.profile_completed",
        "accounts.user.activated",
    ]


@pytest.mark.asyncio
async def test_signup_rate_limit_and_e2e_token_recording_edges(auth_settings) -> None:
    redis = FakeAsyncRedisClient()
    service, _, _, _, _ = _build_service(auth_settings, redis_client=redis)

    for index in range(5):
        await service._enforce_signup_rate_limit(f"user{index}@example.com", "192.0.2.10")

    with pytest.raises(RateLimitError):
        await service._enforce_signup_rate_limit("user5@example.com", "192.0.2.10")

    email_redis = FakeAsyncRedisClient()
    email_service, _, _, _, _ = _build_service(auth_settings, redis_client=email_redis)
    for index in range(3):
        await email_service._enforce_signup_rate_limit(
            "same@example.com",
            f"192.0.2.{index}",
        )

    with pytest.raises(RateLimitError):
        await email_service._enforce_signup_rate_limit("same@example.com", "192.0.2.99")

    service.platform_settings = SimpleNamespace(feature_e2e_mode=True)
    await service._record_e2e_verification_token("USER@Example.com", "verify-token")
    client = await redis._get_client()

    assert await client.get("e2e:accounts:verification-token:user@example.com") == "verify-token"


@pytest.mark.asyncio
async def test_pending_approvals_and_approval_decisions(auth_settings) -> None:
    service, repo, _, producer, _ = _build_service(auth_settings)
    user = await repo.create_user(
        email="pending@example.com",
        display_name="Pending User",
        status=UserStatus.pending_approval,
        signup_source=SignupSource.self_registration,
    )
    user.email_verified_at = datetime.now(UTC)
    await repo.create_approval_request(user.id, user.email_verified_at)

    pending = await service.get_pending_approvals(page=1, page_size=20)
    approved = await service.approve_user(user.id, reviewer_id=uuid4(), reason="approved")

    assert pending.total == 1
    assert approved.status == UserStatus.active
    assert repo.approvals[user.id].decision == ApprovalDecision.approved
    assert [event["event_type"] for event in producer.events[-2:]] == [
        "accounts.user.approved",
        "accounts.user.activated",
    ]

    with pytest.raises(NotFoundError):
        await service.approve_user(uuid4(), reviewer_id=uuid4(), reason=None)


@pytest.mark.asyncio
async def test_reject_user_archives_account_and_marks_approval(auth_settings) -> None:
    service, repo, _, producer, _ = _build_service(auth_settings)
    user = await repo.create_user(
        email="reject@example.com",
        display_name="Reject Me",
        status=UserStatus.pending_approval,
        signup_source=SignupSource.self_registration,
    )
    await repo.create_approval_request(user.id, datetime.now(UTC))

    rejected = await service.reject_user(user.id, reviewer_id=uuid4(), reason="rejected")

    assert rejected.status == UserStatus.archived
    assert user.deleted_at is not None
    assert repo.approvals[user.id].decision == ApprovalDecision.rejected
    assert producer.events[-1]["event_type"] == "accounts.user.rejected"


@pytest.mark.asyncio
async def test_create_invitation_get_details_accept_and_list(auth_settings) -> None:
    service, repo, auth_service, producer, notifications = _build_service(auth_settings)
    inviter = await repo.create_user(
        email="admin@example.com",
        display_name="Admin User",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    workspace_id = uuid4()
    create_response = await service.create_invitation(
        CreateInvitationRequest(
            email="invitee@example.com",
            roles=[RoleType.VIEWER],
            workspace_ids=[workspace_id],
            message="Welcome aboard",
        ),
        inviter_id=inviter.id,
    )
    token = str(notifications.invitation_calls[0]["token"])
    details = await service.get_invitation_details(token)
    accepted = await service.accept_invitation(
        AcceptInvitationRequest(
            token=token,
            display_name="Invitee User",
            password="StrongP@ssw0rd!",
        )
    )
    listed = await service.list_invitations(inviter.id, None, page=1, page_size=20)

    assert create_response.status == InvitationStatus.pending
    assert details.inviter_display_name == "Admin User"
    assert accepted.status == UserStatus.active
    assert auth_service.assigned_roles[-1] == (accepted.user_id, ["viewer"], [workspace_id])
    assert listed.total == 1
    assert [event["event_type"] for event in producer.events[-2:]] == [
        "accounts.invitation.accepted",
        "accounts.user.activated",
    ]


@pytest.mark.asyncio
async def test_invitation_failures_and_revoke_permissions(auth_settings) -> None:
    service, repo, _, producer, notifications = _build_service(auth_settings)
    inviter = await repo.create_user(
        email="admin@example.com",
        display_name="Admin User",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    invitation = await service.create_invitation(
        CreateInvitationRequest(email="invitee@example.com", roles=[RoleType.VIEWER]),
        inviter_id=inviter.id,
    )
    token = str(notifications.invitation_calls[0]["token"])
    stored_invitation = repo.invitations_by_id[invitation.id]

    await repo.create_user(
        email="existing@example.com",
        display_name="Existing User",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    with pytest.raises(EmailAlreadyRegisteredError):
        await service.create_invitation(
            CreateInvitationRequest(email="existing@example.com", roles=[RoleType.VIEWER]),
            inviter_id=inviter.id,
        )

    stored_invitation.status = InvitationStatus.consumed
    with pytest.raises(InvitationAlreadyConsumedError):
        await service.accept_invitation(
            AcceptInvitationRequest(
                token=token,
                display_name="Invitee User",
                password="StrongP@ssw0rd!",
            )
        )

    stored_invitation.status = InvitationStatus.revoked
    with pytest.raises(InvitationNotFoundError):
        await service.get_invitation_details(token)

    stored_invitation.status = InvitationStatus.pending
    stored_invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(InvitationExpiredError):
        await service.accept_invitation(
            AcceptInvitationRequest(
                token=token,
                display_name="Invitee User",
                password="StrongP@ssw0rd!",
            )
        )

    stored_invitation.expires_at = datetime.now(UTC) + timedelta(days=1)
    with pytest.raises(AuthorizationError):
        await service.revoke_invitation(stored_invitation.id, requestor_id=uuid4())

    await service.revoke_invitation(stored_invitation.id, requestor_id=inviter.id)
    assert producer.events[-1]["event_type"] == "accounts.invitation.revoked"


@pytest.mark.asyncio
async def test_lifecycle_actions_invalidate_sessions_and_do_not_duplicate_activation(
    auth_settings,
) -> None:
    service, repo, auth_service, producer, _ = _build_service(auth_settings)
    user = await repo.create_user(
        email="active@example.com",
        display_name="Active User",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    user.activated_at = datetime.now(UTC) - timedelta(days=1)
    actor_id = uuid4()

    suspended = await service.suspend_user(user.id, actor_id, "pause")
    reactivated = await service.reactivate_user(user.id, actor_id, "resume")
    blocked = await service.block_user(user.id, actor_id, "blocked")
    unblocked = await service.unblock_user(user.id, actor_id, "restored")
    archived = await service.archive_user(user.id, actor_id, "archive")

    assert suspended.status == UserStatus.suspended
    assert reactivated.status == UserStatus.active
    assert blocked.status == UserStatus.blocked
    assert unblocked.status == UserStatus.active
    assert archived.status == UserStatus.archived
    assert auth_service.invalidated_sessions == [user.id, user.id, user.id]
    assert "accounts.user.activated" not in [event["event_type"] for event in producer.events]

    with pytest.raises(NotFoundError):
        await service.suspend_user(uuid4(), actor_id, "missing")


@pytest.mark.asyncio
async def test_lifecycle_resets_delegate_to_auth_service(auth_settings) -> None:
    service, repo, auth_service, producer, _ = _build_service(auth_settings)
    user = await repo.create_user(
        email="reset@example.com",
        display_name="Reset User",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    actor_id = uuid4()

    reset_mfa_response = await service.reset_mfa(user.id, actor_id)
    reset_password_response = await service.reset_password(
        user.id,
        actor_id,
        ResetPasswordRequest(force_change_on_login=False),
    )
    unlock_response = await service.unlock_user(user.id, actor_id)

    assert reset_mfa_response.mfa_cleared is True
    assert reset_password_response.password_reset_initiated is True
    assert unlock_response.unlocked is True
    assert auth_service.reset_mfa_calls == [user.id]
    assert auth_service.password_reset_calls == [(user.id, False)]
    assert auth_service.clear_lockout_calls == [user.id]
    assert [event["event_type"] for event in producer.events] == [
        "accounts.user.mfa_reset",
        "accounts.user.password_reset_initiated",
    ]


@pytest.mark.asyncio
async def test_invitation_lookup_raises_not_found_when_inviter_missing(auth_settings) -> None:
    service, repo, _, _, _ = _build_service(auth_settings)
    invitation = await repo.create_invitation(
        inviter_id=uuid4(),
        invitee_email="invitee@example.com",
        token_hash=AccountsService._hash_token("invite-token"),
        roles_json='["viewer"]',
        workspace_ids_json=None,
        message=None,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    with pytest.raises(InvitationNotFoundError):
        await service.get_invitation_details("invite-token")

    invitation.status = InvitationStatus.revoked
    with pytest.raises(InvitationNotFoundError):
        await service.get_invitation_details("invite-token")


@pytest.mark.asyncio
async def test_accept_invitation_rejects_duplicate_email(auth_settings) -> None:
    service, repo, _, _, notifications = _build_service(auth_settings)
    inviter = await repo.create_user(
        email="admin@example.com",
        display_name="Admin User",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    invitation = await service.create_invitation(
        CreateInvitationRequest(email="invitee@example.com", roles=[RoleType.VIEWER]),
        inviter_id=inviter.id,
    )
    await repo.create_user(
        email="invitee@example.com",
        display_name="Existing Invitee",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    token = str(notifications.invitation_calls[0]["token"])

    with pytest.raises(EmailAlreadyRegisteredError):
        await service.accept_invitation(
            AcceptInvitationRequest(
                token=token,
                display_name="Invitee User",
                password="StrongP@ssw0rd!",
            )
        )

    assert invitation.id in repo.invitations_by_id


@pytest.mark.asyncio
async def test_pin_clickwrap_dpa_writes_metadata_idempotently(auth_settings) -> None:
    """T085 — pinning records the DPA version once and never overwrites."""
    service, repo, _, _, _ = _build_service(auth_settings)

    class FakeTenant:
        def __init__(self) -> None:
            self.contract_metadata_json: dict[str, object] = {}

    class FakeTenantsRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def get_by_id(self, _tenant_id: UUID) -> FakeTenant:
            return tenant

    class FakeSession:
        def __init__(self) -> None:
            self.flushed = 0

        async def flush(self) -> None:
            self.flushed += 1

    tenant = FakeTenant()
    repo.session = FakeSession()
    user = await repo.create_user(
        email="signup@example.com",
        display_name="New User",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    user.tenant_id = uuid4()

    import platform.tenants.repository as tenants_repo_module

    original_repo = tenants_repo_module.TenantsRepository
    tenants_repo_module.TenantsRepository = FakeTenantsRepository  # type: ignore[misc]
    try:
        await service._pin_clickwrap_dpa_if_needed(user)
        assert "clickwrap_dpa_version_pinned_at" in tenant.contract_metadata_json
        assert tenant.contract_metadata_json["clickwrap_dpa_version"] == "standard-v1"
        assert repo.session.flushed == 1

        # Second call must be a no-op: timestamp does not change, no flush.
        first_pinned_at = tenant.contract_metadata_json["clickwrap_dpa_version_pinned_at"]
        await service._pin_clickwrap_dpa_if_needed(user)
        assert tenant.contract_metadata_json["clickwrap_dpa_version_pinned_at"] == first_pinned_at
        assert repo.session.flushed == 1
    finally:
        tenants_repo_module.TenantsRepository = original_repo  # type: ignore[misc]
