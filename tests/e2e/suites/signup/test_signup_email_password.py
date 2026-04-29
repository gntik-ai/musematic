from __future__ import annotations

import httpx
import pytest

from suites.signup.helpers import (
    PASSWORD,
    auth_headers,
    clear_signup_rate_limits,
    fetch_verification_token,
    register_email_user,
    unique_email,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_email_password_signup_verifies_and_logs_in(
    platform_api_url: str,
    http_client,
) -> None:
    await clear_signup_rate_limits(http_client)
    email = unique_email("signup-email")

    async with httpx.AsyncClient(
        base_url=platform_api_url,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        register = await register_email_user(client, email)
        assert register.status_code == 202, register.text
        assert "verification email" in register.json()["message"]

        premature_login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": PASSWORD},
        )
        assert premature_login.status_code == 401, premature_login.text

        token = await fetch_verification_token(http_client, email)
        verify = await client.post("/api/v1/accounts/verify-email", json={"token": token})
        assert verify.status_code == 200, verify.text
        assert verify.json()["status"] == "active"

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        access_token = login.json()["access_token"]

        profile = await client.get(
            "/api/v1/accounts/me",
            headers=auth_headers(access_token),
        )
        assert profile.status_code == 200, profile.text
        assert profile.json()["email"] == email
        assert profile.json()["status"] == "active"
