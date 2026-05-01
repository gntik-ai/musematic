from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from platform.accounts.models import SignupSource, UserStatus
from platform.accounts.repository import AccountsRepository
from platform.auth.events import (
    OAuthAccountLinkedPayload,
    OAuthAccountUnlinkedPayload,
    OAuthConfigImportedPayload,
    OAuthProviderConfiguredPayload,
    OAuthRateLimitUpdatedPayload,
    OAuthSecretRotatedPayload,
    OAuthSignInFailedPayload,
    OAuthSignInSucceededPayload,
    OAuthUserProvisionedPayload,
    publish_auth_event,
)
from platform.auth.exceptions import (
    InactiveUserError,
    OAuthBootstrapEnvironmentError,
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
    OAuthConfigReseedResponse,
    OAuthHistoryEntryResponse,
    OAuthHistoryListResponse,
    OAuthLinkListResponse,
    OAuthLinkResponse,
    OAuthProviderAdminListResponse,
    OAuthProviderAdminResponse,
    OAuthProviderPublic,
    OAuthProviderPublicListResponse,
    OAuthProviderSourceType,
    OAuthProviderStatusResponse,
    OAuthProviderType,
    OAuthRateLimitConfig,
)
from platform.auth.service import AuthService
from platform.auth.services.oauth_bootstrap import bootstrap_oauth_provider_from_env
from platform.auth.services.oauth_providers.github import GitHubOAuthProvider
from platform.auth.services.oauth_providers.google import GoogleOAuthProvider
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import _VALID_OAUTH_BOOTSTRAP_ROLES, PlatformSettings
from platform.common.events.producer import EventProducer
from platform.common.exceptions import ValidationError
from platform.common.secret_provider import (
    CredentialPolicyDeniedError,
    CredentialUnavailableError,
    SecretProvider,
)
from platform.common.tenant_context import current_tenant
from platform.connectors.security import compute_hmac_sha256
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder

_PLAINTEXT_SECRET_PREFIX = "plain:"
_REDACTED_PLAINTEXT_SECRET_REF = "plain:<redacted>"
_LOOPBACK_REDIRECT_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_loopback_redirect_uri(uri: str) -> bool:
    try:
        host = urlsplit(uri).hostname
    except ValueError:
        return False
    return host in _LOOPBACK_REDIRECT_HOSTS


