from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from suites.signup.helpers import (
    configure_oauth_provider,
    oauth_authorize_flow,
    unique_login,
)


ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_oauth_callback_uses_fragment_and_frontend_clears_history(
    platform_api_url: str,
    http_client,
    mock_google_oidc: str,
) -> None:
    await configure_oauth_provider(http_client, platform_api_url, "google")

    async with httpx.AsyncClient(
        base_url=platform_api_url,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        location = await oauth_authorize_flow(
            client,
            provider="google",
            mock_server=mock_google_oidc,
            login=unique_login("signup-fragment"),
        )

    assert "#oauth_session=" in location
    assert "access_token=" not in location
    assert "refresh_token=" not in location

    handler = (
        ROOT / "apps/web/components/features/auth/OAuthCallbackHandler.tsx"
    ).read_text(encoding="utf-8")
    assert 'window.history.replaceState(null, "", window.location.pathname)' in handler
