from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_add_google_role_mapping_via_admin_api(
    http_client,
    ensure_bootstrap_provider,
    platform_api_url,
) -> None:
    provider = await ensure_bootstrap_provider(
        http_client,
        "google",
        platform_api_url,
        group_role_mapping={"admins@company.com": "admin"},
    )

    assert provider["group_role_mapping"] == {"admins@company.com": "admin"}


@pytest.mark.asyncio
async def test_role_mapping_rejects_unknown_role(http_client, oauth_provider_payload) -> None:
    payload = oauth_provider_payload("google") | {
        "group_role_mapping": {"admins@company.com": "unknown_role"}
    }
    response = await http_client.put("/api/v1/admin/oauth/providers/google", json=payload)

    assert response.status_code in {400, 422}


@pytest.mark.asyncio
async def test_future_oauth_user_uses_mapping_default_shape(
    http_client,
    ensure_bootstrap_provider,
    platform_api_url,
) -> None:
    provider = await ensure_bootstrap_provider(
        http_client,
        "github",
        platform_api_url,
        group_role_mapping={"musematic-e2e/admins": "admin"},
        default_role="member",
    )

    assert provider["group_role_mapping"]["musematic-e2e/admins"] == "admin"
    assert provider["default_role"] == "member"


@pytest.mark.asyncio
async def test_existing_link_count_survives_mapping_change(
    http_client,
    ensure_bootstrap_provider,
    platform_api_url,
) -> None:
    await ensure_bootstrap_provider(
        http_client,
        "google",
        platform_api_url,
        group_role_mapping={"admins@company.com": "admin"},
    )
    before = await http_client.get("/api/v1/admin/oauth/providers/google/status")
    before.raise_for_status()

    await ensure_bootstrap_provider(
        http_client,
        "google",
        platform_api_url,
        group_role_mapping={"admins@company.com": "super_admin"},
    )
    after = await http_client.get("/api/v1/admin/oauth/providers/google/status")
    after.raise_for_status()

    assert after.json()["active_linked_users"] >= before.json()["active_linked_users"]
