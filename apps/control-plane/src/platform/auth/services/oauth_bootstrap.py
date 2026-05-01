from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from platform.admin.bootstrap import BootstrapConfigError
from platform.auth.events import (
    OAuthConfigReseededPayload,
    OAuthProviderBootstrappedPayload,
    publish_auth_event,
)
from platform.auth.models import OAuthProviderSource
from platform.auth.repository_oauth import OAuthRepository
from platform.common.config import (
    OAuthGithubBootstrap,
    OAuthGoogleBootstrap,
    PlatformSettings,
)
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.common.secret_provider import SecretProvider
from platform.common.tenant_context import current_tenant
from platform.tenants.vault_paths import tenant_vault_path
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

LOGGER = get_logger(__name__)

ProviderType = Literal["google", "github"]
_VALID_ENVIRONMENTS = {"production", "staging", "dev", "test", "ci"}
_PLAINTEXT_SECRET_PREFIX = "plain:"
_REDACTED_PLAINTEXT_SECRET_REF = "plain:<redacted>"


@dataclass(frozen=True)
class OAuthBootstrapProviderResult:
    provider_type: ProviderType
    status: str
    changed_fields: dict[str, Any]
    audit_event_id: UUID | None = None


def oauth_bootstrap_enabled(settings: PlatformSettings) -> bool:
    return bool(settings.oauth_bootstrap.google.enabled or settings.oauth_bootstrap.github.enabled)


async def bootstrap_oauth_providers_from_env(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: PlatformSettings,
    secret_provider: SecretProvider,
    audit_chain: Any | None = None,
    producer: EventProducer | None = None,
    provider_types: Iterable[ProviderType] | None = None,
    actor_id: UUID | None = None,
    force_update_override: bool | None = None,
) -> list[OAuthBootstrapProviderResult]:
    selected = list(provider_types or ("google", "github"))
    try:
        async with session_factory() as session:
            async with session.begin():
                repository = OAuthRepository(session, audit_chain)
                results = []
                for provider_type in selected:
                    results.append(
                        await bootstrap_oauth_provider_from_env(
                            repository=repository,
                            settings=settings,
                            secret_provider=secret_provider,
                            producer=producer,
                            provider_type=provider_type,
                            actor_id=actor_id,
                            force_update_override=force_update_override,
                        )
                    )
                return results
    except BootstrapConfigError:
        raise
    except Exception as exc:
        raise BootstrapConfigError(f"OAuth provider bootstrap failed: {exc}") from exc


