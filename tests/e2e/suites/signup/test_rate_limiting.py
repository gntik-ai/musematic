from __future__ import annotations

import httpx
import pytest

from suites.signup.helpers import (
    PASSWORD,
    clear_signup_rate_limits,
    register_email_user,
    unique_email,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_signup_rate_limits_match_fr_588(
    platform_api_url: str,
    http_client,
) -> None:
    async with httpx.AsyncClient(
        base_url=platform_api_url,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        await clear_signup_rate_limits(http_client)
        repeated_email = unique_email("signup-rate-email")
        email_attempts = [
            await register_email_user(client, repeated_email, password=PASSWORD)
            for _ in range(4)
        ]
        assert [response.status_code for response in email_attempts[:3]] == [202, 202, 202]
        assert email_attempts[3].status_code == 429, email_attempts[3].text
        assert int(email_attempts[3].headers["Retry-After"]) > 0

        await clear_signup_rate_limits(http_client)
        ip_attempts = [
            await register_email_user(client, unique_email("signup-rate-ip"))
            for _ in range(6)
        ]
        assert [response.status_code for response in ip_attempts[:5]] == [202] * 5
        assert ip_attempts[5].status_code == 429, ip_attempts[5].text
        assert int(ip_attempts[5].headers["Retry-After"]) > 0
