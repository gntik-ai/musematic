from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_rotation_returns_204_with_empty_body(http_client, bootstrapped_oauth_providers) -> None:
    del bootstrapped_oauth_providers
    response = await http_client.post(
        "/api/v1/admin/oauth/providers/google/rotate-secret",
        json={"new_secret": "new-google-client-secret"},
    )

    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.asyncio
async def test_rotation_writes_new_vault_version(
    http_client,
    bootstrapped_oauth_providers,
    populated_vault,
) -> None:
    path = bootstrapped_oauth_providers["google"]["client_secret_ref"]
    before = populated_vault(path)
    response = await http_client.post(
        "/api/v1/admin/oauth/providers/google/rotate-secret",
        json={"new_secret": "rotated-google-client-secret"},
    )
    assert response.status_code == 204
    after = populated_vault(path)
    assert max(after) >= max(before)


@pytest.mark.asyncio
async def test_rotation_audit_entry_omits_plaintext_secret(
    http_client,
    bootstrapped_oauth_providers,
) -> None:
    del bootstrapped_oauth_providers
    response = await http_client.post(
        "/api/v1/admin/oauth/providers/github/rotate-secret",
        json={"new_secret": "rotated-github-client-secret"},
    )
    assert response.status_code == 204

    audit = await http_client.get("/api/v1/admin/oauth/audit", params={"provider_type": "github"})
    audit.raise_for_status()
    serialized = audit.text
    assert "rotated-github-client-secret" not in serialized
    assert "secret_rotated" in serialized


@pytest.mark.asyncio
async def test_rotation_keeps_provider_enabled_for_in_flight_oauth(
    http_client,
    bootstrapped_oauth_providers,
) -> None:
    del bootstrapped_oauth_providers
    response = await http_client.post(
        "/api/v1/admin/oauth/providers/google/rotate-secret",
        json={"new_secret": "dual-window-client-secret"},
    )
    assert response.status_code == 204
    public_list = await http_client.get("/api/v1/auth/oauth/providers")
    public_list.raise_for_status()
    providers = {item["provider_type"] for item in public_list.json()["providers"]}
    assert "google" in providers