async def bootstrap_oauth_provider_from_env(
    *,
    repository: OAuthRepository,
    settings: PlatformSettings,
    secret_provider: SecretProvider,
    producer: EventProducer | None,
    provider_type: ProviderType,
    actor_id: UUID | None = None,
    force_update_override: bool | None = None,
) -> OAuthBootstrapProviderResult:
    config = _provider_config(settings, provider_type)
    if not config.enabled:
        return OAuthBootstrapProviderResult(provider_type, "skipped_disabled", {})

    force_update = config.force_update if force_update_override is None else force_update_override
    existing = await repository.get_by_type_for_update(provider_type)
    existing_source = _source_value(getattr(existing, "source", None))
    if existing is not None and existing_source not in {"manual", "env_var", ""}:
        LOGGER.warning(
            "OAuth bootstrap skipped for provider %s from external source %s",
            provider_type,
            existing_source,
        )
        return OAuthBootstrapProviderResult(provider_type, "skipped_external_source", {})

    before = _provider_snapshot(existing)
    if existing is not None and not force_update:
        LOGGER.info(
            "OAuth bootstrap skipped for provider %s because a provider already exists",
            provider_type,
        )
        return OAuthBootstrapProviderResult(provider_type, "skipped_existing_provider", {})

    secret = _resolve_client_secret(config)
    secret_path = _secret_path(settings, provider_type)
    try:
        await secret_provider.put(secret_path, {"value": secret})
    except Exception as exc:
        raise BootstrapConfigError(
            f"Vault unreachable; cannot bootstrap OAuth provider '{provider_type}'"
        ) from exc

    provider, created = await repository.upsert_provider(
        provider_type,
        display_name="Google" if provider_type == "google" else "GitHub",
        enabled=True,
        client_id=config.client_id,
        client_secret_ref=secret_path,
        redirect_uri=config.redirect_uri,
        scopes=_default_scopes(provider_type),
        domain_restrictions=list(
            config.allowed_domains if isinstance(config, OAuthGoogleBootstrap) else []
        ),
        org_restrictions=list(
            config.allowed_orgs if isinstance(config, OAuthGithubBootstrap) else []
        ),
        group_role_mapping=dict(
            config.group_role_mappings
            if isinstance(config, OAuthGoogleBootstrap)
            else config.team_role_mappings
        ),
        default_role=config.default_role,
        require_mfa=config.require_mfa,
        source=OAuthProviderSource.env_var,
        last_edited_by=None,
        last_edited_at=datetime.now(UTC),
    )
    after = _provider_snapshot(provider)
    changed_fields = _diff_provider(before, after)
    if force_update and not created:
        changed_fields.setdefault("force_update", True)
        changed_fields.setdefault("overrode_source", existing_source or "manual")
        changed_fields.setdefault("severity", "critical")

    action = "provider_bootstrapped" if created else "config_reseeded"
    audit = await repository.create_audit_entry(
        provider_type=provider.provider_type,
        provider_id=provider.id,
        user_id=None,
        external_id=None,
        action=action,
        outcome="success",
        failure_reason=None,
        source_ip=None,
        user_agent=None,
        actor_id=actor_id,
        changed_fields=changed_fields,
    )
    if action == "provider_bootstrapped":
        await publish_auth_event(
            "auth.oauth.provider_bootstrapped",
            OAuthProviderBootstrappedPayload(
                actor_id=actor_id,
                provider_type=provider.provider_type,
                source="env_var",
                force_update_used=force_update,
            ),
            uuid4(),
            producer,
        )
    else:
        await publish_auth_event(
            "auth.oauth.config_reseeded",
            OAuthConfigReseededPayload(
                actor_id=actor_id,
                provider_type=provider.provider_type,
                force_update=force_update,
                changed_fields=sorted(changed_fields),
            ),
            uuid4(),
            producer,
        )
    return OAuthBootstrapProviderResult(
        provider_type,
        "created" if created else "updated",
        changed_fields,
        audit_event_id=audit.id,
    )


def _provider_config(
    settings: PlatformSettings,
    provider_type: ProviderType,
) -> OAuthGoogleBootstrap | OAuthGithubBootstrap:
    if provider_type == "google":
        return settings.oauth_bootstrap.google
    return settings.oauth_bootstrap.github


def _resolve_client_secret(config: OAuthGoogleBootstrap | OAuthGithubBootstrap) -> str:
    if config.client_secret is not None:
        return config.client_secret.get_secret_value()
    if config.client_secret_file:
        return Path(config.client_secret_file).read_text(encoding="utf-8").strip()
    raise BootstrapConfigError("client_secret OR client_secret_file required")


def _secret_path(settings: PlatformSettings, provider_type: ProviderType) -> str:
    environment = (
        (
            os.getenv("PLATFORM_ENVIRONMENT")
            or os.getenv("PLATFORM_ENV")
            or os.getenv("ENVIRONMENT")
            or os.getenv("ENV")
            or settings.profile
        )
        .strip()
        .lower()
    )
    if environment not in _VALID_ENVIRONMENTS:
        environment = "dev"
    tenant = current_tenant.get(None)
    tenant_slug = tenant.slug if tenant is not None else "default"
    return tenant_vault_path(environment, tenant_slug, "oauth", f"{provider_type}/client-secret")


def _default_scopes(provider_type: ProviderType) -> list[str]:
    if provider_type == "google":
        return ["openid", "email", "profile"]
    return ["read:user", "user:email"]


def _source_value(source: Any) -> str:
    if source is None:
        return ""
    return str(getattr(source, "value", source))


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
        "source": _source_value(getattr(provider, "source", None)) or "manual",
    }


def _diff_provider(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    if before is None:
        return {"created": True, "changed_fields": sorted((after or {}).keys())}
    changed: dict[str, Any] = {}
    for key, value in (after or {}).items():
        if before.get(key) != value:
            changed[key] = {
                "before": _redact_provider_audit_value(key, before.get(key)),
                "after": _redact_provider_audit_value(key, value),
            }
    return changed


def _redact_provider_audit_value(key: str, value: Any) -> Any:
    if (
        key == "client_secret_ref"
        and isinstance(value, str)
        and value.startswith(_PLAINTEXT_SECRET_PREFIX)
    ):
        return _REDACTED_PLAINTEXT_SECRET_REF
    return value
