from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_reapplying_same_bootstrap_payload_is_idempotent(
    http_client,
    ensure_bootstrap_provider,
    platform_api_url,
) -> None:
    first = await ensure_bootstrap_provider(http_client, "google", platform_api_url)
    second = await ensure_bootstrap_provider(http_client, "google", platform_api_url)

    assert second["id"] == first["id"]
    assert second["client_secret_ref"] == first["client_secret_ref"]
    assert second["source"] == "env_var"


@pytest.mark.asyncio
async def test_manual_edit_is_preserved_until_force_update(
    http_client,
    ensure_bootstrap_provider,
    platform_api_url,
    oauth_provider_payload,
) -> None:
    manual_payload = oauth_provider_payload("google", source="manual") | {
        "display_name": "Manual Google",
        "client_id": "manual-client.apps.googleusercontent.com",
    }
    manual = await http_client.put("/api/v1/admin/oauth/providers/google", json=manual_payload)
    manual.raise_for_status()
    preserved = manual.json()

    assert preserved["source"] == "manual"
    assert preserved["display_name"] == "Manual Google"

    forced = await ensure_bootstrap_provider(
        http_client,
        "google",
        platform_api_url,
        display_name="E2E Google",
        client_id="e2e-google-client.apps.googleusercontent.com",
        source="env_var",
    )
    assert forced["source"] == "env_var"
    assert forced["display_name"] == "E2E Google"


@pytest.mark.asyncio
async def test_force_update_history_records_provider_change(
    http_client,
    ensure_bootstrap_provider,
    platform_api_url,
) -> None:
    await ensure_bootstrap_provider(http_client, "google", platform_api_url, source="env_var")
    history = await http_client.get("/api/v1/admin/oauth/providers/google/history")
    history.raise_for_status()
    actions = [item["action"] for item in history.json().get("entries", [])]
    assert "provider_configured" in actions or "config_reseeded" in actions


@pytest.mark.asyncio
async def test_force_update_on_empty_state_keeps_env_var_source(
    http_client,
    ensure_bootstrap_provider,
    platform_api_url,
) -> None:
    provider = await ensure_bootstrap_provider(
        http_client,
        "github",
        platform_api_url,
        source="env_var",
    )

    assert provider["source"] == "env_var"
    assert provider["enabled"] is True
