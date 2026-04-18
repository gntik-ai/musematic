from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from platform.auth.events import (
    ApiKeyRotatedPayload,
    MfaEnrolledPayload,
    SessionRevokedPayload,
    UserAuthenticatedPayload,
    publish_auth_event,
)
from platform.auth.exceptions import (
    AccessTokenExpiredError,
    AccountLockedError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    InvalidMfaTokenError,
    InvalidRefreshTokenError,
    MfaAlreadyEnrolledError,
    NoPendingEnrollmentError,
)
from platform.auth.lockout import LockoutManager
from platform.auth.mfa import (
    create_provisioning_uri,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_totp_secret,
    verify_recovery_code,
    verify_totp_code,
)
from platform.auth.password import hash_password, needs_rehash, verify_password
from platform.auth.rbac import rbac_engine
from platform.auth.repository import AuthRepository
from platform.auth.schemas import (
    AuthOutcome,
    CredentialStatus,
    LoginResponse,
    MfaChallengeResponse,
    MfaConfirmResponse,
    MfaEnrollResponse,
    MfaStatus,
    PermissionCheckResponse,
    ServiceAccountCreateResponse,
    TokenPair,
)
from platform.auth.session import RedisSessionStore
from platform.auth.tokens import create_access_token, create_token_pair, decode_token
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import AuthSettings, PlatformSettings
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from typing import Any, cast
from uuid import UUID, uuid4

