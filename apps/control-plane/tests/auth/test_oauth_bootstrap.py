from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from platform.admin.bootstrap import BootstrapConfigError
from platform.auth.services.oauth_bootstrap import (
    _resolve_client_secret,
    bootstrap_oauth_provider_from_env,
)
from platform.common.config import PlatformSettings
from typing import Any

import pytest
from tests.auth_oauth_support import OAuthRepositoryStub, build_provider


OAUTH_ENV_KEYS = (
    "PLATFORM_ENVIRONMENT",
    "PLATFORM_OAUTH_GOOGLE_ALLOWED_DOMAINS",
    "PLATFORM_OAUTH_GOOGLE_CLIENT_ID",
    "PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET",
    "PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET_FILE",
    "PLATFORM_OAUTH_GOOGLE_ENABLED",
    "PLATFORM_OAUTH_GOOGLE_FORCE_UPDATE",
    "PLATFORM_OAUTH_GOOGLE_GROUP_ROLE_MAPPINGS",
    "PLATFORM_OAUTH_GOOGLE_REDIRECT_URI",
    "PLATFORM_OAUTH_GITHUB_ALLOWED_ORGS",
    "PLATFORM_OAUTH_GITHUB_CLIENT_ID",
    "PLATFORM_OAUTH_GITHUB_CLIENT_SECRET",
    "PLATFORM_OAUTH_GITHUB_CLIENT_SECRET_FILE",
    "PLATFORM_OAUTH_GITHUB_ENABLED",
    "PLATFORM_OAUTH_GITHUB_FORCE_UPDATE",
    "PLATFORM_OAUTH_GITHUB_REDIRECT_URI",
    "PLATFORM_OAUTH_GITHUB_TEAM_ROLE_MAPPINGS",
)


@pytest.fixture(autouse=True)
def clean_oauth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in OAUTH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


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


def _github_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "dev")
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_ENABLED", "true")
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_CLIENT_ID", "Iv1TestClient")
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_CLIENT_SECRET", "github-secret")
    monkeypatch.setenv(
        "PLATFORM_OAUTH_GITHUB_REDIRECT_URI",
        "https://app.example.com/auth/oauth/github/callback",
    )
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_ALLOWED_ORGS", "musematic")
    monkeypatch.setenv(
        "PLATFORM_OAUTH_GITHUB_TEAM_ROLE_MAPPINGS",
        '{"musematic/platform":"platform_admin"}',
    )


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


class FailingPutSecretProvider(SecretProviderStub):
    async def put(self, path: str, values: dict[str, str]) -> None:
        del path, values
        raise RuntimeError("vault down")


class FailingAuditRepository(OAuthRepositoryStub):
    async def create_audit_entry(self, **kwargs: Any) -> Any:
        del kwargs
        raise RuntimeError("audit unavailable")


@pytest.mark.asyncio
async def test_google_bootstrap_writes_secret_and_env_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    repository = OAuthRepositoryStub()
    secrets = SecretProviderStub()

    result = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=PlatformSettings(),
        secret_provider=secrets,
        producer=None,
        provider_type="google",
    )

    provider = repository.providers["google"]
    assert result.status == "created"
    assert provider.source == "env_var"
    assert provider.domain_restrictions == ["example.com"]
    assert provider.group_role_mapping == {"admins": "admin"}
    assert provider.client_secret_ref == "secret/data/musematic/dev/oauth/google/client-secret"
    assert secrets.values[provider.client_secret_ref] == {"value": "google-secret"}


@pytest.mark.asyncio
async def test_github_bootstrap_writes_team_mappings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _github_env(monkeypatch)
    repository = OAuthRepositoryStub()

    result = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=PlatformSettings(),
        secret_provider=SecretProviderStub(),
        producer=None,
        provider_type="github",
    )

    provider = repository.providers["github"]
    assert result.status == "created"
    assert provider.org_restrictions == ["musematic"]
    assert provider.group_role_mapping == {"musematic/platform": "platform_admin"}


