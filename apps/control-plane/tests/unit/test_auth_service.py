from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.auth.exceptions import (
    AccessTokenExpiredError,
    AccountLockedError,
    AccountPendingApprovalError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    InvalidMfaTokenError,
    InvalidRefreshTokenError,
    MfaAlreadyEnrolledError,
    NoPendingEnrollmentError,
)
from platform.auth.mfa import encrypt_secret, generate_recovery_codes, generate_totp_secret
from platform.auth.password import hash_password
from platform.auth.schemas import PermissionCheckResponse
from platform.auth.service import AuthService
from platform.common.exceptions import NotFoundError
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pyotp
import pytest

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


class FakeAuthRepository:
    def __init__(self) -> None:
        self.user_id = uuid4()
        self.email = "user@example.com"
        self.account_user = SimpleNamespace(
            id=self.user_id,
            email=self.email,
            display_name="User",
            status="active",
        )
        self.platform_user = SimpleNamespace(
            id=self.user_id,
            email=self.email,
            display_name="User",
            status="active",
        )
        self.credential = SimpleNamespace(
            user_id=self.user_id,
            password_hash=hash_password("SecureP@ss123"),
            is_active=True,
        )
        self.roles = [SimpleNamespace(role="viewer", workspace_id=None)]
        self.assigned_roles: list[tuple[UUID, str, UUID | None]] = []
        self.mfa_enrollment = None
        self.auth_attempts: list[str] = []
        self.created_credentials: list[SimpleNamespace] = []
        self.password_reset_tokens: list[SimpleNamespace] = []
        self.service_accounts: dict[str, SimpleNamespace] = {}
        self.db = object()

    async def get_account_user(self, user_id):
        return self.account_user if user_id == self.user_id else None

    async def get_active_suspension_id(self, user_id):
        # UPD-050 — abuse-prevention suspension lookup. Tests run under
        # the assumption that no suspension is active.
        return None

    async def get_account_user_by_email(self, email: str):
        return self.account_user if email.lower() == self.email else None

    async def ensure_account_user(self, user_id, email: str, display_name: str):
        self.account_user = SimpleNamespace(
            id=user_id,
            email=email.lower(),
            display_name=display_name,
            status="active",
        )
        return self.account_user

    async def get_credential_by_email(self, email: str):
        return self.credential if email == self.email else None

    async def get_credential_by_user_id(self, user_id):
        return self.credential if user_id == self.user_id else None

    async def ensure_credential(self, user_id, email: str, password_hash: str):
        self.credential = SimpleNamespace(
            user_id=user_id,
            email=email.lower(),
            password_hash=password_hash,
            is_active=True,
        )
        return self.credential

    async def get_platform_user(self, user_id):
        return self.platform_user if user_id == self.user_id else None

    async def get_platform_user_by_email(self, email: str):
        return self.platform_user if email.lower() == self.email else None

    async def create_platform_user(self, user_id, email: str, display_name: str):
        self.platform_user = SimpleNamespace(
            id=user_id,
            email=email.lower(),
            display_name=display_name,
            status="active",
        )
        return self.platform_user

    async def update_password_hash(self, user_id, new_hash: str) -> None:
        assert user_id == self.user_id
        self.credential.password_hash = new_hash

    async def create_credential(self, user_id, email: str, password_hash: str):
        credential = SimpleNamespace(
            user_id=user_id,
            email=email.lower(),
            password_hash=password_hash,
            is_active=True,
        )
        self.created_credentials.append(credential)
        return credential

    async def get_user_roles(self, user_id, workspace_id):
        del user_id, workspace_id
        return list(self.roles)

    async def assign_user_role(self, user_id, role: str, workspace_id):
        self.assigned_roles.append((user_id, role, workspace_id))
        assignment = SimpleNamespace(user_id=user_id, role=role, workspace_id=workspace_id)
        self.roles.append(assignment)
        return assignment

    async def record_auth_attempt(
        self,
        user_id,
        email: str,
        ip: str,
        user_agent: str,
        outcome: str,
    ) -> None:
        del user_id, email, ip, user_agent
        self.auth_attempts.append(outcome)

    async def get_mfa_enrollment(self, user_id):
        assert user_id == self.user_id
        return self.mfa_enrollment

    async def create_mfa_enrollment(
        self,
        user_id,
        encrypted_secret: str,
        recovery_hashes,
        expires_at,
    ):
        self.mfa_enrollment = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            encrypted_secret=encrypted_secret,
            recovery_codes_hash=list(recovery_hashes),
            status="pending",
            expires_at=expires_at,
            enrolled_at=None,
        )
        return self.mfa_enrollment

    async def activate_mfa_enrollment(self, enrollment_id) -> None:
        assert self.mfa_enrollment is not None
        assert self.mfa_enrollment.id == enrollment_id
        self.mfa_enrollment.status = "active"
        self.mfa_enrollment.enrolled_at = datetime.now(UTC)
        self.mfa_enrollment.expires_at = None

    async def consume_recovery_code(self, enrollment_id, code_index: int, updated_hashes) -> None:
        del code_index
        assert self.mfa_enrollment is not None
        assert self.mfa_enrollment.id == enrollment_id
        self.mfa_enrollment.recovery_codes_hash = list(updated_hashes)

    async def disable_mfa_enrollment(self, user_id) -> bool:
        if self.mfa_enrollment is None or self.mfa_enrollment.user_id != user_id:
            return False
        self.mfa_enrollment.status = "disabled"
        return True

    async def create_password_reset_token(self, user_id, raw_token: str, expires_at):
        token = SimpleNamespace(user_id=user_id, raw_token=raw_token, expires_at=expires_at)
        self.password_reset_tokens.append(token)
        return token

    async def get_active_service_accounts(self):
        return [
            credential
            for credential in self.service_accounts.values()
            if credential.status == "active"
        ]

    async def create_service_account_credential(
        self,
        sa_id,
        name: str,
        key_hash: str,
        role: str,
        workspace_id,
    ):
        credential = SimpleNamespace(
            service_account_id=sa_id,
            name=name,
            api_key_hash=key_hash,
            role=role,
            status="active",
            workspace_id=workspace_id,
        )
        self.service_accounts[str(sa_id)] = credential
        return credential

    async def update_service_account_key_hash(self, sa_id, new_hash: str, status: str) -> None:
        credential = self.service_accounts[str(sa_id)]
        credential.api_key_hash = new_hash
        credential.status = status

    async def get_service_account_by_id(self, sa_id):
        return self.service_accounts.get(str(sa_id))

    async def revoke_service_account(self, sa_id) -> None:
        credential = self.service_accounts[str(sa_id)]
        credential.status = "revoked"


