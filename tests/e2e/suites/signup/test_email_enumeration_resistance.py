from __future__ import annotations

from typing import Any

import httpx
import pytest

from suites.signup.helpers import (
    clear_signup_rate_limits,
    register_email_user,
    unique_email,
)


def _canonical(response: httpx.Response) -> tuple[int, Any]:
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return response.status_code, body


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_signup_paths_preserve_email_enumeration_resistance(
    platform_api_url: str,
    http_client,
) -> None:
    await clear_signup_rate_limits(http_client)

    async with httpx.AsyncClient(
        base_url=platform_api_url,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        existing_email = unique_email("signup-enum-existing")
        new_email = unique_email("signup-enum-new")
        created = await register_email_user(client, existing_email)
        assert created.status_code == 202, created.text

        existing_register = await register_email_user(client, existing_email)
        new_register = await register_email_user(client, new_email)
        assert _canonical(existing_register) == _canonical(new_register)

        invalid_verify = await client.post(
            "/api/v1/accounts/verify-email",
            json={"token": "not-a-real-token"},
        )
        expired_token_response = await http_client.post(
            "/api/v1/_e2e/accounts/expired-verification-token",
            json={"email": existing_email},
        )
        assert expired_token_response.status_code == 200, expired_token_response.text
        expired_verify = await client.post(
            "/api/v1/accounts/verify-email",
            json={"token": expired_token_response.json()["token"]},
        )
        assert _canonical(invalid_verify) == _canonical(expired_verify)

        existing_resend = await client.post(
            "/api/v1/accounts/resend-verification",
            json={"email": existing_email},
        )
        unknown_resend = await client.post(
            "/api/v1/accounts/resend-verification",
            json={"email": unique_email("signup-enum-unknown")},
        )
        assert _canonical(existing_resend) == _canonical(unknown_resend)

        existing_links = await client.get(
            "/api/v1/auth/oauth/links",
            params={"email": existing_email},
        )
        unknown_links = await client.get(
            "/api/v1/auth/oauth/links",
            params={"email": unique_email("signup-enum-no-links")},
        )
        assert _canonical(existing_links) == _canonical(unknown_links)
