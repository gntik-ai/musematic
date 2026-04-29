from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from journeys.helpers.narrative import journey_step
from suites.signup.helpers import (
    PASSWORD,
    auth_headers,
    clear_signup_rate_limits,
    complete_profile_if_required,
    configure_oauth_provider,
    decode_oauth_session,
    fetch_verification_token,
    oauth_authorize_flow,
    oauth_link_flow,
    register_email_user,
    register_verify_and_login,
    set_signup_mode,
    unique_email,
    unique_login,
)

JOURNEY_ID = "j19"
TIMEOUT_SECONDS = 300

# Cross-context inventory:
# - accounts
# - auth
# - audit
# - governance
# - notifications


@pytest.mark.journey
@pytest.mark.j19_new_user_signup
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j19_new_user_signup(
    platform_api_url: str,
    admin_client,
    mock_google_oidc: str,
    mock_github_oauth: str,
) -> None:
    with journey_step("Setup clears limits and enables OAuth providers"):
        await clear_signup_rate_limits(admin_client)
        await configure_oauth_provider(admin_client, platform_api_url, "google")
        await configure_oauth_provider(admin_client, platform_api_url, "github")

    async with httpx.AsyncClient(
        base_url=platform_api_url,
        follow_redirects=False,
        timeout=30.0,
    ) as client:
        with journey_step("US1 visitor starts email signup"):
            email = unique_email("j19-email")
            register = await register_email_user(client, email, display_name="J19 Email User")
            assert register.status_code == 202, register.text

        with journey_step("US1 visitor verifies email"):
            token = await fetch_verification_token(admin_client, email)
            verify = await client.post("/api/v1/accounts/verify-email", json={"token": token})
            assert verify.status_code == 200, verify.text
            assert verify.json()["status"] == "active"

        with journey_step("US1 verified visitor logs in and reads profile"):
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": PASSWORD},
            )
            assert login.status_code == 200, login.text
            profile = await client.get(
                "/api/v1/accounts/me",
                headers=auth_headers(login.json()["access_token"]),
            )
            assert profile.status_code == 200, profile.text
            assert profile.json()["email"] == email

        previous_mode: str | None = None
        try:
            with journey_step("US2 tenant switches to approval mode"):
                previous_mode = await set_signup_mode(admin_client, "admin_approval")
                await clear_signup_rate_limits(admin_client)

            with journey_step("US2 pending user verifies email but cannot log in"):
                approval_email = unique_email("j19-approval")
                register = await register_email_user(client, approval_email)
                assert register.status_code == 202, register.text
                token = await fetch_verification_token(admin_client, approval_email)
                verify = await client.post(
                    "/api/v1/accounts/verify-email",
                    json={"token": token},
                )
                assert verify.status_code == 200, verify.text
                approval_user_id = verify.json()["user_id"]
                assert verify.json()["status"] == "pending_approval"
                blocked = await client.post(
                    "/api/v1/auth/login",
                    json={"email": approval_email, "password": PASSWORD},
                )
                assert blocked.status_code == 403, blocked.text

            with journey_step("US2 admin approval unlocks the pending user"):
                approved = await admin_client.post(
                    f"/api/v1/accounts/{approval_user_id}/approve",
                    json={"reason": "J19 approval"},
                )
                assert approved.status_code == 200, approved.text
                login = await client.post(
                    "/api/v1/auth/login",
                    json={"email": approval_email, "password": PASSWORD},
                )
                assert login.status_code == 200, login.text
        finally:
            if previous_mode is not None:
                await set_signup_mode(admin_client, previous_mode)  # type: ignore[arg-type]
            await clear_signup_rate_limits(admin_client)

        with journey_step("US3 Google OAuth callback returns frontend fragment"):
            google_location = await oauth_authorize_flow(
                client,
                provider="google",
                mock_server=mock_google_oidc,
                login=unique_login("j19-google"),
            )
            assert google_location.startswith("/auth/oauth/google/callback#oauth_session=")
            google_payload = decode_oauth_session(google_location)
            assert google_payload["user"]["status"] == "pending_profile_completion"

        with journey_step("US3 Google OAuth profile completion activates account"):
            google_payload = await complete_profile_if_required(client, google_payload)
            assert google_payload["user"]["status"] == "active"

        with journey_step("US3 GitHub OAuth organisation restriction is configured"):
            await configure_oauth_provider(
                admin_client,
                platform_api_url,
                "github",
                org_restrictions=["musematic"],
            )

        try:
            with journey_step("US3 GitHub OAuth accepts an organisation member"):
                github_location = await oauth_authorize_flow(
                    client,
                    provider="github",
                    mock_server=mock_github_oauth,
                    login="signup-github-member",
                )
                assert github_location.startswith("/auth/oauth/github/callback#oauth_session=")

            with journey_step("US3 GitHub OAuth rejects an organisation outsider"):
                denied = await oauth_authorize_flow(
                    client,
                    provider="github",
                    mock_server=mock_github_oauth,
                    login="signup-github-outsider",
                )
                assert "org_not_allowed" in denied
        finally:
            await configure_oauth_provider(admin_client, platform_api_url, "github")

        with journey_step("US4 local account is created for link management"):
            link_email = unique_email("j19-link")
            link_login = await register_verify_and_login(client, admin_client, link_email)
            link_token = link_login["access_token"]
            assert link_token

        with journey_step("US4 authenticated user links GitHub provider"):
            github_link = await oauth_link_flow(
                client,
                provider="github",
                mock_server=mock_github_oauth,
                login=unique_login("j19-link-github"),
                access_token=link_token,
            )
            assert github_link == "/profile?message=oauth_linked"

        with journey_step("US4 linked providers list includes GitHub"):
            links = await client.get(
                "/api/v1/auth/oauth/links",
                headers=auth_headers(link_token),
            )
            assert links.status_code == 200, links.text
            assert "github" in {item["provider_type"] for item in links.json()["items"]}

        with journey_step("US5 recovery account signs in before linking"):
            recovery_email = unique_email("j19-recovery")
            recovery_login = await register_verify_and_login(
                client,
                admin_client,
                recovery_email,
            )
            recovery_provider_login = unique_login("j19-recovery-google")
            recovery_token = recovery_login["access_token"]

        with journey_step("US5 recovery account links Google provider"):
            linked = await oauth_link_flow(
                client,
                provider="google",
                mock_server=mock_google_oidc,
                login=recovery_provider_login,
                access_token=recovery_token,
            )
            assert linked == "/profile?message=oauth_linked"

        with journey_step("US5 linked OAuth provider recovers account access"):
            recovered_location = await oauth_authorize_flow(
                client,
                provider="google",
                mock_server=mock_google_oidc,
                login=recovery_provider_login,
                params={"intent": "recovery", "email": recovery_email},
            )
            recovered = decode_oauth_session(recovered_location)
            assert recovered["recovery_intent"] is True
            assert recovered["user"]["email"] == recovery_email

        with journey_step("US2 pending approval user can be seeded for rejection"):
            rejected_id = str(uuid4())
            rejected = await admin_client.post(
                "/api/v1/_e2e/users",
                json={
                    "id": rejected_id,
                    "email": unique_email("j19-rejected"),
                    "password": PASSWORD,
                    "display_name": "J19 Rejected User",
                    "roles": [],
                    "status": "pending_approval",
                },
            )
            assert rejected.status_code == 200, rejected.text

        with journey_step("US2 rejection remains terminal for a pending approval user"):
            decision = await admin_client.post(
                f"/api/v1/accounts/{rejected_id}/reject",
                json={"reason": "J19 rejection"},
            )
            assert decision.status_code == 200, decision.text
            assert decision.json()["status"] == "archived"