@pytest.mark.asyncio
async def test_login_happy_path_creates_tokens_session_and_event(auth_settings) -> None:
    repository = FakeAuthRepository()
    redis_client = FakeAsyncRedisClient()
    producer = RecordingProducer()
    service = AuthService(repository, redis_client, auth_settings, producer=producer)

    response = await service.login(repository.email, "SecureP@ss123", "127.0.0.1", "pytest")

    assert response.token_type == "bearer"
    assert repository.auth_attempts == ["success"]
    assert producer.events[0]["event_type"] == "auth.user.authenticated"


@pytest.mark.asyncio
async def test_login_wrong_password_increments_lockout_counter(auth_settings) -> None:
    repository = FakeAuthRepository()
    redis_client = FakeAsyncRedisClient()
    service = AuthService(repository, redis_client, auth_settings)

    with pytest.raises(InvalidCredentialsError):
        await service.login(repository.email, "wrong-password", "127.0.0.1", "pytest")

    client = await redis_client._get_client()
    assert await client.get(f"auth:lockout:{repository.user_id}") == 1
    assert repository.auth_attempts == ["failure_password"]


@pytest.mark.asyncio
async def test_login_rejects_pre_locked_account(auth_settings) -> None:
    repository = FakeAuthRepository()
    redis_client = FakeAsyncRedisClient()
    client = await redis_client._get_client()
    await client.set(f"auth:locked:{repository.user_id}", "1", ex=60)
    service = AuthService(repository, redis_client, auth_settings)

    with pytest.raises(AccountLockedError):
        await service.login(repository.email, "SecureP@ss123", "127.0.0.1", "pytest")

    assert repository.auth_attempts == ["failure_locked"]


