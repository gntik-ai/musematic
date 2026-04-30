from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_google_bootstrap_creates_env_source_provider(
    bootstrapped_oauth_providers,
    kind_cluster_with_oauth_env_vars,
) -> None:
    assert kind_cluster_with_oauth_env_vars["PLATFORM_OAUTH_GOOGLE_ENABLED"] == "true"
    google = bootstrapped_oauth_providers["google"]
    assert google["provider_type"] == "google"
    assert google["enabled"] is True
    assert google["source"] == "env_var"


@pytest.mark.asyncio
async def test_google_bootstrap_uses_canonical_vault_path(
    bootstrapped_oauth_providers,
    populated_vault,
) -> None:
    google = bootstrapped_oauth_providers["google"]
    path = google["client_secret_ref"]
    assert path == "secret/data/musematic/dev/oauth/google/client-secret"
    if google["source"] == "env_var":
        versions = populated_vault(path)
        assert versions


@pytest.mark.asyncio
async def test_google_bootstrap_exposes_public_login_button_provider(
    http_client,
    bootstrapped_oauth_providers,
) -> None:
    del bootstrapped_oauth_providers
    response = await http_client.get("/api/v1/auth/oauth/providers")
    response.raise_for_status()
    providers = {item["provider_type"]: item for item in response.json()["providers"]}
    assert providers["google"]["display_name"]
