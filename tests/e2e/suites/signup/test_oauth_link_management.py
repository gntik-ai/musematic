from __future__ import annotations

import httpx
import pytest

from suites.signup.helpers import (
    PASSWORD,
    auth_headers,
    clear_signup_rate_limits,
    complete_profile_if_required,
    configure_oauth_provider,
    decode_oauth_session,
    oauth_authorize_flow,
    oauth_link_flow,
    register_verify_and_login,
    unique_email,
    unique_login,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_oauth_link_management_and_last_method_safety(
    platform_api_url: str,
    http_client,
    mock_google_oidc: str,
    mock_github_oauth: str,
) -> None:
    await clear_signup_rate_limits(http_client)
    await configure_oauth_provider(http_client, platform_api_url, "google")
    await configure_oauth_provider(http_client, platform_api_url, "github")

    async with httpx.AsyncClient(
        base_url=platform_api_url,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        local_email = unique_email("signup-link-local")
        login = await register_verify_and_login(client, http_client, local_email)
        access_token = login["access_token"]

        google_login = unique_login("signup-link-google")
        google_link = await oauth_link_flow(
            client,
            provider="google",
            mock_server=mock_google_oidc,
            login=google_login,
            access_token=access_token,
        )
        assert google_link == "/profile?message=oauth_linked"

        links = await client.get("/api/v1/auth/oauth/links", headers=auth_headers(access_token))
        assert links.status_code == 200, links.text
        assert {item["provider_type"] for item in links.json()["items"]} == {"google"}

        github_link = await oauth_link_flow(
            client,
            provider="github",
            mock_server=mock_github_oauth,
            login=unique_login("signup-link-github"),
            access_token=access_token,
        )
        assert github_link == "/profile?message=oauth_linked"

        unlink_google = await client.delete(
            "/api/v1/auth/oauth/google/link",
            headers=auth_headers(access_token),
        )
        assert unlink_google.status_code == 204, unlink_google.text

        conflict = await oauth_link_flow(
            client,
            provider="google",
            mock_server=mock_google_oidc,
            login=google_login,
            access_token=access_token,
        )
        assert conflict.startswith("/auth/oauth/google/callback?error=oauth_link_conflict")

        oauth_only_location = await oauth_authorize_flow(
            client,
            provider="google",
            mock_server=mock_google_oidc,
            login=unique_login("signup-oauth-only"),
        )
        oauth_only_payload = decode_oauth_session(oauth_only_location)
        oauth_only_payload = await complete_profile_if_required(client, oauth_only_payload)
        oauth_only_token = oauth_only_payload["token_pair"]["access_token"]
        assert oauth_only_payload["user"]["has_local_password"] is False

        unlink_only = await client.delete(
            "/api/v1/auth/oauth/google/link",
            headers=auth_headers(oauth_only_token),
        )
        assert unlink_only.status_code == 409, unlink_only.text
        assert unlink_only.json()["error"]["code"] == "OAUTH_LAST_AUTH_METHOD"
