from __future__ import annotations

import httpx
import pytest

from suites.signup.helpers import (
    complete_profile_if_required,
    configure_oauth_provider,
    decode_oauth_session,
    oauth_audit_actions,
    oauth_authorize_flow,
    unique_login,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_google_oauth_signup_profile_completion_and_domain_restriction(
    platform_api_url: str,
    http_client,
    mock_google_oidc: str,
) -> None:
    async with httpx.AsyncClient(
        base_url=platform_api_url,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        await configure_oauth_provider(
            http_client,
            platform_api_url,
            "google",
            domain_restrictions=["e2e.test"],
        )
        location = await oauth_authorize_flow(
            client,
            provider="google",
            mock_server=mock_google_oidc,
            login=unique_login("signup-google"),
        )
        assert location.startswith("/auth/oauth/google/callback#oauth_session="), location
        payload = decode_oauth_session(location)
        assert payload["user"]["status"] == "pending_profile_completion"

        payload = await complete_profile_if_required(client, payload)
        actions = await oauth_audit_actions(
            http_client,
            provider_type="google",
            user_id=payload["user"]["id"],
        )
        assert {"user_provisioned", "sign_in_succeeded"}.issubset(actions)

        await configure_oauth_provider(
            http_client,
            platform_api_url,
            "google",
            domain_restrictions=["example.com"],
        )
        denied_location = await oauth_authorize_flow(
            client,
            provider="google",
            mock_server=mock_google_oidc,
            login=unique_login("signup-google-denied"),
        )
        assert denied_location.startswith("/auth/oauth/google/callback?error=")
        assert "domain_not_allowed" in denied_location