@pytest.mark.asyncio
async def test_disabled_provider_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_ENABLED", "false")
    repository = OAuthRepositoryStub()

    result = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=PlatformSettings(),
        secret_provider=SecretProviderStub(),
        producer=None,
        provider_type="google",
    )

    assert result.status == "skipped_disabled"
    assert repository.providers == {}
    assert repository.audit_entries == []


@pytest.mark.asyncio
async def test_idempotent_rerun_skips_existing_provider_without_audit(
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
async def test_force_update_overwrites_existing_provider_with_critical_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_FORCE_UPDATE", "true")
    existing = build_provider(provider_type="google", domain_restrictions=["old.example"])
    repository = OAuthRepositoryStub(providers={"google": existing})

    result = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=PlatformSettings(),
        secret_provider=SecretProviderStub(),
        producer=None,
        provider_type="google",
    )

    assert result.status == "updated"
    assert existing.source == "env_var"
    assert existing.domain_restrictions == ["example.com"]
    assert repository.audit_entries[-1]["action"] == "config_reseeded"
    assert repository.audit_entries[-1]["changed_fields"]["severity"] == "critical"


@pytest.mark.asyncio
async def test_external_source_provider_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    _google_env(monkeypatch)
    existing = build_provider(provider_type="google")
    existing.source = "ibor"
    repository = OAuthRepositoryStub(providers={"google": existing})
    secrets = SecretProviderStub()

    result = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=PlatformSettings(),
        secret_provider=secrets,
        producer=None,
        provider_type="google",
    )

    assert result.status == "skipped_external_source"
    assert secrets.put_calls == []
    assert existing.source == "ibor"


@pytest.mark.asyncio
async def test_vault_failure_raises_bootstrap_config_error_without_db_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    repository = OAuthRepositoryStub()

    with pytest.raises(BootstrapConfigError, match="Vault unreachable"):
        await bootstrap_oauth_provider_from_env(
            repository=repository,
            settings=PlatformSettings(),
            secret_provider=FailingPutSecretProvider(),
            producer=None,
            provider_type="google",
        )

    assert repository.providers == {}
    assert repository.audit_entries == []


@pytest.mark.asyncio
async def test_audit_failure_bubbles_after_secret_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    repository = FailingAuditRepository()
    secrets = SecretProviderStub()

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await bootstrap_oauth_provider_from_env(
            repository=repository,
            settings=PlatformSettings(),
            secret_provider=secrets,
            producer=None,
            provider_type="google",
        )

    assert secrets.put_calls
    assert repository.providers["google"].source == "env_var"


@pytest.mark.asyncio
async def test_both_providers_can_be_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    _github_env(monkeypatch)
    repository = OAuthRepositoryStub()
    secrets = SecretProviderStub()

    google = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=PlatformSettings(),
        secret_provider=secrets,
        producer=None,
        provider_type="google",
    )
    github = await bootstrap_oauth_provider_from_env(
        repository=repository,
        settings=PlatformSettings(),
        secret_provider=secrets,
        producer=None,
        provider_type="github",
    )

    assert [google.status, github.status] == ["created", "created"]
    assert set(repository.providers) == {"google", "github"}
    assert len(secrets.put_calls) == 2


def test_secret_file_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "google-secret"
    secret_file.write_text("secret-from-file\n", encoding="utf-8")
    _google_env(monkeypatch)
    monkeypatch.delenv("PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET_FILE", str(secret_file))

    assert _resolve_client_secret(PlatformSettings().oauth_bootstrap.google) == "secret-from-file"


def test_missing_secret_raises_bootstrap_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _google_env(monkeypatch)
    monkeypatch.delenv("PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET")

    with pytest.raises(BootstrapConfigError, match="client_secret OR client_secret_file"):
        _resolve_client_secret(PlatformSettings().oauth_bootstrap.google)


def test_validation_failures_are_caught_before_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "production")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_REDIRECT_URI", "http://localhost/callback")

    with pytest.raises(ValueError, match="must use HTTPS"):
        PlatformSettings()