import jwt


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        redis_client: AsyncRedisClient,
        settings: PlatformSettings | AuthSettings,
        *,
        producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.redis_client = redis_client
        self.settings = settings.auth if isinstance(settings, PlatformSettings) else settings
        self.producer = producer
        self.session_store = RedisSessionStore(redis_client, self.settings)
        self.lockout = LockoutManager(redis_client, producer=producer)

    async def login(
        self,
        email: str,
        password: str,
        ip: str,
        device: str,
        session_id: UUID | None = None,
        *,
        correlation_id: UUID | None = None,
    ) -> LoginResponse | MfaChallengeResponse:
        normalized_email = email.strip().lower()
        correlation = correlation_id or uuid4()
        credential = await self.repository.get_credential_by_email(normalized_email)
        user_id = credential.user_id if credential is not None else None

        if user_id is not None and await self.lockout.is_locked(user_id):
            await self.repository.record_auth_attempt(
                user_id,
                normalized_email,
                ip,
                device,
                AuthOutcome.FAILURE_LOCKED.value,
            )
            raise AccountLockedError()

        if (
            credential is None
            or not credential.is_active
            or not verify_password(password, credential.password_hash)
        ):
            if user_id is not None:
                attempts = await self.lockout.increment_failure(
                    user_id,
                    self.settings.lockout_threshold,
                    self.settings.lockout_duration,
                    correlation_id=correlation,
                )
                outcome = (
                    AuthOutcome.FAILURE_LOCKED
                    if attempts >= self.settings.lockout_threshold
                    else AuthOutcome.FAILURE_PASSWORD
                )
                await self.repository.record_auth_attempt(
                    user_id,
                    normalized_email,
                    ip,
                    device,
                    outcome.value,
                )
                if outcome is AuthOutcome.FAILURE_LOCKED:
                    raise AccountLockedError()
            else:
                await self.repository.record_auth_attempt(
                    None,
                    normalized_email,
                    ip,
                    device,
                    AuthOutcome.FAILURE_PASSWORD.value,
                )
            raise InvalidCredentialsError()

        assert user_id is not None
        platform_user = await self.repository.get_platform_user(user_id)
        if platform_user is None or platform_user.status != "active":
            await self.repository.record_auth_attempt(
                user_id,
                normalized_email,
                ip,
                device,
                AuthOutcome.FAILURE_PASSWORD.value,
            )
            raise InvalidCredentialsError()
        if needs_rehash(credential.password_hash):
            await self.repository.update_password_hash(user_id, hash_password(password))

        await self.lockout.reset_failure_counter(user_id)
        roles = await self._serialize_roles(user_id, None)
        enrollment = await self.repository.get_mfa_enrollment(user_id)

        if enrollment is not None and enrollment.status == MfaStatus.ACTIVE.value:
            pending_session_id = session_id or uuid4()
            mfa_token = await self._create_pending_mfa_token(
                user_id=user_id,
                email=normalized_email,
                roles=roles,
                ip=ip,
                device=device,
                session_id=pending_session_id,
            )
            await self.repository.record_auth_attempt(
                user_id,
                normalized_email,
                ip,
                device,
                AuthOutcome.FAILURE_MFA.value,
            )
            return MfaChallengeResponse(mfa_token=mfa_token)

        token_pair = await self._issue_token_pair(
            user_id=user_id,
            email=normalized_email,
            roles=roles,
            ip=ip,
            device=device,
            session_id=session_id or uuid4(),
            correlation_id=correlation,
        )
        await self.repository.record_auth_attempt(
            user_id,
            normalized_email,
            ip,
            device,
            AuthOutcome.SUCCESS.value,
        )
        return LoginResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            expires_in=token_pair.expires_in,
        )

    async def refresh_token(self, refresh_token_str: str) -> TokenPair:
        claims = decode_token(refresh_token_str, self.settings)
        if claims.get("type") != "refresh":
            raise InvalidRefreshTokenError()

        user_id = UUID(str(claims["sub"]))
        session_id = UUID(str(claims["session_id"]))
        jti = str(claims["jti"])
        session = await self.session_store.get_session(user_id, session_id)
        if session is None or str(session["refresh_jti"]) != jti:
            raise InvalidRefreshTokenError()

        access_token = create_access_token(
            user_id=user_id,
            email=str(session["email"]),
            session_id=session_id,
            roles=cast(list[dict[str, Any]], session["roles"]),
            settings=self.settings,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token_str,
            expires_in=self.settings.access_token_ttl,
        )

    async def validate_token(self, token: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self.settings.verification_key,
                algorithms=[self.settings.jwt_algorithm],
            )
        except jwt.ExpiredSignatureError as exc:
            raise AccessTokenExpiredError() from exc
        except jwt.PyJWTError as exc:
            raise InvalidAccessTokenError() from exc

        if not isinstance(payload, dict):
            raise InvalidAccessTokenError()
        if payload.get("type") not in {None, "access"}:
            raise InvalidAccessTokenError()

        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise InvalidAccessTokenError()

        try:
            user_id = UUID(subject)
        except ValueError as exc:
            raise InvalidAccessTokenError() from exc

        platform_user = await self.repository.get_platform_user(user_id)
        if platform_user is None:
            raise InvalidAccessTokenError()
        if platform_user.status in {"blocked", "suspended", "archived"}:
            raise InactiveUserError()
        if platform_user.status != "active":
            raise InvalidAccessTokenError()

        return payload

    async def logout(
        self,
        user_id: UUID,
        session_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> None:
        await self.session_store.delete_session(user_id, session_id)
        await publish_auth_event(
            "auth.session.revoked",
            SessionRevokedPayload(
                user_id=user_id,
                session_id=session_id,
                reason="logout",
            ),
            correlation_id or uuid4(),
            self.producer,
        )

    async def logout_all(self, user_id: UUID) -> int:
        return await self.session_store.delete_all_sessions(user_id)

    async def verify_mfa(self, mfa_token: str, totp_code: str) -> TokenPair:
        pending = await self._get_pending_mfa_token(mfa_token)
        if pending is None:
            raise InvalidMfaTokenError()

        user_id = UUID(str(pending["user_id"]))
        enrollment = await self.repository.get_mfa_enrollment(user_id)
        if enrollment is None or enrollment.status != MfaStatus.ACTIVE.value:
            raise InvalidMfaTokenError()

        secret = decrypt_secret(enrollment.encrypted_secret, self.settings.mfa_encryption_key)
        normalized_code = totp_code.strip().upper()
        verified = verify_totp_code(secret, normalized_code)
        if not verified:
            recovery_index = verify_recovery_code(
                normalized_code,
                list(enrollment.recovery_codes_hash),
            )
            if recovery_index is None:
                raise InvalidMfaCodeError()
            updated_hashes = list(enrollment.recovery_codes_hash)
            updated_hashes.pop(recovery_index)
            await self.repository.consume_recovery_code(
                enrollment.id,
                recovery_index,
                updated_hashes,
            )

        token_pair = await self._issue_token_pair(
            user_id=user_id,
            email=str(pending["email"]),
            roles=cast(list[dict[str, Any]], pending["roles"]),
            ip=str(pending["ip"]),
            device=str(pending["device"]),
            session_id=UUID(str(pending["session_id"])),
            correlation_id=uuid4(),
        )
        await self._delete_pending_mfa_token(mfa_token)
        return token_pair

    async def enroll_mfa(self, user_id: UUID, email: str) -> MfaEnrollResponse:
        existing = await self.repository.get_mfa_enrollment(user_id)
        if existing is not None and existing.status == MfaStatus.ACTIVE.value:
            raise MfaAlreadyEnrolledError()

        secret = generate_totp_secret()
        encrypted_secret = encrypt_secret(secret, self.settings.mfa_encryption_key)
        recovery_codes, recovery_hashes = generate_recovery_codes()
        expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.mfa_enrollment_ttl)
        await self.repository.create_mfa_enrollment(
            user_id=user_id,
            encrypted_secret=encrypted_secret,
            recovery_hashes=recovery_hashes,
            expires_at=expires_at,
        )
        return MfaEnrollResponse(
            secret=secret,
            provisioning_uri=create_provisioning_uri(secret, email),
            recovery_codes=recovery_codes,
        )

    async def confirm_mfa(
        self,
        user_id: UUID,
        totp_code: str,
        *,
        correlation_id: UUID | None = None,
    ) -> MfaConfirmResponse:
        enrollment = await self.repository.get_mfa_enrollment(user_id)
        if (
            enrollment is None
            or enrollment.status != MfaStatus.PENDING.value
            or (enrollment.expires_at is not None and enrollment.expires_at < datetime.now(UTC))
        ):
            raise NoPendingEnrollmentError()

        secret = decrypt_secret(enrollment.encrypted_secret, self.settings.mfa_encryption_key)
        if not verify_totp_code(secret, totp_code.strip()):
            raise InvalidMfaCodeError()

        await self.repository.activate_mfa_enrollment(enrollment.id)
        await publish_auth_event(
            "auth.mfa.enrolled",
            MfaEnrolledPayload(user_id=user_id, method="totp"),
            correlation_id or uuid4(),
            self.producer,
        )
        return MfaConfirmResponse()

    async def create_session(
        self,
        *,
        user_id: UUID,
        email: str,
        ip: str,
        device: str,
        roles: list[dict[str, Any]] | None = None,
        correlation_id: UUID | None = None,
    ) -> TokenPair:
        resolved_roles = roles if roles is not None else await self._serialize_roles(user_id, None)
        return await self._issue_token_pair(
            user_id=user_id,
            email=email,
            roles=resolved_roles,
            ip=ip,
            device=device,
            session_id=uuid4(),
            correlation_id=correlation_id or uuid4(),
        )

    async def create_pending_mfa_challenge(
        self,
        *,
        user_id: UUID,
        email: str,
        ip: str,
        device: str,
        roles: list[dict[str, Any]] | None = None,
    ) -> MfaChallengeResponse:
        resolved_roles = roles if roles is not None else await self._serialize_roles(user_id, None)
        token = await self._create_pending_mfa_token(
            user_id=user_id,
            email=email,
            roles=resolved_roles,
            ip=ip,
            device=device,
            session_id=uuid4(),
        )
        return MfaChallengeResponse(mfa_token=token)

    async def check_permission(
        self,
        user_id: UUID,
        resource_type: str,
        action: str,
        workspace_id: UUID | None,
        *,
        identity_type: str = "user",
        agent_purpose: str | None = None,
        correlation_id: UUID | None = None,
    ) -> PermissionCheckResponse:
        return await rbac_engine.check_permission(
            user_id=user_id,
            resource_type=resource_type,
            action=action,
            workspace_id=workspace_id,
            db=self.repository.db,
            redis_client=self.redis_client,
            producer=self.producer,
            correlation_id=correlation_id,
            identity_type=identity_type,
            agent_purpose=agent_purpose,
        )

    async def create_service_account(
        self,
        name: str,
        role: str,
        workspace_id: UUID | None,
    ) -> ServiceAccountCreateResponse:
        service_account_id = uuid4()
        raw_key = f"msk_{secrets.token_urlsafe(40)}"
        credential = await self.repository.create_service_account_credential(
            sa_id=service_account_id,
            name=name,
            key_hash=hash_password(raw_key),
            role=role,
            workspace_id=workspace_id,
        )
        return ServiceAccountCreateResponse(
            service_account_id=credential.service_account_id,
            name=credential.name,
            api_key=raw_key,
            role=credential.role,
        )

    async def verify_api_key(self, raw_key: str) -> Any | None:
        for credential in await self.repository.get_active_service_accounts():
            if verify_password(raw_key, credential.api_key_hash):
                return credential
        return None

    async def rotate_api_key(self, sa_id: UUID, *, correlation_id: UUID | None = None) -> str:
        credential = await self.repository.get_service_account_by_id(sa_id)
        if credential is None:
            raise NotFoundError("SERVICE_ACCOUNT_NOT_FOUND", "Service account not found")
        raw_key = f"msk_{secrets.token_urlsafe(40)}"
        await self.repository.update_service_account_key_hash(
            sa_id,
            hash_password(raw_key),
            CredentialStatus.ACTIVE.value,
        )
        await publish_auth_event(
            "auth.apikey.rotated",
            ApiKeyRotatedPayload(service_account_id=sa_id),
            correlation_id or uuid4(),
            self.producer,
        )
        return raw_key

    async def revoke_service_account(self, sa_id: UUID) -> None:
        credential = await self.repository.get_service_account_by_id(sa_id)
        if credential is None:
            raise NotFoundError("SERVICE_ACCOUNT_NOT_FOUND", "Service account not found")
        await self.repository.revoke_service_account(sa_id)

    async def create_user_credential(self, user_id: UUID, email: str, password: str) -> None:
        await self.repository.create_credential(user_id, email, hash_password(password))

    async def assign_user_roles(
        self,
        user_id: UUID,
        roles: list[str],
        workspace_ids: list[UUID] | None = None,
    ) -> None:
        if workspace_ids:
            for workspace_id in workspace_ids:
                for role in roles:
                    await self.repository.assign_user_role(user_id, role, workspace_id)
            return
        for role in roles:
            await self.repository.assign_user_role(user_id, role, None)

    async def invalidate_user_sessions(self, user_id: UUID) -> int:
        return await self.session_store.delete_all_sessions(user_id)

    async def reset_mfa(self, user_id: UUID) -> bool:
        return await self.repository.disable_mfa_enrollment(user_id)

    async def initiate_password_reset(
        self,
        user_id: UUID,
        force_change_on_login: bool = True,
    ) -> str:
        del force_change_on_login
        raw_token = secrets.token_urlsafe(32)
        await self.repository.create_password_reset_token(
            user_id,
            raw_token,
            datetime.now(UTC) + timedelta(seconds=self.settings.password_reset_ttl),
        )
        return raw_token

    async def clear_lockout(self, user_id: UUID) -> None:
        await self.lockout.reset_failure_counter(user_id)

    async def _issue_token_pair(
        self,
        *,
        user_id: UUID,
        email: str,
        roles: list[dict[str, Any]],
        ip: str,
        device: str,
        session_id: UUID,
        correlation_id: UUID,
    ) -> TokenPair:
        access_token, refresh_token = create_token_pair(
            user_id=user_id,
            email=email,
            session_id=session_id,
            roles=roles,
            settings=self.settings,
        )
        refresh_claims = decode_token(refresh_token, self.settings)
        await self.session_store.create_session(
            user_id=user_id,
            session_id=session_id,
            email=email,
            roles=roles,
            ip=ip,
            device=device,
            refresh_jti=str(refresh_claims["jti"]),
        )
        await publish_auth_event(
            "auth.user.authenticated",
            UserAuthenticatedPayload(
                user_id=user_id,
                session_id=session_id,
                ip_address=ip,
                device_info=device,
            ),
            correlation_id,
            self.producer,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_ttl,
        )

    async def _serialize_roles(
        self,
        user_id: UUID,
        workspace_id: UUID | None,
    ) -> list[dict[str, Any]]:
        roles = await self.repository.get_user_roles(user_id, workspace_id)
        return [
            {
                "role": role.role,
                "workspace_id": str(role.workspace_id) if role.workspace_id is not None else None,
            }
            for role in roles
        ]

    async def _create_pending_mfa_token(
        self,
        *,
        user_id: UUID,
        email: str,
        roles: list[dict[str, Any]],
        ip: str,
        device: str,
        session_id: UUID,
    ) -> str:
        token = str(uuid4())
        client = await self.redis_client._get_client()
        payload = json.dumps(
            {
                "user_id": str(user_id),
                "email": email,
                "roles": roles,
                "ip": ip,
                "device": device,
                "session_id": str(session_id),
            }
        )
        await client.set(self._pending_mfa_key(token), payload, ex=self.settings.mfa_enrollment_ttl)
        return token

    async def _get_pending_mfa_token(self, token: str) -> dict[str, Any] | None:
        client = await self.redis_client._get_client()
        value = await client.get(self._pending_mfa_key(token))
        if value is None:
            return None
        raw = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            return None
        return loaded

    async def _delete_pending_mfa_token(self, token: str) -> None:
        client = await self.redis_client._get_client()
        await client.delete(self._pending_mfa_key(token))

    @staticmethod
    def _pending_mfa_key(token: str) -> str:
        return f"auth:mfa:{token}"