@pytest.mark.asyncio
async def test_login_rejects_unknown_email(auth_settings) -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)

    with pytest.raises(InvalidCredentialsError):
        await service.login("missing@example.com", "wrong-password", "127.0.0.1", "pytest")

    assert repository.auth_attempts == ["failure_password"]


@pytest.mark.asyncio
async def test_login_rehashes_password_when_parameters_are_outdated(auth_settings) -> None:
    from argon2 import PasswordHasher

    repository = FakeAuthRepository()
    repository.credential.password_hash = PasswordHasher(
        time_cost=2,
        memory_cost=1024,
        parallelism=2,
    ).hash("SecureP@ss123")
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)

    await service.login(repository.email, "SecureP@ss123", "127.0.0.1", "pytest")

    assert repository.credential.password_hash.startswith("$argon2id$")


@pytest.mark.asyncio
async def test_login_with_mfa_challenge_and_recovery_code_verification(auth_settings) -> None:
    repository = FakeAuthRepository()
    redis_client = FakeAsyncRedisClient()
    service = AuthService(repository, redis_client, auth_settings)
    secret = generate_totp_secret()
    recovery_codes, recovery_hashes = generate_recovery_codes()
    repository.mfa_enrollment = SimpleNamespace(
        id=uuid4(),
        user_id=repository.user_id,
        encrypted_secret=encrypt_secret(secret, auth_settings.auth.mfa_encryption_key),
        recovery_codes_hash=list(recovery_hashes),
        status="active",
        expires_at=None,
    )

    challenge = await service.login(repository.email, "SecureP@ss123", "127.0.0.1", "pytest")
    token_pair = await service.verify_mfa(challenge.mfa_token, recovery_codes[0])

    assert challenge.mfa_required is True
    assert token_pair.token_type == "bearer"
    assert len(repository.mfa_enrollment.recovery_codes_hash) == 9


@pytest.mark.asyncio
async def test_refresh_token_rejects_access_tokens(auth_settings) -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)
    login_response = await service.login(repository.email, "SecureP@ss123", "127.0.0.1", "pytest")

    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh_token(login_response.access_token)


@pytest.mark.asyncio
async def test_verify_mfa_rejects_invalid_token_and_code(auth_settings) -> None:
    repository = FakeAuthRepository()
    redis_client = FakeAsyncRedisClient()
    service = AuthService(repository, redis_client, auth_settings)

    with pytest.raises(InvalidMfaTokenError):
        await service.verify_mfa("missing-token", "123456")

    secret = generate_totp_secret()
    repository.mfa_enrollment = SimpleNamespace(
        id=uuid4(),
        user_id=repository.user_id,
        encrypted_secret=encrypt_secret(secret, auth_settings.auth.mfa_encryption_key),
        recovery_codes_hash=[],
        status="active",
        expires_at=None,
    )
    token = await service._create_pending_mfa_token(
        user_id=repository.user_id,
        email=repository.email,
        roles=[],
        ip="127.0.0.1",
        device="pytest",
        session_id=uuid4(),
    )

    with pytest.raises(InvalidMfaCodeError):
        await service.verify_mfa(token, "BADCODE")


