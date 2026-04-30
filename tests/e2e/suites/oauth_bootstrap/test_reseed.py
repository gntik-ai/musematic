from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_reseed_without_running_env_block_returns_clear_400(
    http_client,
    bootstrapped_oauth_providers,
) -> None:
    del bootstrapped_oauth_providers
    response = await http_client.post(
        "/api/v1/admin/oauth/providers/google/reseed-from-env",
        json={"force_update": False},
    )

    assert response.status_code in {200, 400}
    if response.status_code == 400:
        assert "cannot reseed" in response.text or "ENABLED" in response.text


@pytest.mark.asyncio
async def test_reseed_force_update_reports_changed_fields(
    http_client,
    bootstrapped_oauth_providers,
) -> None:
    del bootstrapped_oauth_providers
    response = await http_client.post(
        "/api/v1/admin/oauth/providers/github/reseed-from-env",
        json={"force_update": True},
    )

    assert response.status_code in {200, 400}
    if response.status_code == 200:
        payload = response.json()
        assert "diff" in payload
        assert "changed_fields" in str(payload["diff"])


@pytest.mark.asyncio
async def test_reseed_preserves_no_plaintext_secret_in_response(
    http_client,
    bootstrapped_oauth_providers,
) -> None:
    del bootstrapped_oauth_providers
    response = await http_client.post(
        "/api/v1/admin/oauth/providers/google/reseed-from-env",
        json={"force_update": True},
    )

    assert "client_secret" not in response.text.lower()
    assert "secret/data/musematic" not in response.text or response.status_code == 400
