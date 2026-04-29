from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from suites.signup.helpers import (
    PASSWORD,
    clear_signup_rate_limits,
    fetch_verification_token,
    register_email_user,
    set_signup_mode,
    unique_email,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_signup_approval_required_blocks_then_allows_login(
    platform_api_url: str,
    http_client,
) -> None:
    previous_mode = await set_signup_mode(http_client, "admin_approval")
    await clear_signup_rate_limits(http_client)
    email = unique_email("signup-approval")

    try:
        async with httpx.AsyncClient(
            base_url=platform_api_url,
            follow_redirects=False,
            timeout=30.0,
        ) as client:
            register = await register_email_user(client, email)
            assert register.status_code == 202, register.text
            token = await fetch_verification_token(http_client, email)

            verify = await client.post("/api/v1/accounts/verify-email", json={"token": token})
            assert verify.status_code == 200, verify.text
            user_id = verify.json()["user_id"]
            assert verify.json()["status"] == "pending_approval"

            blocked = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": PASSWORD},
            )
            assert blocked.status_code == 403, blocked.text
            error = blocked.json()["error"]
            assert error["code"] == "account_pending_approval"
            assert error["details"]["redirect_to"] == "/waiting-approval"

            pending = await http_client.get("/api/v1/accounts/pending-approvals")
            assert pending.status_code == 200, pending.text
            assert user_id in {item["user_id"] for item in pending.json()["items"]}

            approved = await http_client.post(
                f"/api/v1/accounts/{user_id}/approve",
                json={"reason": "E2E approval"},
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == "active"

            login = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": PASSWORD},
            )
            assert login.status_code == 200, login.text

            rejected_user_id = str(uuid4())
            rejected_email = unique_email("signup-rejected")
            provision = await http_client.post(
                "/api/v1/_e2e/users",
                json={
                    "id": rejected_user_id,
                    "email": rejected_email,
                    "password": PASSWORD,
                    "display_name": "Rejected Signup User",
                    "status": "pending_approval",
                    "roles": [],
                },
            )
            assert provision.status_code == 200, provision.text

            rejected = await http_client.post(
                f"/api/v1/accounts/{rejected_user_id}/reject",
                json={"reason": "E2E rejection"},
            )
            assert rejected.status_code == 200, rejected.text
            assert rejected.json()["status"] == "archived"
    finally:
        await set_signup_mode(http_client, previous_mode)  # type: ignore[arg-type]
        await clear_signup_rate_limits(http_client)
