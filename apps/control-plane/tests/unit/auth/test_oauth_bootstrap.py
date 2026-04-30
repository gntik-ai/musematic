from __future__ import annotations

from platform.auth.services.oauth_bootstrap import bootstrap_oauth_provider_from_env
from platform.common.config import PlatformSettings
from typing import Any

import pytest
from tests.auth_oauth_support import OAuthRepositoryStub, build_provider


class SecretProviderStub:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, str]] = {}
        self.put_calls: list[tuple[str, dict[str, str]]] = []

    async def get(self, path: str, key: str = "value") -> str:
        return self.values[path][key]

    async def put(self, path: str, values: dict[str, str]) -> None:
        self.put_calls.append((path, dict(values)))
        self.values[path] = dict(values)

    async def flush_cache(self, path: str | None = None) -> None:
        del path

    async def delete_version(self, path: str, version: int) -> None:
        del path, version

    async def list_versions(self, path: str) -> list[int]:
        return [1] if path in self.values else []

    async def health_check(self) -> Any:
        return None


def _google_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "dev")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_ENABLED", "true")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_CLIENT_ID", "test.apps.googleusercontent.com")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv(
        "PLATFORM_OAUTH_GOOGLE_REDIRECT_URI",
        "https://app.example.com/auth/oauth/google/callback",
    )
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_ALLOWED_DOMAINS", "example.com")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_GROUP_ROLE_MAPPINGS", '{"admins":"admin"}')


def test_oauth_bootstrap_settings_load_platform_prefixed_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)

    settings = PlatformSettings()

    assert settings.oauth_bootstrap.google.enabled is True
    assert settings.oauth_bootstrap.google.client_id == "test.apps.googleusercontent.com"
    assert settings.oauth_bootstrap.google.allowed_domains == ["example.com"]
    assert settings.oauth_bootstrap.google.group_role_mappings == {"admins": "admin"}


def test_oauth_bootstrap_settings_reject_mutually_exclusive_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET_FILE", "/tmp/google-secret")

    with pytest.raises(ValueError, match="mutually exclusive"):
        PlatformSettings()


@pytest.mark.asyncio
async def test_bootstrap_google_creates_provider_and_writes_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    settings = PlatformSettings()
    repository = OAuthRepositoryStub(providers={})
    secrets = SecretProviderStub()

    result = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=settings,
        secret_provider=secrets,
        producer=None,
        provider_type="google",
    )

    provider = repository.providers["google"]
    assert result.status == "created"
    assert provider.source == "env_var"
    assert provider.client_secret_ref == "secret/data/musematic/dev/oauth/google/client-secret"
    assert secrets.values[provider.client_secret_ref] == {"value": "google-secret"}
    assert repository.audit_entries[-1]["action"] == "provider_bootstrapped"


@pytest.mark.asyncio
async def test_bootstrap_existing_provider_is_idempotent_without_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    existing = build_provider(provider_type="google")
    repository = OAuthRepositoryStub(providers={"google": existing})
    secrets = SecretProviderStub()

    result = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=PlatformSettings(),
        secret_provider=secrets,
        producer=None,
        provider_type="google",
    )

    assert result.status == "skipped_existing_provider"
    assert secrets.put_calls == []
    assert repository.audit_entries == []


@pytest.mark.asyncio
async def test_bootstrap_force_update_overwrites_existing_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_FORCE_UPDATE", "true")
    existing = build_provider(provider_type="google", domain_restrictions=["old.example"])
    repository = OAuthRepositoryStub(providers={"google": existing})
    secrets = SecretProviderStub()

    result = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=PlatformSettings(),
        secret_provider=secrets,
        producer=None,
        provider_type="google",
    )

    assert result.status == "updated"
    assert existing.source == "env_var"
    assert existing.domain_restrictions == ["example.com"]
    assert repository.audit_entries[-1]["action"] == "config_reseeded"
    assert repository.audit_entries[-1]["changed_fields"]["severity"] == "critical"
    assert (
        repository.audit_entries[-1]["changed_fields"]["client_secret_ref"]["before"]
        == "plain:<redacted>"
    )
    assert "google-secret" not in str(repository.audit_entries[-1]["changed_fields"])
