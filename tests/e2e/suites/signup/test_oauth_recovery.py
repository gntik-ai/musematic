from __future__ import annotations

import httpx
import pytest

from suites.signup.helpers import (
    auth_headers,
    clear_signup_rate_limits,
    configure_oauth_provider,
    decode_oauth_session,
    oauth_audit_actions,
    oauth_authorize_flow,
    oauth_link_flow,
    register_verify_and_login,
    unique_email,
    unique_login,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_oauth_recovery_requires_existing_link_and_records_audit(
    platform_api_url: str,
    http_client,
    mock_google_oidc: str,
) -> None:
    await clear_signup_rate_limits(http_client)
    await configure_oauth_provider(http_client, platform_api_url, "google")

    async with httpx.AsyncClient(
        base_url=platform_api_url,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        linked_email = unique_email("signup-recovery-linked")
        login = await register_verify_and_login(client, http_client, linked_email)
        access_token = login["access_token"]
        google_login = unique_login("signup-recovery-google")

        link_location = await oauth_link_flow(
            client,
            provider="google",
            mock_server=mock_google_oidc,
            login=google_login,
            access_token=access_token,
        )
        assert link_location == "/profile?message=oauth_linked"

        public_links = await client.get(
            "/api/v1/auth/oauth/links",
            params={"email": linked_email},
        )
        assert public_links.status_code == 200, public_links.text
        assert [item["provider_type"] for item in public_links.json()["items"]] == ["google"]

        recovery_location = await oauth_authorize_flow(
            client,
            provider="google",
            mock_server=mock_google_oidc,
            login=google_login,
            params={"intent": "recovery", "email": linked_email},
        )
        payload = decode_oauth_session(recovery_location)
        assert payload["recovery_intent"] is True

        profile = await client.get(
            "/api/v1/accounts/me",
            headers=auth_headers(payload["token_pair"]["access_token"]),
        )
        assert profile.status_code == 200, profile.text
        assert profile.json()["email"] == linked_email

        actions = await oauth_audit_actions(
            http_client,
            provider_type="google",
            user_id=payload["user"]["id"],
        )
        assert "password_reset_via_oauth_recovery" in actions

        unlinked_email = unique_email("signup-recovery-unlinked")
        await register_verify_and_login(client, http_client, unlinked_email)
        unlinked_links = await client.get(
            "/api/v1/auth/oauth/links",
            params={"email": unlinked_email},
        )
        assert unlinked_links.status_code == 200, unlinked_links.text
        assert unlinked_links.json()["items"] == []