@dataclass(slots=True)
class OAuthUserIdentity:
    external_id: str
    email: str
    name: str | None
    locale: str | None
    timezone: str | None
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
        secret_provider: SecretProvider | None = None,
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
        self.secret_provider = secret_provider

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

    async def list_links_for_email(self, email: str) -> OAuthLinkListResponse:
        platform_user = await self.auth_repository.get_platform_user_by_email(email.strip().lower())
        if platform_user is None:
            return OAuthLinkListResponse(items=[])
        return await self.list_links(platform_user.id)

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
        source: OAuthProviderSourceType | str = OAuthProviderSourceType.MANUAL,
    ) -> tuple[OAuthProviderAdminResponse, bool]:
        self._validate_role(default_role)
        for role in group_role_mapping.values():
            self._validate_role(role)

        source_value = source.value if isinstance(source, OAuthProviderSourceType) else str(source)
        existing = await self.repository.get_provider_by_type(provider_type)
        before = self._provider_snapshot(existing)
        last_edited_by = await self._resolved_existing_actor_id(actor_id)
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
            source=source_value,
            last_edited_by=last_edited_by,
            last_edited_at=datetime.now(UTC),
        )
        changed_fields = self._diff_provider(before, self._provider_snapshot(provider))
        audit_action = "config_imported" if source_value == "imported" else "provider_configured"
        await self.repository.create_audit_entry(
            provider_type=provider.provider_type,
            provider_id=provider.id,
            user_id=None,
            external_id=None,
            action=audit_action,
            outcome="success",
            failure_reason=None,
            source_ip=None,
            user_agent=None,
            actor_id=actor_id,
            changed_fields=changed_fields,
        )
        if source_value == "imported":
            await publish_auth_event(
                "auth.oauth.config_imported",
                OAuthConfigImportedPayload(
                    actor_id=actor_id,
                    provider_type=provider.provider_type,
                    vault_path=provider.client_secret_ref,
                ),
                uuid4(),
                self.producer,
            )
            return self._serialize_admin_provider(provider), created

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

    async def _resolved_existing_actor_id(self, actor_id: UUID) -> UUID | None:
        if await self.auth_repository.get_platform_user(actor_id) is None:
            return None
        return actor_id

    async def rotate_secret(self, provider_type: str, new_secret: str, actor_id: UUID) -> None:
        provider = await self._require_provider(provider_type)
        versions_before = await self._list_secret_versions(provider.client_secret_ref)
        await self._put_secret(provider.client_secret_ref, new_secret)
        await self._flush_secret_cache(provider.client_secret_ref)
        versions_after = await self._list_secret_versions(provider.client_secret_ref)
        old_version = max(versions_before) if versions_before else None
        new_version = max(versions_after) if versions_after else None
        await self.repository.create_audit_entry(
            provider_type=provider.provider_type,
            provider_id=provider.id,
            user_id=None,
            external_id=None,
            action="secret_rotated",
            outcome="success",
            failure_reason=None,
            source_ip=None,
            user_agent=None,
            actor_id=actor_id,
            changed_fields={"changed_fields": ["client_secret"]},
        )
        await publish_auth_event(
            "auth.oauth.secret_rotated",
            OAuthSecretRotatedPayload(
                actor_id=actor_id,
                provider_type=provider.provider_type,
                old_version=old_version,
                new_version=new_version,
            ),
            uuid4(),
            self.producer,
        )

    async def reseed_from_env(
        self,
        provider_type: str,
        *,
        force_update: bool,
        actor_id: UUID,
        settings: PlatformSettings,
        secret_provider: SecretProvider,
    ) -> OAuthConfigReseedResponse:
        if provider_type == "google" and not settings.oauth_bootstrap.google.enabled:
            raise OAuthBootstrapEnvironmentError(provider_type)
        if provider_type == "github" and not settings.oauth_bootstrap.github.enabled:
            raise OAuthBootstrapEnvironmentError(provider_type)
        if provider_type not in {"google", "github"}:
            raise OAuthProviderNotFoundError(provider_type)
        result = await bootstrap_oauth_provider_from_env(
            repository=self.repository,
            settings=settings,
            secret_provider=secret_provider,
            producer=self.producer,
            provider_type=cast(Any, provider_type),
            actor_id=actor_id,
            force_update_override=force_update,
        )
        return OAuthConfigReseedResponse(
            diff={
                "status": result.status,
                "changed_fields": result.changed_fields,
                "audit_event_id": str(result.audit_event_id) if result.audit_event_id else None,
            }
        )

    async def get_history(
        self,
        provider_type: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> OAuthHistoryListResponse:
        provider = await self._require_provider(provider_type)
        parsed_cursor = datetime.fromisoformat(cursor) if cursor else None
        entries = await self.repository.get_history(
            provider.id,
            limit=limit,
            cursor=parsed_cursor,
        )
        next_cursor = entries[-1].created_at.isoformat() if len(entries) == limit else None
        return OAuthHistoryListResponse(
            entries=[self._serialize_history_entry(item) for item in entries],
            next_cursor=next_cursor,
        )

    async def get_rate_limits(self, provider_type: str) -> OAuthRateLimitConfig:
        provider = await self._require_provider(provider_type)
        limits = await self.repository.get_rate_limits(provider.id)
        if limits is None:
            return self._default_rate_limits()
        return self._serialize_rate_limits(limits)

    async def update_rate_limits(
        self,
        provider_type: str,
        config: OAuthRateLimitConfig,
        actor_id: UUID,
    ) -> OAuthRateLimitConfig:
        provider = await self._require_provider(provider_type)
        before_row = await self.repository.get_rate_limits(provider.id)
        before = (
            self._serialize_rate_limits(before_row).model_dump()
            if before_row is not None
            else self._default_rate_limits().model_dump()
        )
        limits = await self.repository.upsert_rate_limits(provider.id, **config.model_dump())
        after = self._serialize_rate_limits(limits)
        await self.repository.create_audit_entry(
            provider_type=provider.provider_type,
            provider_id=provider.id,
            user_id=None,
            external_id=None,
            action="rate_limit_updated",
            outcome="success",
            failure_reason=None,
            source_ip=None,
            user_agent=None,
            actor_id=actor_id,
            changed_fields={"before": before, "after": after.model_dump()},
        )
        await publish_auth_event(
            "auth.oauth.rate_limit_updated",
            OAuthRateLimitUpdatedPayload(
                actor_id=actor_id,
                provider_type=provider.provider_type,
                before=before,
                after=after.model_dump(),
            ),
            uuid4(),
            self.producer,
        )
        return after

    async def get_status(self, provider_type: str) -> OAuthProviderStatusResponse:
        provider = await self._require_provider(provider_type)
        now = datetime.now(UTC)
        auth_count_24h = await self.repository.count_successful_auths_since(
            provider.id,
            now - timedelta(hours=24),
        )
        auth_count_7d = await self.repository.count_successful_auths_since(
            provider.id,
            now - timedelta(days=7),
        )
        auth_count_30d = await self.repository.count_successful_auths_since(
            provider.id,
            now - timedelta(days=30),
        )
        return OAuthProviderStatusResponse(
            provider_type=OAuthProviderType(provider.provider_type),
            source=OAuthProviderSourceType(self._source_value(getattr(provider, "source", None))),
            last_successful_auth_at=getattr(provider, "last_successful_auth_at", None),
            auth_count_24h=auth_count_24h,
            auth_count_7d=auth_count_7d,
            auth_count_30d=auth_count_30d,
            active_linked_users=await self.repository.count_active_links(provider.id),
        )

    async def get_authorization_url(
        self,
        provider_type: str,
        *,
        link_for_user_id: UUID | None = None,
        dry_run: bool = False,
        intent: str | None = None,
        recovery_email: str | None = None,
    ) -> OAuthAuthorizeResponse:
        provider = await self._require_enabled_provider(provider_type)
        if intent not in {None, "recovery"}:
            raise ValidationError("OAUTH_INTENT_INVALID", "Unsupported OAuth authorization intent")
        if intent == "recovery" and not recovery_email:
            raise ValidationError("OAUTH_RECOVERY_EMAIL_REQUIRED", "Recovery email is required")
        if intent == "recovery" and link_for_user_id is not None:
            raise ValidationError(
                "OAUTH_INTENT_CONFLICT",
                "OAuth recovery cannot be combined with account linking",
            )
        nonce = secrets.token_urlsafe(24)
        code_verifier = self._build_code_verifier()
        payload = {
            "provider_type": provider.provider_type,
            "code_verifier": code_verifier,
            "created_at": datetime.now(UTC).isoformat(),
            "link_for_user_id": str(link_for_user_id) if link_for_user_id else None,
            "intent": intent,
            "recovery_email": recovery_email.strip().lower() if recovery_email else None,
            "tenant_id": str(provider.tenant_id),
            "redirect_uri": self._tenant_callback_url(
                provider.provider_type, provider.redirect_uri
            ),
        }
        if not dry_run:
            await self.redis_client.set(
                self._state_key(nonce),
                json.dumps(payload).encode("utf-8"),
                ttl=self.settings.auth.oauth_state_ttl,
            )
        state = self._sign_state(nonce)
        redirect_url = self._provider_client(provider.provider_type).get_auth_url(
            client_id=provider.client_id,
            redirect_uri=str(payload["redirect_uri"]),
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
                provider,
                code,
                str(state_payload["code_verifier"]),
                redirect_uri=str(state_payload.get("redirect_uri") or provider.redirect_uri),
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
        recovery_intent = state_payload.get("intent") == "recovery"

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
        if recovery_intent and existing_link is None:
            conflict = OAuthLinkConflictError(
                "OAuth recovery is only available for already linked providers"
            )
            await self._write_failed_sign_in(
                provider,
                identity,
                conflict,
                source_ip,
                user_agent,
            )
            raise conflict
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
        recovery_email = str(state_payload.get("recovery_email") or "").strip().lower()
        if (
            recovery_intent
            and platform_user is not None
            and platform_user.email.lower() != recovery_email
        ):
            conflict = OAuthLinkConflictError(
                "Linked provider does not match the requested recovery account"
            )
            await self._write_failed_sign_in(
                provider,
                identity,
                conflict,
                source_ip,
                user_agent,
            )
            raise conflict
        allowed_statuses = {
            UserStatus.active.value,
            UserStatus.pending_approval.value,
            UserStatus.pending_profile_completion.value,
        }
        if platform_user is None or platform_user.status not in allowed_statuses:
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
        success_at = datetime.now(UTC)
        await self.repository.update_provider_last_successful_auth(provider, success_at)
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
        if recovery_intent:
            await self.repository.create_audit_entry(
                provider_type=provider.provider_type,
                provider_id=provider.id,
                user_id=user_id,
                external_id=identity.external_id,
                action="password_reset_via_oauth_recovery",
                outcome="success",
                failure_reason=None,
                source_ip=source_ip,
                user_agent=user_agent,
                actor_id=user_id,
                changed_fields={
                    "recovery_email": state_payload.get("recovery_email"),
                    "provider_type": provider.provider_type,
                },
            )
        return {
            "token_pair": token_pair,
            "user": user_payload,
            "recovery_intent": recovery_intent,
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
        status = self._initial_user_status(identity)
        user = await self.accounts_repository.create_user(
            email=identity.email,
            display_name=identity.name or identity.email.split("@", 1)[0],
            status=status,
            signup_source=SignupSource.self_registration,
        )
        now = datetime.now(UTC)
        status_fields: dict[str, object] = {"email_verified_at": now}
        if status == UserStatus.active:
            status_fields["activated_at"] = now
        await self.accounts_repository.update_user_status(user.id, status, **status_fields)
        if status == UserStatus.pending_approval:
            await self.accounts_repository.create_approval_request(user.id, now)
        await self.auth_repository.assign_user_role(user.id, role, None)
        return user.id

    async def _resolve_identity(
        self,
        provider: Any,
        code: str,
        code_verifier: str,
        *,
        redirect_uri: str,
    ) -> OAuthUserIdentity:
        client_secret = await self._resolve_secret(provider.client_secret_ref)
        client = self._provider_client(provider.provider_type)
        token_payload = await client.exchange_code(
            client_id=provider.client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
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
                locale=str(user_payload.get("locale") or "") or None,
                timezone=None,
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
            locale=None,
            timezone=None,
            avatar_url=str(user_payload.get("avatar_url") or "") or None,
            groups=[*org_markers, *list(groups)],
        )

    def _initial_user_status(self, identity: OAuthUserIdentity) -> UserStatus:
        if not identity.name or not identity.locale or not identity.timezone:
            return UserStatus.pending_profile_completion
        if self.settings.accounts.signup_mode == "admin_approval":
            return UserStatus.pending_approval
        return UserStatus.active

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
        tenant = current_tenant.get(None)
        if tenant is not None and str(payload.get("tenant_id")) != str(tenant.id):
            raise OAuthStateInvalidError()
        return cast(dict[str, Any], jsonable_encoder(payload))

    def _tenant_callback_url(self, provider_type: str, fallback: str) -> str:
        tenant = current_tenant.get(None)
        domain = self.settings.PLATFORM_DOMAIN.strip().lower().rstrip(".")
        if _is_loopback_redirect_uri(fallback):
            return fallback
        if tenant is None or not domain:
            return fallback
        return f"https://{tenant.subdomain}.{domain}/auth/oauth/{provider_type}/callback"

    async def _resolve_secret(self, reference: str) -> str:
        if reference.startswith(_PLAINTEXT_SECRET_PREFIX):
            return reference.removeprefix(_PLAINTEXT_SECRET_PREFIX)
        return await self._require_secret_provider().get(reference)

    def _require_secret_provider(self) -> SecretProvider:
        if self.secret_provider is None:
            raise ValidationError(
                "SECRET_PROVIDER_UNAVAILABLE",
                "OAuth secret operation requires a configured SecretProvider",
            )
        return self.secret_provider

    async def _put_secret(self, reference: str, value: str) -> None:
        await self._require_secret_provider().put(reference, {"value": value})

    async def _flush_secret_cache(self, reference: str) -> None:
        await self._require_secret_provider().flush_cache(reference)

    async def _list_secret_versions(self, reference: str) -> list[int]:
        try:
            return await self._require_secret_provider().list_versions(reference)
        except CredentialPolicyDeniedError:
            raise
        except CredentialUnavailableError:
            return []

    def _resolve_role(self, provider: Any, groups: list[str]) -> str:
        for group in groups:
            role = provider.group_role_mapping.get(group)
            if role:
                return str(role)
        return str(provider.default_role)

    @staticmethod
    def _validate_role(role: str) -> None:
        if not role or not role.strip():
            raise ValidationError("OAUTH_ROLE_INVALID", "OAuth role mapping cannot be blank")
        normalized = role.strip()
        if normalized not in _VALID_OAUTH_BOOTSTRAP_ROLES:
            valid_roles = ", ".join(sorted(_VALID_OAUTH_BOOTSTRAP_ROLES))
            raise ValidationError(
                "OAUTH_ROLE_INVALID",
                f"Unknown OAuth role mapping role: {normalized}. Valid roles: {valid_roles}",
            )

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
            "source": OAuthService._source_value(getattr(provider, "source", None)),
        }

    @staticmethod
    def _diff_provider(
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if before is None:
            return {
                "created": True,
                **{
                    key: OAuthService._redact_provider_audit_value(key, value)
                    for key, value in (after or {}).items()
                },
            }
        changed: dict[str, Any] = {}
        for key, value in (after or {}).items():
            if before.get(key) != value:
                changed[key] = {
                    "before": OAuthService._redact_provider_audit_value(
                        key,
                        before.get(key),
                    ),
                    "after": OAuthService._redact_provider_audit_value(key, value),
                }
        return changed

    @staticmethod
    def _redact_provider_audit_value(key: str, value: Any) -> Any:
        if (
            key == "client_secret_ref"
            and isinstance(value, str)
            and value.startswith(_PLAINTEXT_SECRET_PREFIX)
        ):
            return _REDACTED_PLAINTEXT_SECRET_REF
        return value

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
            source=OAuthProviderSourceType(
                OAuthService._source_value(getattr(provider, "source", None))
            ),
            last_edited_by=getattr(provider, "last_edited_by", None),
            last_edited_at=getattr(provider, "last_edited_at", None),
            last_successful_auth_at=getattr(provider, "last_successful_auth_at", None),
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )

    @staticmethod
    def _serialize_history_entry(entry: Any) -> OAuthHistoryEntryResponse:
        changed = dict(entry.changed_fields or {})
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        for key, value in changed.items():
            if isinstance(value, dict) and {"before", "after"}.issubset(value):
                before[key] = value.get("before")
                after[key] = value.get("after")
        return OAuthHistoryEntryResponse(
            timestamp=entry.created_at,
            admin_id=entry.actor_id,
            action=entry.action,
            before=before or None,
            after=after or None,
        )

    def _default_rate_limits(self) -> OAuthRateLimitConfig:
        return OAuthRateLimitConfig(
            per_ip_max=self.settings.auth.oauth_rate_limit_max,
            per_ip_window=self.settings.auth.oauth_rate_limit_window,
            per_user_max=self.settings.auth.oauth_rate_limit_max,
            per_user_window=self.settings.auth.oauth_rate_limit_window,
            global_max=self.settings.auth.oauth_rate_limit_max,
            global_window=self.settings.auth.oauth_rate_limit_window,
        )

    @staticmethod
    def _serialize_rate_limits(limits: Any) -> OAuthRateLimitConfig:
        return OAuthRateLimitConfig(
            per_ip_max=limits.per_ip_max,
            per_ip_window=limits.per_ip_window,
            per_user_max=limits.per_user_max,
            per_user_window=limits.per_user_window,
            global_max=limits.global_max,
            global_window=limits.global_window,
        )

    @staticmethod
    def _source_value(source: Any) -> str:
        if source is None:
            return "manual"
        return str(getattr(source, "value", source))

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
        credential = await self.auth_repository.get_credential_by_user_id(user_id)
        return {
            "id": str(user_id),
            "email": platform_user.email,
            "display_name": platform_user.display_name or identity.email.split("@", 1)[0],
            "avatar_url": identity.avatar_url,
            "status": platform_user.status,
            "roles": [role.role for role in roles],
            "workspace_id": None,
            "mfa_enrolled": bool(
                enrollment is not None and getattr(enrollment, "status", "") == "active"
            ),
            "has_local_password": credential is not None,
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
