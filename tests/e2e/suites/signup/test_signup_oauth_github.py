from __future__ import annotations

import httpx
import pytest

from suites.signup.helpers import (
    complete_profile_if_required,
    configure_oauth_provider,
    decode_oauth_session,
    oauth_audit_actions,
    oauth_authorize_flow,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_github_oauth_signup_honors_org_restriction(
    platform_api_url: str,
    http_client,
    mock_github_oauth: str,
) -> None:
    await configure_oauth_provider(
        http_client,
        platform_api_url,
        "github",
        org_restrictions=["musematic"],
    )

    async with httpx.AsyncClient(
        base_url=platform_api_url,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        location = await oauth_authorize_flow(
            client,
            provider="github",
            mock_server=mock_github_oauth,
            login="signup-github-member",
        )
        assert location.startswith("/auth/oauth/github/callback#oauth_session="), location
        payload = decode_oauth_session(location)
        payload = await complete_profile_if_required(client, payload)
        actions = await oauth_audit_actions(
            http_client,
            provider_type="github",
            user_id=payload["user"]["id"],
        )
        assert "sign_in_succeeded" in actions

        denied_location = await oauth_authorize_flow(
            client,
            provider="github",
            mock_server=mock_github_oauth,
            login="signup-github-outsider",
        )
        assert denied_location.startswith("/auth/oauth/github/callback?error=")
        assert "org_not_allowed" in denied_location