@pytest.mark.asyncio
async def test_auth_service_rejects_token_and_mfa_edge_cases(monkeypatch, auth_settings) -> None:
    missing_platform_repository = FakeAuthRepository()
    missing_platform_repository.platform_user = None
    missing_platform_service = AuthService(
        missing_platform_repository,
        FakeAsyncRedisClient(),
        auth_settings,
    )
    with pytest.raises(InvalidCredentialsError):
        await missing_platform_service.login(
            missing_platform_repository.email,
            "SecureP@ss123",
            "127.0.0.1",
            "pytest",
        )
    assert missing_platform_repository.auth_attempts == ["failure_password"]

    repository = FakeAuthRepository()
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)
    expired_token = jwt.encode(
        {
            "sub": str(repository.user_id),
            "type": "access",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        service.settings.signing_key,
        algorithm=service.settings.jwt_algorithm,
    )
    refresh_type_token = jwt.encode(
        {
            "sub": str(repository.user_id),
            "type": "refresh",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        service.settings.signing_key,
        algorithm=service.settings.jwt_algorithm,
    )
    non_string_subject_token = jwt.encode(
        {
            "sub": 123,
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        service.settings.signing_key,
        algorithm=service.settings.jwt_algorithm,
    )
    invalid_uuid_subject_token = jwt.encode(
        {
            "sub": "not-a-uuid",
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        service.settings.signing_key,
        algorithm=service.settings.jwt_algorithm,
    )

    with pytest.raises(AccessTokenExpiredError):
        await service.validate_token(expired_token)
    for token in [refresh_type_token, non_string_subject_token, invalid_uuid_subject_token]:
        with pytest.raises(InvalidAccessTokenError):
            await service.validate_token(token)

    monkeypatch.setattr("platform.auth.service.jwt.decode", lambda *_, **__: ["not", "a", "dict"])
    with pytest.raises(InvalidAccessTokenError):
        await service.validate_token("not-a-real-token")
    monkeypatch.setattr(
        "platform.auth.service.jwt.decode",
        lambda *_, **__: {"sub": 123, "type": "access"},
    )
    with pytest.raises(InvalidAccessTokenError):
        await service.validate_token("not-a-real-token")
    monkeypatch.undo()

    mfa_repository = FakeAuthRepository()
    mfa_service = AuthService(mfa_repository, FakeAsyncRedisClient(), auth_settings)
    pending_without_enrollment = await mfa_service._create_pending_mfa_token(
        user_id=mfa_repository.user_id,
        email=mfa_repository.email,
        roles=[],
        ip="127.0.0.1",
        device="pytest",
        session_id=uuid4(),
    )
    with pytest.raises(InvalidMfaTokenError):
        await mfa_service.verify_mfa(pending_without_enrollment, "123456")

    secret = generate_totp_secret()
    mfa_repository.mfa_enrollment = SimpleNamespace(
        id=uuid4(),
        user_id=mfa_repository.user_id,
        encrypted_secret=encrypt_secret(secret, auth_settings.auth.mfa_encryption_key),
        recovery_codes_hash=[],
        status="active",
        expires_at=None,
    )
    pending_with_enrollment = await mfa_service._create_pending_mfa_token(
        user_id=mfa_repository.user_id,
        email=mfa_repository.email,
        roles=[],
        ip="127.0.0.1",
        device="pytest",
        session_id=uuid4(),
    )
    token_pair = await mfa_service.verify_mfa(pending_with_enrollment, pyotp.TOTP(secret).now())
    assert token_pair.access_token

    created_session = await mfa_service.create_session(
        user_id=mfa_repository.user_id,
        email=mfa_repository.email,
        ip="127.0.0.1",
        device="pytest",
    )
    assert created_session.refresh_token


@pytest.mark.asyncio
async def test_enroll_and_confirm_mfa(auth_settings) -> None:
    repository = FakeAuthRepository()
    producer = RecordingProducer()
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings, producer=producer)

    enrollment = await service.enroll_mfa(repository.user_id, repository.email)
    result = await service.confirm_mfa(
        repository.user_id,
        pyotp.TOTP(enrollment.secret).now(),
    )

    assert enrollment.provisioning_uri.startswith("otpauth://")
    assert result.status == "active"
    assert repository.mfa_enrollment.status == "active"
    assert producer.events[0]["event_type"] == "auth.mfa.enrolled"

    with pytest.raises(MfaAlreadyEnrolledError):
        await service.enroll_mfa(repository.user_id, repository.email)


@pytest.mark.asyncio
async def test_confirm_mfa_rejects_missing_or_invalid_pending_enrollment(auth_settings) -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)

    with pytest.raises(NoPendingEnrollmentError):
        await service.confirm_mfa(repository.user_id, "123456")

    repository.mfa_enrollment = SimpleNamespace(
        id=uuid4(),
        user_id=repository.user_id,
        encrypted_secret=encrypt_secret(
            generate_totp_secret(),
            auth_settings.auth.mfa_encryption_key,
        ),
        recovery_codes_hash=[],
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    with pytest.raises(InvalidMfaCodeError):
        await service.confirm_mfa(repository.user_id, "000000")


@pytest.mark.asyncio
async def test_refresh_logout_and_logout_all(auth_settings) -> None:
    repository = FakeAuthRepository()
    redis_client = FakeAsyncRedisClient()
    producer = RecordingProducer()
    service = AuthService(repository, redis_client, auth_settings, producer=producer)

    session_one = await service.login(repository.email, "SecureP@ss123", "127.0.0.1", "pytest")
    session_two = await service.login(repository.email, "SecureP@ss123", "127.0.0.2", "pytest")

    refreshed = await service.refresh_token(session_one.refresh_token)

    assert refreshed.refresh_token == session_one.refresh_token

    assert await service._get_pending_mfa_token("missing") is None
    decoded = jwt.decode(
        session_one.access_token,
        auth_settings.auth.verification_key,
        algorithms=[auth_settings.auth.jwt_algorithm],
    )
    await service.logout(repository.user_id, UUID(decoded["session_id"]))

    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh_token(session_one.refresh_token)

    assert await service.logout_all(repository.user_id) == 1
    assert session_two.refresh_token


@pytest.mark.asyncio
async def test_service_account_lifecycle(auth_settings) -> None:
    repository = FakeAuthRepository()
    producer = RecordingProducer()
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings, producer=producer)

    created = await service.create_service_account("ci-bot", "service_account", None)
    verified = await service.verify_api_key(created.api_key)
    rotated = await service.rotate_api_key(created.service_account_id)
    rotated_verified = await service.verify_api_key(rotated)
    await service.revoke_service_account(created.service_account_id)

    assert created.api_key.startswith("msk_")
    assert verified is not None
    assert await service.verify_api_key(created.api_key) is None
    assert rotated_verified is not None
    assert await service.verify_api_key(rotated) is None
    assert producer.events[0]["event_type"] == "auth.apikey.rotated"


@pytest.mark.asyncio
async def test_service_account_not_found_paths(auth_settings) -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)
    missing_id = uuid4()

    with pytest.raises(NotFoundError):
        await service.rotate_api_key(missing_id)

    with pytest.raises(NotFoundError):
        await service.revoke_service_account(missing_id)


@pytest.mark.asyncio
async def test_pending_mfa_helpers_handle_non_dict_payload(auth_settings) -> None:
    repository = FakeAuthRepository()
    redis_client = FakeAsyncRedisClient()
    service = AuthService(repository, redis_client, auth_settings)
    client = await redis_client._get_client()
    await client.set(service._pending_mfa_key("bad"), '"string"', ex=60)

    assert await service._get_pending_mfa_token("bad") is None


@pytest.mark.asyncio
async def test_check_permission_delegates_to_rbac(monkeypatch, auth_settings) -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)
    expected = PermissionCheckResponse(
        allowed=True,
        role="viewer",
        resource_type="agent",
        action="read",
        scope="workspace",
    )

    async def fake_check_permission(**kwargs):
        return expected

    monkeypatch.setattr("platform.auth.service.rbac_engine.check_permission", fake_check_permission)

    result = await service.check_permission(repository.user_id, "agent", "read", None)

    assert result == expected

