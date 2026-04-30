from __future__ import annotations

from collections.abc import Iterator

import pytest
from platform.common.config import PlatformSettings


OAUTH_ENV_KEYS = (
    "ALLOW_INSECURE",
    "ENV",
    "ENVIRONMENT",
    "PLATFORM_ENV",
    "PLATFORM_ENVIRONMENT",
    "PLATFORM_OAUTH_GOOGLE_ALLOWED_DOMAINS",
    "PLATFORM_OAUTH_GOOGLE_CLIENT_ID",
    "PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET",
    "PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET_FILE",
    "PLATFORM_OAUTH_GOOGLE_DEFAULT_ROLE",
    "PLATFORM_OAUTH_GOOGLE_ENABLED",
    "PLATFORM_OAUTH_GOOGLE_FORCE_UPDATE",
    "PLATFORM_OAUTH_GOOGLE_GROUP_ROLE_MAPPINGS",
    "PLATFORM_OAUTH_GOOGLE_REDIRECT_URI",
    "PLATFORM_OAUTH_GOOGLE_REQUIRE_MFA",
    "PLATFORM_OAUTH_GITHUB_ALLOWED_ORGS",
    "PLATFORM_OAUTH_GITHUB_CLIENT_ID",
    "PLATFORM_OAUTH_GITHUB_CLIENT_SECRET",
    "PLATFORM_OAUTH_GITHUB_CLIENT_SECRET_FILE",
    "PLATFORM_OAUTH_GITHUB_DEFAULT_ROLE",
    "PLATFORM_OAUTH_GITHUB_ENABLED",
    "PLATFORM_OAUTH_GITHUB_FORCE_UPDATE",
    "PLATFORM_OAUTH_GITHUB_REDIRECT_URI",
    "PLATFORM_OAUTH_GITHUB_REQUIRE_MFA",
    "PLATFORM_OAUTH_GITHUB_TEAM_ROLE_MAPPINGS",
)


@pytest.fixture(autouse=True)
def clean_oauth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in OAUTH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


def _google_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "production")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_ENABLED", "true")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_CLIENT_ID", "app.apps.googleusercontent.com")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv(
        "PLATFORM_OAUTH_GOOGLE_REDIRECT_URI",
        "https://app.example.com/auth/oauth/google/callback",
    )


def _github_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "production")
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_ENABLED", "true")
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_CLIENT_ID", "Iv1TestClient")
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_CLIENT_SECRET", "github-secret")
    monkeypatch.setenv(
        "PLATFORM_OAUTH_GITHUB_REDIRECT_URI",
        "https://app.example.com/auth/oauth/github/callback",
    )


def test_default_empty_oauth_bootstrap_config_is_disabled() -> None:
    settings = PlatformSettings()

    assert settings.oauth_bootstrap.google.enabled is False
    assert settings.oauth_bootstrap.github.enabled is False
    assert settings.oauth_bootstrap.google.client_id == ""
    assert settings.oauth_bootstrap.github.default_role == "member"


def test_valid_google_config_loads_platform_prefixed_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_ALLOWED_DOMAINS", "example.com,corp.example")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_GROUP_ROLE_MAPPINGS", '{"admins":"admin"}')
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_REQUIRE_MFA", "true")

    config = PlatformSettings().oauth_bootstrap.google

    assert config.enabled is True
    assert config.client_id == "app.apps.googleusercontent.com"
    assert config.client_secret is not None
    assert config.client_secret.get_secret_value() == "google-secret"
    assert config.allowed_domains == ["example.com", "corp.example"]
    assert config.group_role_mappings == {"admins": "admin"}
    assert config.require_mfa is True


def test_valid_github_config_loads_orgs_and_team_role_mappings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _github_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_ALLOWED_ORGS", '["musematic","platform"]')
    monkeypatch.setenv(
        "PLATFORM_OAUTH_GITHUB_TEAM_ROLE_MAPPINGS",
        '{"musematic/admins":"platform_admin"}',
    )

    config = PlatformSettings().oauth_bootstrap.github

    assert config.enabled is True
    assert config.allowed_orgs == ["musematic", "platform"]
    assert config.team_role_mappings == {"musematic/admins": "platform_admin"}


def test_enabled_google_requires_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _google_env(monkeypatch)
    monkeypatch.delenv("PLATFORM_OAUTH_GOOGLE_CLIENT_ID")

    with pytest.raises(ValueError, match="CLIENT_ID is required"):
        PlatformSettings()


def test_enabled_google_rejects_invalid_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_CLIENT_ID", "plain-client-id")

    with pytest.raises(ValueError, match="apps.googleusercontent.com"):
        PlatformSettings()


def test_enabled_github_rejects_invalid_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _github_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_CLIENT_ID", "client id with spaces")

    with pytest.raises(ValueError, match="alphanumeric"):
        PlatformSettings()


def test_client_secret_and_secret_file_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET_FILE", "/etc/secrets/google")

    with pytest.raises(ValueError, match="mutually exclusive"):
        PlatformSettings()


def test_invalid_role_mapping_json_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_GROUP_ROLE_MAPPINGS", "{invalid-json")

    with pytest.raises(ValueError):
        PlatformSettings()


def test_unknown_role_in_mapping_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_GROUP_ROLE_MAPPINGS", '{"admins":"owner"}')

    with pytest.raises(ValueError, match="Unknown OAuth bootstrap role"):
        PlatformSettings()


def test_non_https_redirect_uri_is_rejected_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_REDIRECT_URI", "http://app.example.com/callback")

    with pytest.raises(ValueError, match="must use HTTPS"):
        PlatformSettings()


def test_non_https_redirect_uri_is_allowed_in_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _google_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "dev")
    monkeypatch.setenv("PLATFORM_OAUTH_GOOGLE_REDIRECT_URI", "http://localhost:3000/callback")

    assert PlatformSettings().oauth_bootstrap.google.redirect_uri.startswith("http://")


def test_allow_insecure_flag_permits_http_redirect_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _github_env(monkeypatch)
    monkeypatch.setenv("ALLOW_INSECURE", "true")
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_REDIRECT_URI", "http://localhost:3000/callback")

    assert PlatformSettings().oauth_bootstrap.github.redirect_uri.startswith("http://")


def test_force_update_flag_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    _github_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_OAUTH_GITHUB_FORCE_UPDATE", "true")

    assert PlatformSettings().oauth_bootstrap.github.force_update is True
