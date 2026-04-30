from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from typing import Any

import pytest


ProviderClient = Any
ProviderPayloadFactory = Callable[[str, str], dict[str, Any]]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _base_provider_payload(provider: str, platform_api_url: str) -> dict[str, Any]:
    callbacks = {
        "google": f"{platform_api_url.rstrip('/')}/api/v1/auth/oauth/google/callback",
        "github": f"{platform_api_url.rstrip('/')}/api/v1/auth/oauth/github/callback",
    }
    if provider == "google":
        return {
            "display_name": "E2E Google",
            "enabled": True,
            "client_id": _env(
                "E2E_OAUTH_GOOGLE_CLIENT_ID",
                "e2e-google-client.apps.googleusercontent.com",
            ),
            "client_secret_ref": _env(
                "E2E_OAUTH_GOOGLE_CLIENT_SECRET_REF",
                "secret/data/musematic/dev/oauth/google/client-secret",
            ),
            "redirect_uri": callbacks["google"],
            "scopes": ["openid", "email", "profile"],
            "domain_restrictions": ["company.com"],
            "org_restrictions": [],
            "group_role_mapping": {"admins@company.com": "admin"},
            "default_role": "member",
            "require_mfa": False,
            "source": "env_var",
        }
    if provider == "github":
        return {
            "display_name": "E2E GitHub",
            "enabled": True,
            "client_id": _env("E2E_OAUTH_GITHUB_CLIENT_ID", "e2e-github-client"),
            "client_secret_ref": _env(
                "E2E_OAUTH_GITHUB_CLIENT_SECRET_REF",
                "secret/data/musematic/dev/oauth/github/client-secret",
            ),
            "redirect_uri": callbacks["github"],
            "scopes": ["read:user", "user:email"],
            "domain_restrictions": [],
            "org_restrictions": ["musematic-e2e"],
            "group_role_mapping": {"musematic-e2e/admins": "admin"},
            "default_role": "member",
            "require_mfa": False,
            "source": "env_var",
        }
    raise AssertionError(f"unsupported OAuth provider: {provider}")


async def _json(client: ProviderClient, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = await client.request(method, path, **kwargs)
    assert response.status_code in {200, 201, 202, 204}, response.text
    if response.status_code == 204 or not response.content:
        return {}
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


async def _upsert_provider(
    client: ProviderClient,
    provider: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await _json(client, "PUT", f"/api/v1/admin/oauth/providers/{provider}", json=payload)


async def _admin_providers(client: ProviderClient) -> dict[str, dict[str, Any]]:
    payload = await _json(client, "GET", "/api/v1/admin/oauth/providers")
    return {
        str(item["provider_type"]): item
        for item in payload.get("providers", [])
        if isinstance(item, dict)
    }


async def _ensure_bootstrap_provider(
    client: ProviderClient,
    provider: str,
    platform_api_url: str,
    **overrides: Any,
) -> dict[str, Any]:
    payload = _base_provider_payload(provider, platform_api_url) | overrides
    return await _upsert_provider(client, provider, payload)


def _vault_versions(path: str) -> list[int]:
    if shutil.which("vault") is None:
        pytest.skip("vault CLI is required to validate live Vault KV versions")
    cli_path = path.replace("secret/data/", "secret/", 1)
    completed = subprocess.run(
        ["vault", "kv", "metadata", "get", "-format=json", cli_path],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return []
    return [1]


@pytest.fixture(scope="session")
def kind_cluster_with_oauth_env_vars() -> dict[str, str]:
    return {
        "PLATFORM_OAUTH_GOOGLE_ENABLED": _env("PLATFORM_OAUTH_GOOGLE_ENABLED", "true"),
        "PLATFORM_OAUTH_GITHUB_ENABLED": _env("PLATFORM_OAUTH_GITHUB_ENABLED", "true"),
        "PLATFORM_VAULT_MODE": _env("PLATFORM_VAULT_MODE", "mock"),
    }


@pytest.fixture(scope="session")
def mock_oauth_provider_endpoints() -> dict[str, str]:
    return {
        "google": _env("MOCK_GOOGLE_OIDC_URL", "http://localhost:8083"),
        "github": _env("MOCK_GITHUB_OAUTH_URL", "http://localhost:8084"),
    }


@pytest.fixture(scope="session")
def populated_vault() -> Callable[[str], list[int]]:
    return _vault_versions


@pytest.fixture
async def clean_oauth_state(http_client: ProviderClient) -> ProviderClient:
    return http_client


@pytest.fixture
async def oauth_provider_payload(platform_api_url: str) -> ProviderPayloadFactory:
    return lambda provider, source="env_var": _base_provider_payload(
        provider,
        platform_api_url,
    ) | {"source": source}


@pytest.fixture
async def bootstrapped_oauth_providers(
    clean_oauth_state: ProviderClient,
    platform_api_url: str,
) -> dict[str, dict[str, Any]]:
    google = await _ensure_bootstrap_provider(clean_oauth_state, "google", platform_api_url)
    github = await _ensure_bootstrap_provider(clean_oauth_state, "github", platform_api_url)
    return {"google": google, "github": github}


@pytest.fixture
def oauth_admin_providers() -> Callable[[ProviderClient], Awaitable[dict[str, dict[str, Any]]]]:
    return _admin_providers


@pytest.fixture
def ensure_bootstrap_provider() -> Callable[..., Awaitable[dict[str, Any]]]:
    return _ensure_bootstrap_provider