@pytest.mark.asyncio
async def test_login_rejects_inactive_platform_user(auth_settings) -> None:
    repository = FakeAuthRepository()
    repository.platform_user.status = "pending"
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)

    with pytest.raises(InvalidCredentialsError):
        await service.login(repository.email, "SecureP@ss123", "127.0.0.1", "pytest")

    assert repository.auth_attempts == ["failure_password"]


@pytest.mark.asyncio
async def test_login_rejects_pending_approval_with_redirect(auth_settings) -> None:
    repository = FakeAuthRepository()
    repository.platform_user.status = "pending_approval"
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)

    with pytest.raises(AccountPendingApprovalError) as exc_info:
        await service.login(repository.email, "SecureP@ss123", "127.0.0.1", "pytest")

    assert exc_info.value.details == {"redirect_to": "/waiting-approval"}
    assert repository.auth_attempts == ["failure_password"]


@pytest.mark.asyncio
async def test_validate_token_rejects_inactive_missing_and_malformed_users(auth_settings) -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)
    token_pair = await service.login(repository.email, "SecureP@ss123", "127.0.0.1", "pytest")

    payload = await service.validate_token(token_pair.access_token)
    assert payload["sub"] == str(repository.user_id)

    repository.platform_user.status = "suspended"
    with pytest.raises(InactiveUserError):
        await service.validate_token(token_pair.access_token)

    repository.platform_user.status = "pending"
    with pytest.raises(InvalidAccessTokenError):
        await service.validate_token(token_pair.access_token)

    repository.platform_user = None
    with pytest.raises(InvalidAccessTokenError):
        await service.validate_token(token_pair.access_token)

    with pytest.raises(InvalidAccessTokenError):
        await service.validate_token("not-a-jwt")


