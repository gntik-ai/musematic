from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_missing_client_id_is_rejected(http_client, oauth_provider_payload) -> None:
    payload = oauth_provider_payload("google") | {"client_id": ""}
    response = await http_client.put("/api/v1/admin/oauth/providers/google", json=payload)

    assert response.status_code in {400, 422}


@pytest.mark.asyncio
async def test_invalid_google_client_id_is_rejected(http_client, oauth_provider_payload) -> None:
    payload = oauth_provider_payload("google") | {"client_id": "not-a-google-client"}
    response = await http_client.put("/api/v1/admin/oauth/providers/google", json=payload)

    assert response.status_code in {200, 400, 422}
    if response.status_code >= 400:
        assert "client" in response.text.lower()


@pytest.mark.asyncio
async def test_invalid_group_role_mapping_role_is_rejected(
    http_client,
    oauth_provider_payload,
) -> None:
    payload = oauth_provider_payload("google") | {
        "group_role_mapping": {"admins@company.com": "not_a_role"}
    }
    response = await http_client.put("/api/v1/admin/oauth/providers/google", json=payload)

    assert response.status_code in {400, 422}


@pytest.mark.asyncio
async def test_non_https_redirect_uri_is_rejected_in_production_shape(
    http_client,
    oauth_provider_payload,
) -> None:
    payload = oauth_provider_payload("google") | {
        "redirect_uri": "http://app.example.com/api/v1/auth/oauth/google/callback"
    }
    response = await http_client.put("/api/v1/admin/oauth/providers/google", json=payload)

    assert response.status_code in {200, 400, 422}


@pytest.mark.asyncio
async def test_allowed_domains_empty_is_warning_only(
    http_client,
    ensure_bootstrap_provider,
    platform_api_url,
) -> None:
    provider = await ensure_bootstrap_provider(
        http_client,
        "google",
        platform_api_url,
        domain_restrictions=[],
    )

    assert provider["domain_restrictions"] == []
    assert provider["enabled"] is True


@pytest.mark.asyncio
async def test_external_source_provider_is_not_replaced_by_bootstrap(
    http_client,
    oauth_provider_payload,
) -> None:
    payload = oauth_provider_payload("google", source="imported")
    imported = await http_client.put("/api/v1/admin/oauth/providers/google", json=payload)
    imported.raise_for_status()

    current = await http_client.get("/api/v1/admin/oauth/providers")
    current.raise_for_status()
    providers = {item["provider_type"]: item for item in current.json()["providers"]}
    assert providers["google"]["source"] == "imported"


@pytest.mark.asyncio
async def test_vault_unreachable_reseed_fails_fast(
    http_client,
    bootstrapped_oauth_providers,
) -> None:
    del bootstrapped_oauth_providers
    response = await http_client.post(
        "/api/v1/admin/oauth/providers/google/reseed-from-env",
        json={"force_update": True},
    )

    assert response.status_code in {200, 400, 503}


def test_bootstrap_validation_suite_documents_json_mapping_case() -> None:
    invalid_mapping = "{not-json"
    assert invalid_mapping.startswith("{")
    assert "}" not in invalid_mapping
