from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from platform.accounts.models import SignupSource, UserStatus
from platform.accounts.repository import AccountsRepository
from platform.auth.events import (
    OAuthAccountLinkedPayload,
    OAuthAccountUnlinkedPayload,
    OAuthProviderConfiguredPayload,
    OAuthSignInFailedPayload,
    OAuthSignInSucceededPayload,
    OAuthUserProvisionedPayload,
    publish_auth_event,
)
from platform.auth.exceptions import (
    InactiveUserError,
    OAuthLinkConflictError,
    OAuthProviderDisabledError,
    OAuthProviderNotFoundError,
    OAuthRestrictionError,
    OAuthStateExpiredError,
    OAuthStateInvalidError,
    OAuthUnlinkLastMethodError,
)
from platform.auth.repository import AuthRepository
from platform.auth.repository_oauth import OAuthRepository
from platform.auth.schemas import (
    OAuthAuditEntryListResponse,
    OAuthAuditEntryResponse,
    OAuthAuthorizeResponse,
    OAuthLinkListResponse,
    OAuthLinkResponse,
    OAuthProviderAdminListResponse,
    OAuthProviderAdminResponse,
    OAuthProviderPublic,
    OAuthProviderPublicListResponse,
    OAuthProviderType,
)
from platform.auth.service import AuthService
from platform.auth.services.oauth_providers.github import GitHubOAuthProvider
from platform.auth.services.oauth_providers.google import GoogleOAuthProvider
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.connectors.security import compute_hmac_sha256
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder


@dataclass(slots=True)
class OAuthUserIdentity:
    external_id: str
    email: str
    name: str | None
    avatar_url: str | None
    groups: list[str]