@pytest.mark.asyncio
async def test_verify_mfa_accepts_recovery_code_and_consumes_it(auth_settings) -> None:
    repository = FakeAuthRepository()
    redis_client = FakeAsyncRedisClient()
    service = AuthService(repository, redis_client, auth_settings)
    secret = generate_totp_secret()
    recovery_codes, recovery_hashes = generate_recovery_codes()
    repository.mfa_enrollment = SimpleNamespace(
        id=uuid4(),
        user_id=repository.user_id,
        encrypted_secret=encrypt_secret(secret, auth_settings.auth.mfa_encryption_key),
        recovery_codes_hash=list(recovery_hashes),
        status="active",
        expires_at=None,
        enrolled_at=datetime.now(UTC),
    )
    mfa_token = await service._create_pending_mfa_token(
        user_id=repository.user_id,
        email=repository.email,
        roles=[{"role": "viewer", "workspace_id": None}],
        ip="127.0.0.1",
        device="pytest",
        session_id=uuid4(),
    )

    token_pair = await service.verify_mfa(mfa_token, recovery_codes[0])

    assert token_pair.access_token
    assert len(repository.mfa_enrollment.recovery_codes_hash) == len(recovery_hashes) - 1
    assert await service._get_pending_mfa_token(mfa_token) is None


@pytest.mark.asyncio
async def test_ensure_user_records_creates_missing_rows_and_rejects_conflicts(
    auth_settings,
) -> None:
    repository = FakeAuthRepository()
    repository.account_user = None
    repository.platform_user = None
    repository.credential = None
    service = AuthService(repository, FakeAsyncRedisClient(), auth_settings)

    await service._ensure_user_records(user_id=repository.user_id, email="USER@Example.COM")

    assert repository.account_user.email == "user@example.com"
    assert repository.platform_user.email == "user@example.com"
    assert repository.credential.email == "user@example.com"

    conflicting_repository = FakeAuthRepository()
    conflicting_repository.account_user.id = uuid4()
    conflicting_service = AuthService(conflicting_repository, FakeAsyncRedisClient(), auth_settings)

    with pytest.raises(InvalidAccessTokenError):
        await conflicting_service._ensure_user_records(
            user_id=uuid4(),
            email=conflicting_repository.email,
        )


@pytest.mark.asyncio
async def test_admin_auth_helpers_delegate_to_repository_and_session_store(auth_settings) -> None:
    repository = FakeAuthRepository()
    redis_client = FakeAsyncRedisClient()
    service = AuthService(repository, redis_client, auth_settings)
    user_id = uuid4()
    workspace_id = uuid4()
    repository.mfa_enrollment = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        status="active",
    )

    await service.create_user_credential(user_id, "New@Example.COM", "SecureP@ss123")
    await service.assign_user_roles(user_id, ["viewer", "operator"], [workspace_id])
    await service.assign_user_roles(user_id, ["viewer"])
    invalidated = await service.invalidate_user_sessions(user_id)
    mfa_cleared = await service.reset_mfa(user_id)
    reset_token = await service.initiate_password_reset(user_id, force_change_on_login=False)
    await service.clear_lockout(user_id)
    challenge = await service.create_pending_mfa_challenge(
        user_id=user_id,
        email="new@example.com",
        ip="127.0.0.1",
        device="pytest",
    )

    assert repository.created_credentials[0].email == "new@example.com"
    assert repository.assigned_roles == [
        (user_id, "viewer", workspace_id),
        (user_id, "operator", workspace_id),
        (user_id, "viewer", None),
    ]
    assert invalidated == 0
    assert mfa_cleared is True
    assert reset_token
    assert repository.password_reset_tokens[0].user_id == user_id
    assert challenge.mfa_token
