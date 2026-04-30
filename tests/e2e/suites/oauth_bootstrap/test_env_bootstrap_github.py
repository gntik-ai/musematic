from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_github_bootstrap_creates_env_source_provider(
    bootstrapped_oauth_providers,
    kind_cluster_with_oauth_env_vars,
) -> None:
    assert kind_cluster_with_oauth_env_vars["PLATFORM_OAUTH_GITHUB_ENABLED"] == "true"
    github = bootstrapped_oauth_providers["github"]
    assert github["provider_type"] == "github"
    assert github["enabled"] is True
    assert github["source"] == "env_var"


@pytest.mark.asyncio
async def test_github_bootstrap_uses_canonical_vault_path(
    bootstrapped_oauth_providers,
    populated_vault,
) -> None:
    github = bootstrapped_oauth_providers["github"]
    path = github["client_secret_ref"]
    assert path == "secret/data/musematic/dev/oauth/github/client-secret"
    if github["source"] == "env_var":
        versions = populated_vault(path)
        assert versions


@pytest.mark.asyncio
async def test_github_bootstrap_exposes_team_mapping_shape(bootstrapped_oauth_providers) -> None:
    github = bootstrapped_oauth_providers["github"]
    assert github["group_role_mapping"] == {"musematic-e2e/admins": "admin"}
    assert github["org_restrictions"] == ["musematic-e2e"]