class OAuthService:
    def __init__(
        self,
        *,
        repository: OAuthRepository,
        auth_repository: AuthRepository,
        accounts_repository: AccountsRepository,
        redis_client: AsyncRedisClient,
        settings: PlatformSettings,
        producer: EventProducer | None,
        auth_service: AuthService,
        google_provider: GoogleOAuthProvider | None = None,
        github_provider: GitHubOAuthProvider | None = None,
        credential_resolver: Any | None = None,
    ) -> None:
        self.repository = repository
        self.auth_repository = auth_repository
        self.accounts_repository = accounts_repository
        self.redis_client = redis_client
        self.settings = settings
        self.producer = producer
        self.auth_service = auth_service
        self.google_provider = google_provider or GoogleOAuthProvider()
        self.github_provider = github_provider or GitHubOAuthProvider()
        self.credential_resolver = credential_resolver

    async def list_public_providers(self) -> OAuthProviderPublicListResponse:
        providers = [
            OAuthProviderPublic(
                provider_type=OAuthProviderType(provider.provider_type),
                display_name=provider.display_name,
            )
            for provider in await self.repository.get_all_providers()
            if provider.enabled
        ]
        return OAuthProviderPublicListResponse(providers=providers)

    async def list_admin_providers(self) -> OAuthProviderAdminListResponse:
        providers = await self.repository.get_all_providers()
        return OAuthProviderAdminListResponse(
            providers=[self._serialize_admin_provider(item) for item in providers]
        )

    async def list_links(self, user_id: UUID) -> OAuthLinkListResponse:
        links = await self.repository.get_links_for_user(user_id)
        return OAuthLinkListResponse(items=[self._serialize_link(item) for item in links])

    async def list_audit_entries(
        self,
        *,
        provider_type: str | None = None,
        user_id: UUID | None = None,
        outcome: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> OAuthAuditEntryListResponse:
        entries = await self.repository.list_audit_entries(
            provider_type=provider_type,
            user_id=user_id,
            outcome=outcome,
            start_time=datetime.fromisoformat(start_time) if start_time else None,
            end_time=datetime.fromisoformat(end_time) if end_time else None,
            limit=limit,
        )
        return OAuthAuditEntryListResponse(
            items=[self._serialize_audit_entry(item) for item in entries]
        )

    async def upsert_provider(
        self,
        *,
        provider_type: str,
        actor_id: UUID,
        display_name: str,
        enabled: bool,
        client_id: str,
        client_secret_ref: str,
        redirect_uri: str,
        scopes: list[str],
        domain_restrictions: list[str],
        org_restrictions: list[str],
        group_role_mapping: dict[str, str],
        default_role: str,
        require_mfa: bool,
    ) -> tuple[OAuthProviderAdminResponse, bool]:
        self._validate_role(default_role)
        for role in group_role_mapping.values():
            self._validate_role(role)

        existing = await self.repository.get_provider_by_type(provider_type)
        before = self._provider_snapshot(existing)
        provider, created = await self.repository.upsert_provider(
            provider_type,
            display_name=display_name,
            enabled=enabled,
            client_id=client_id,
            client_secret_ref=client_secret_ref,
            redirect_uri=redirect_uri,
            scopes=scopes,
            domain_restrictions=domain_restrictions,
            org_restrictions=org_restrictions,
            group_role_mapping=group_role_mapping,
            default_role=default_role,
            require_mfa=require_mfa,
        )
        changed_fields = self._diff_provider(before, self._provider_snapshot(provider))
        await self.repository.create_audit_entry(
            provider_type=provider.provider_type,
            provider_id=provider.id,
            user_id=None,
            external_id=None,
            action="provider_configured",
            outcome="success",
            failure_reason=None,
            source_ip=None,
            user_agent=None,
            actor_id=actor_id,
            changed_fields=changed_fields,
        )
        await publish_auth_event(
            "auth.oauth.provider_configured",
            OAuthProviderConfiguredPayload(
                actor_id=actor_id,
                provider_type=provider.provider_type,
                enabled=provider.enabled,
            ),
            uuid4(),
            self.producer,
        )
        return self._serialize_admin_provider(provider), created

    async def get_authorization_url(
        self,
        provider_type: str,
        *,
        link_for_user_id: UUID | None = None,
    ) -> OAuthAuthorizeResponse:
        provider = await self._require_enabled_provider(provider_type)
        nonce = secrets.token_urlsafe(24)
        code_verifier = self._build_code_verifier()
        payload = {
            "provider_type": provider.provider_type,
            "code_verifier": code_verifier,
            "created_at": datetime.now(UTC).isoformat(),
            "link_for_user_id": str(link_for_user_id) if link_for_user_id else None,
        }
        await self.redis_client.set(
            self._state_key(nonce),
            json.dumps(payload).encode("utf-8"),
            ttl=self.settings.auth.oauth_state_ttl,
        )
        state = self._sign_state(nonce)
        redirect_url = self._provider_client(provider.provider_type).get_auth_url(
            client_id=provider.client_id,
            redirect_uri=provider.redirect_uri,
            scopes=list(provider.scopes),
            state=state,
            code_challenge=self._build_code_challenge(code_verifier),
        )
        return OAuthAuthorizeResponse(redirect_url=redirect_url)

    async def handle_callback(
        self,
        *,
        provider_type: str,
        code: str,
        raw_state: str,
        source_ip: str,
        user_agent: str,
    ) -> dict[str, Any]:
        provider = await self._require_provider(provider_type)
        try:
            state_payload = await self._consume_state(raw_state, provider.provider_type)
        except (OAuthStateInvalidError, OAuthStateExpiredError) as exc:
            await self.repository.create_audit_entry(
                provider_type=provider.provider_type,
                provider_id=provider.id,
                user_id=None,
                external_id=None,
                action="sign_in_failed",
                outcome="failure",
                failure_reason=exc.code,
                source_ip=source_ip,
                user_agent=user_agent,
                actor_id=None,
                changed_fields=None,
            )
            raise
        if not provider.enabled:
            await self.repository.create_audit_entry(
                provider_type=provider.provider_type,
                provider_id=provider.id,
                user_id=None,
                external_id=None,
                action="sign_in_failed",
                outcome="failure",
                failure_reason="OAUTH_PROVIDER_DISABLED",
                source_ip=source_ip,
                user_agent=user_agent,
                actor_id=None,
                changed_fields=None,
            )
            raise OAuthProviderDisabledError(provider_type)
        try:
            identity = await self._resolve_identity(
                provider, code, str(state_payload["code_verifier"])
            )
        except Exception as exc:
            await self.repository.create_audit_entry(
                provider_type=provider.provider_type,
                provider_id=provider.id,
                user_id=None,
                external_id=None,
                action="sign_in_failed",
                outcome="failure",
                failure_reason=getattr(exc, "code", None) or str(exc),
                source_ip=source_ip,
                user_agent=user_agent,
                actor_id=None,
                changed_fields=None,
            )
            raise
        link_for_user_id = self._parse_optional_uuid(state_payload.get("link_for_user_id"))

        if link_for_user_id is not None:
            try:
                link = await self._link_identity(
                    user_id=link_for_user_id,
                    provider=provider,
                    identity=identity,
                    source_ip=source_ip,
                    user_agent=user_agent,
                )
            except OAuthLinkConflictError as exc:
                await self.repository.create_audit_entry(
                    provider_type=provider.provider_type,
                    provider_id=provider.id,
                    user_id=link_for_user_id,
                    external_id=identity.external_id,
                    action="account_linked",
                    outcome="failure",
                    failure_reason=exc.code,
                    source_ip=source_ip,
                    user_agent=user_agent,
                    actor_id=link_for_user_id,
                    changed_fields=None,
                )
                raise
            return {"link": link, "linked": True}

        try:
            self._enforce_restrictions(provider, identity)
        except OAuthRestrictionError as exc:
            await self._write_failed_sign_in(provider, identity, exc, source_ip, user_agent)
            raise

        existing_link = await self.repository.get_link_by_external(
            provider.id,
            identity.external_id,
        )
        if existing_link is not None:
            user_id = existing_link.user_id
            await self.repository.update_link(
                existing_link,
                external_email=identity.email,
                external_name=identity.name,
                external_avatar_url=identity.avatar_url,
                external_groups=identity.groups,
                last_login_at=datetime.now(UTC),
            )
        else:
            platform_user = await self.auth_repository.get_platform_user_by_email(identity.email)
            if platform_user is not None:
                conflict = OAuthLinkConflictError(
                    "Existing account with this email must sign in locally "
                    "and link the provider first"
                )
                await self._write_failed_sign_in(
                    provider,
                    identity,
                    conflict,
                    source_ip,
                    user_agent,
                )
                raise conflict
            user_id = await self._auto_provision_user(provider, identity)
            await self.repository.create_audit_entry(
                provider_type=provider.provider_type,
                provider_id=provider.id,
                user_id=user_id,
                external_id=identity.external_id,
                action="user_provisioned",
                outcome="success",
                failure_reason=None,
                source_ip=source_ip,
                user_agent=user_agent,
                actor_id=user_id,
                changed_fields=None,
            )
            await publish_auth_event(
                "auth.oauth.user_provisioned",
                OAuthUserProvisionedPayload(
                    user_id=user_id,
                    provider_type=provider.provider_type,
                    external_id=identity.external_id,
                    email=identity.email,
                ),
                uuid4(),
                self.producer,
            )
            await self.repository.create_link(
                user_id=user_id,
                provider_id=provider.id,
                external_id=identity.external_id,
                external_email=identity.email,
                external_name=identity.name,
                external_avatar_url=identity.avatar_url,
                external_groups=identity.groups,
                last_login_at=datetime.now(UTC),
            )

        platform_user = await self.auth_repository.get_platform_user(user_id)
        if platform_user is None or platform_user.status != "active":
            error = InactiveUserError()
            await self.repository.create_audit_entry(
                provider_type=provider.provider_type,
                provider_id=provider.id,
                user_id=user_id,
                external_id=identity.external_id,
                action="sign_in_failed",
                outcome="failure",
                failure_reason=error.code,
                source_ip=source_ip,
                user_agent=user_agent,
                actor_id=user_id,
                changed_fields=None,
            )
            raise error

        user_payload = await self._build_user_payload(
            user_id=user_id,
            platform_user=platform_user,
            identity=identity,
        )
        if provider.require_mfa and user_payload["mfa_enrolled"]:
            challenge = await self.auth_service.create_pending_mfa_challenge(
                user_id=user_id,
                email=platform_user.email,
                ip=source_ip,
                device=user_agent,
            )
            await self.repository.create_audit_entry(
                provider_type=provider.provider_type,
                provider_id=provider.id,
                user_id=user_id,
                external_id=identity.external_id,
                action="mfa_challenge_required",
                outcome="success",
                failure_reason=None,
                source_ip=source_ip,
                user_agent=user_agent,
                actor_id=user_id,
                changed_fields=None,
            )
            return {
                "mfa_required": True,
                "session_token": challenge.mfa_token,
                "user": user_payload,
            }

        token_pair = await self.auth_service.create_session(
            user_id=user_id,
            email=platform_user.email,
            ip=source_ip,
            device=user_agent,
        )
        await self.repository.create_audit_entry(
            provider_type=provider.provider_type,
            provider_id=provider.id,
            user_id=user_id,
            external_id=identity.external_id,
            action="sign_in_succeeded",
            outcome="success",
            failure_reason=None,
            source_ip=source_ip,
            user_agent=user_agent,
            actor_id=user_id,
            changed_fields=None,
        )
        await publish_auth_event(
            "auth.oauth.sign_in_succeeded",
            OAuthSignInSucceededPayload(
                user_id=user_id,
                provider_type=provider.provider_type,
                external_id=identity.external_id,
            ),
            uuid4(),
            self.producer,
        )
        return {
            "token_pair": token_pair,
            "user": user_payload,
        }

    async def unlink_account(self, user_id: UUID, provider_type: str) -> None:
        provider = await self.repository.get_provider_by_type(provider_type)
        if provider is None:
            raise OAuthProviderNotFoundError(provider_type)
        link = await self.repository.get_link_for_user_provider(user_id, provider.id)
        if link is None:
            raise OAuthProviderNotFoundError(provider_type)
        if await self.repository.count_auth_methods(user_id) <= 1:
            raise OAuthUnlinkLastMethodError()
        await self.repository.delete_link(link)
        await self.repository.create_audit_entry(
            provider_type=provider.provider_type,
            provider_id=provider.id,
            user_id=user_id,
            external_id=link.external_id,
            action="account_unlinked",
            outcome="success",
            failure_reason=None,
            source_ip=None,
            user_agent=None,
            actor_id=user_id,
            changed_fields=None,
        )
        await publish_auth_event(
            "auth.oauth.account_unlinked",
            OAuthAccountUnlinkedPayload(
                user_id=user_id,
                provider_type=provider.provider_type,
            ),
            uuid4(),
            self.producer,
        )

    async def _link_identity(
        self,
        *,
        user_id: UUID,
        provider: Any,
        identity: OAuthUserIdentity,
        source_ip: str,
        user_agent: str,
    ) -> OAuthLinkResponse:
        existing_link = await self.repository.get_link_by_external(
            provider.id,
            identity.external_id,
        )
        if existing_link is not None and existing_link.user_id != user_id:
            raise OAuthLinkConflictError()
        user_link = await self.repository.get_link_for_user_provider(user_id, provider.id)
        if user_link is not None:
            raise OAuthLinkConflictError("OAuth provider is already linked to this account")
        link = await self.repository.create_link(
            user_id=user_id,
            provider_id=provider.id,
            external_id=identity.external_id,
            external_email=identity.email,
            external_name=identity.name,
            external_avatar_url=identity.avatar_url,
            external_groups=identity.groups,
            last_login_at=datetime.now(UTC),
        )
        link.provider = provider
        await self.repository.create_audit_entry(
            provider_type=provider.provider_type,
            provider_id=provider.id,
            user_id=user_id,
            external_id=identity.external_id,
            action="account_linked",
            outcome="success",
            failure_reason=None,
            source_ip=source_ip,
            user_agent=user_agent,
            actor_id=user_id,
            changed_fields=None,
        )
        await publish_auth_event(
            "auth.oauth.account_linked",
            OAuthAccountLinkedPayload(
                user_id=user_id,
                provider_type=provider.provider_type,
                external_id=identity.external_id,
            ),
            uuid4(),
            self.producer,
        )
        return self._serialize_link(link)

    async def _auto_provision_user(self, provider: Any, identity: OAuthUserIdentity) -> UUID:
        role = self._resolve_role(provider, identity.groups)
        user = await self.accounts_repository.create_user(
            email=identity.email,
            display_name=identity.name or identity.email.split("@", 1)[0],
            status=UserStatus.active,
            signup_source=SignupSource.self_registration,
        )
        now = datetime.now(UTC)
        await self.accounts_repository.update_user_status(
            user.id,
            UserStatus.active,
            email_verified_at=now,
            activated_at=now,
        )
        await self.auth_repository.assign_user_role(user.id, role, None)
        return user.id

    async def _resolve_identity(
        self,
        provider: Any,
        code: str,
        code_verifier: str,
    ) -> OAuthUserIdentity:
        client_secret = await self._resolve_secret(provider.client_secret_ref)
        client = self._provider_client(provider.provider_type)
        token_payload = await client.exchange_code(
            client_id=provider.client_id,
            client_secret=client_secret,
            redirect_uri=provider.redirect_uri,
            code=code,
            code_verifier=code_verifier,
        )
        if provider.provider_type == OAuthProviderType.GOOGLE.value:
            user_payload = await client.fetch_user(
                id_token=str(token_payload.get("id_token") or ""),
                client_id=provider.client_id,
            )
            groups = await client.fetch_groups(
                access_token=str(token_payload.get("access_token") or "")
            )
            return OAuthUserIdentity(
                external_id=str(user_payload.get("sub") or user_payload.get("user_id") or ""),
                email=str(user_payload.get("email") or "").lower(),
                name=str(user_payload.get("name") or "") or None,
                avatar_url=str(user_payload.get("picture") or "") or None,
                groups=list(groups),
            )
        access_token = str(token_payload.get("access_token") or "")
        user_payload = await client.fetch_user(access_token=access_token)
        email = await client.fetch_emails(access_token=access_token)
        allowed_orgs = list(provider.org_restrictions)
        groups = await client.fetch_teams(
            access_token=access_token,
            orgs=allowed_orgs,
        )
        org_markers = [
            f"org:{org}"
            for org in allowed_orgs
            if await client.check_org_membership(access_token=access_token, org=org)
        ]
        return OAuthUserIdentity(
            external_id=str(user_payload.get("id") or ""),
            email=email.lower(),
            name=str(user_payload.get("name") or user_payload.get("login") or "") or None,
            avatar_url=str(user_payload.get("avatar_url") or "") or None,
            groups=[*org_markers, *list(groups)],
        )

    def _enforce_restrictions(self, provider: Any, identity: OAuthUserIdentity) -> None:
        if (
            provider.provider_type == OAuthProviderType.GOOGLE.value
            and provider.domain_restrictions
        ):
            domain = identity.email.split("@", 1)[1] if "@" in identity.email else ""
            if domain not in set(provider.domain_restrictions):
                raise OAuthRestrictionError("DOMAIN_NOT_ALLOWED", "Email domain is not allowed")
        if provider.provider_type == OAuthProviderType.GITHUB.value and provider.org_restrictions:
            org_memberships = {group for group in identity.groups if group.startswith("org:")}
            allowed = {f"org:{org}" for org in provider.org_restrictions}
            if not allowed.intersection(org_memberships):
                raise OAuthRestrictionError("ORG_NOT_ALLOWED", "GitHub organization is not allowed")

    async def _write_failed_sign_in(
        self,
        provider: Any,
        identity: OAuthUserIdentity,
        error: Exception,
        source_ip: str,
        user_agent: str,
    ) -> None:
        failure_reason = getattr(error, "code", None) or str(error)
        await self.repository.create_audit_entry(
            provider_type=provider.provider_type,
            provider_id=provider.id,
            user_id=None,
            external_id=identity.external_id,
            action="sign_in_failed",
            outcome="failure",
            failure_reason=failure_reason,
            source_ip=source_ip,
            user_agent=user_agent,
            actor_id=None,
            changed_fields=None,
        )
        await publish_auth_event(
            "auth.oauth.sign_in_failed",
            OAuthSignInFailedPayload(
                provider_type=provider.provider_type,
                failure_reason=failure_reason,
                external_id=identity.external_id,
            ),
            uuid4(),
            self.producer,
        )

    async def _require_provider(self, provider_type: str) -> Any:
        provider = await self.repository.get_provider_by_type(provider_type)
        if provider is None:
            raise OAuthProviderNotFoundError(provider_type)
        return provider

    async def _require_enabled_provider(self, provider_type: str) -> Any:
        provider = await self._require_provider(provider_type)
        if not provider.enabled:
            raise OAuthProviderDisabledError(provider_type)
        return provider

    async def _consume_state(self, raw_state: str, provider_type: str) -> dict[str, Any]:
        nonce = self._verify_state(raw_state)
        raw_payload = await self.redis_client.get(self._state_key(nonce))
        if raw_payload is None:
            raise OAuthStateExpiredError()
        await self.redis_client.delete(self._state_key(nonce))
        payload = json.loads(
            raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else str(raw_payload)
        )
        if str(payload.get("provider_type")) != provider_type:
            raise OAuthStateInvalidError()
        return cast(dict[str, Any], jsonable_encoder(payload))

    async def _resolve_secret(self, reference: str) -> str:
        if self.credential_resolver is not None:
            result = self.credential_resolver(reference)
            if hasattr(result, "__await__"):
                result = await result
            if isinstance(result, str) and result:
                return result
        if reference.startswith("plain:"):
            return reference.split(":", 1)[1]
        import os

        env_key = "OAUTH_SECRET_" + "".join(ch if ch.isalnum() else "_" for ch in reference).upper()
        value = os.getenv(env_key)
        if value:
            return value
        return reference

    def _resolve_role(self, provider: Any, groups: list[str]) -> str:
        for group in groups:
            role = provider.group_role_mapping.get(group)
            if role:
                return str(role)
        return str(provider.default_role)

    @staticmethod
    def _validate_role(role: str) -> None:
        if not role or not role.strip():
            raise ValueError("OAuth role mapping cannot be blank")

    def _provider_client(self, provider_type: str) -> Any:
        if provider_type == OAuthProviderType.GOOGLE.value:
            return self.google_provider
        if provider_type == OAuthProviderType.GITHUB.value:
            return self.github_provider
        raise OAuthProviderNotFoundError(provider_type)

    def _sign_state(self, nonce: str) -> str:
        signature = compute_hmac_sha256(
            self.settings.auth.oauth_state_secret,
            nonce.encode("utf-8"),
        )
        return f"{nonce}.{signature}"

    def _verify_state(self, raw_state: str) -> str:
        try:
            nonce, provided = raw_state.split(".", 1)
        except ValueError as exc:
            raise OAuthStateInvalidError() from exc
        expected = compute_hmac_sha256(
            self.settings.auth.oauth_state_secret,
            nonce.encode("utf-8"),
        )
        if not hmac.compare_digest(expected, provided):
            raise OAuthStateInvalidError()
        return nonce

    @staticmethod
    def _build_code_verifier() -> str:
        return base64.urlsafe_b64encode(secrets.token_bytes(72)).rstrip(b"=").decode("utf-8")

    @staticmethod
    def _build_code_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")

    @staticmethod
    def _state_key(nonce: str) -> str:
        return f"oauth:state:{nonce}"

    @staticmethod
    def _parse_optional_uuid(value: Any) -> UUID | None:
        if not value:
            return None
        return UUID(str(value))

    @staticmethod
    def _provider_snapshot(provider: Any | None) -> dict[str, Any] | None:
        if provider is None:
            return None
        return {
            "display_name": provider.display_name,
            "enabled": provider.enabled,
            "client_id": provider.client_id,
            "client_secret_ref": provider.client_secret_ref,
            "redirect_uri": provider.redirect_uri,
            "scopes": list(provider.scopes),
            "domain_restrictions": list(provider.domain_restrictions),
            "org_restrictions": list(provider.org_restrictions),
            "group_role_mapping": dict(provider.group_role_mapping),
            "default_role": provider.default_role,
            "require_mfa": provider.require_mfa,
        }

    @staticmethod
    def _diff_provider(
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if before is None:
            return {"created": True, **(after or {})}
        changed: dict[str, Any] = {}
        for key, value in (after or {}).items():
            if before.get(key) != value:
                changed[key] = {"before": before.get(key), "after": value}
        return changed

    @staticmethod
    def _serialize_admin_provider(provider: Any) -> OAuthProviderAdminResponse:
        return OAuthProviderAdminResponse(
            id=provider.id,
            provider_type=OAuthProviderType(provider.provider_type),
            display_name=provider.display_name,
            enabled=provider.enabled,
            client_id=provider.client_id,
            client_secret_ref=provider.client_secret_ref,
            redirect_uri=provider.redirect_uri,
            scopes=list(provider.scopes),
            domain_restrictions=list(provider.domain_restrictions),
            org_restrictions=list(provider.org_restrictions),
            group_role_mapping=dict(provider.group_role_mapping),
            default_role=provider.default_role,
            require_mfa=provider.require_mfa,
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )

    @staticmethod
    def _serialize_audit_entry(entry: Any) -> OAuthAuditEntryResponse:
        return OAuthAuditEntryResponse(
            id=entry.id,
            provider_type=(OAuthProviderType(entry.provider_type) if entry.provider_type else None),
            user_id=entry.user_id,
            external_id=entry.external_id,
            action=entry.action,
            outcome=entry.outcome,
            failure_reason=entry.failure_reason,
            source_ip=entry.source_ip,
            user_agent=entry.user_agent,
            actor_id=entry.actor_id,
            changed_fields=dict(entry.changed_fields or {}),
            created_at=entry.created_at,
        )

    async def _build_user_payload(
        self,
        *,
        user_id: UUID,
        platform_user: Any,
        identity: OAuthUserIdentity,
    ) -> dict[str, Any]:
        roles = await self.auth_repository.get_user_roles(user_id, None)
        enrollment = await self.auth_repository.get_mfa_enrollment(user_id)
        return {
            "id": str(user_id),
            "email": platform_user.email,
            "display_name": platform_user.display_name or identity.email.split("@", 1)[0],
            "avatar_url": identity.avatar_url,
            "roles": [role.role for role in roles],
            "workspace_id": None,
            "mfa_enrolled": bool(
                enrollment is not None and getattr(enrollment, "status", "") == "active"
            ),
        }

    @staticmethod
    def _serialize_link(link: Any) -> OAuthLinkResponse:
        provider = link.provider
        return OAuthLinkResponse(
            provider_type=OAuthProviderType(provider.provider_type),
            display_name=provider.display_name,
            linked_at=link.linked_at,
            last_login_at=link.last_login_at,
            external_email=link.external_email,
            external_name=link.external_name,
            external_avatar_url=link.external_avatar_url,
        )
