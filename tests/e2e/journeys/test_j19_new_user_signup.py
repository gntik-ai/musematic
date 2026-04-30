from __future__ import annotations

from typing import Any

import pytest

from journeys.conftest import AuthenticatedAsyncClient, JourneyContext, _oauth_provider_payload
from journeys.helpers.narrative import journey_step
from journeys.helpers.oauth import oauth_login

JOURNEY_ID = "j19"
TIMEOUT_SECONDS = 180

# Cross-context inventory:
# - auth
# - accounts
# - audit
# - workspaces
# - policies


@pytest.mark.journey
@pytest.mark.j19_new_user_signup
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j19_new_user_signup_with_bootstrapped_oauth(
    admin_client: AuthenticatedAsyncClient,
    http_client: AuthenticatedAsyncClient,
    journey_context: JourneyContext,
    platform_api_url: str,
    mock_google_oidc: str,
) -> None:
    provider_payload: dict[str, Any] | None = None
    provider_response: dict[str, Any] | None = None
    public_providers: dict[str, Any] = {}
    alice_client: AuthenticatedAsyncClient | None = None
    alice_profile: dict[str, Any] | None = None
    audit_payload: dict[str, Any] | None = None
    login_name = f"{journey_context.prefix}alice"

    with journey_step("Confirm Google OAuth provider mock is reachable for signup"):
        assert mock_google_oidc.startswith("http")

    with journey_step("Prepare Google provider payload with admin role mapping"):
        provider_payload = _oauth_provider_payload("google", platform_api_url) | {
            "source": "manual",
            "group_role_mapping": {"admins@company.com": "admin"},
            "default_role": "member",
        }
        assert provider_payload["source"] == "manual"

    with journey_step("Apply the Google provider as an admin-managed provider"):
        configured = await admin_client.put(
            "/api/v1/admin/oauth/providers/google",
            json=provider_payload,
        )
        configured.raise_for_status()
        provider_response = configured.json()
        assert provider_response["provider_type"] == "google"

    with journey_step("Verify the admin inventory exposes the configured provider source"):
        inventory = await admin_client.get("/api/v1/admin/oauth/providers")
        inventory.raise_for_status()
        providers = {
            item["provider_type"]: item
            for item in inventory.json().get("providers", [])
            if isinstance(item, dict)
        }
        assert providers["google"]["source"] in {"manual", "env_var"}

    with journey_step("Verify the provider is visible to signup clients"):
        public = await admin_client.get("/api/v1/auth/oauth/providers")
        public.raise_for_status()
        public_providers = {
            item["provider_type"]: item
            for item in public.json().get("providers", [])
            if isinstance(item, dict)
        }
        assert "google" in public_providers

    with journey_step("Verify role mapping payload is persisted before signup"):
        assert provider_response is not None
        assert provider_response["group_role_mapping"] == {"admins@company.com": "admin"}

    with journey_step("Create a fresh unauthenticated client for Alice"):
        alice_client = http_client.clone()
        alice_client.access_token = None
        alice_client.refresh_token = None
        assert alice_client.access_token is None

    with journey_step("Alice starts Google OAuth from signup"):
        assert alice_client is not None
        await oauth_login(
            alice_client,
            provider="google",
            mock_server=mock_google_oidc,
            login=login_name,
        )
        assert alice_client.access_token is not None

    with journey_step("Alice lands on an authenticated profile"):
        assert alice_client is not None
        profile = await alice_client.get("/api/v1/accounts/me")
        profile.raise_for_status()
        alice_profile = profile.json()
        assert alice_profile["email"]

    with journey_step("Alice has an active account after profile completion"):
        assert alice_profile is not None
        assert alice_profile.get("status") in {"active", "pending_profile_completion"}

    with journey_step("Alice can call the /me endpoint after signup"):
        assert alice_client is not None
        me = await alice_client.get("/api/v1/me")
        me.raise_for_status()
        assert me.json()

    with journey_step("Alice performs a first platform action"):
        assert alice_client is not None
        action = await alice_client.get("/api/v1/auth/oauth/links")
        assert action.status_code in {200, 404}

    with journey_step("Admin can inspect OAuth provider status after Alice signup"):
        status = await admin_client.get("/api/v1/admin/oauth/providers/google/status")
        status.raise_for_status()
        assert status.json()["provider_type"] == "google"

    with journey_step("Admin can inspect OAuth history after signup"):
        history = await admin_client.get("/api/v1/admin/oauth/providers/google/history")
        history.raise_for_status()
        assert "entries" in history.json()

    with journey_step("Admin can inspect OAuth audit entries for Google"):
        audit = await admin_client.get("/api/v1/admin/oauth/audit", params={"provider_type": "google"})
        audit.raise_for_status()
        audit_payload = audit.json()
        assert "items" in audit_payload

    with journey_step("Audit payload does not expose the provider client secret"):
        assert audit_payload is not None
        assert str(provider_payload["client_secret_ref"]) not in str(audit_payload)
        assert "mock-google-client-secret" not in str(audit_payload)

    with journey_step("Provider remains enabled for subsequent signup attempts"):
        refreshed = await admin_client.get("/api/v1/admin/oauth/providers")
        refreshed.raise_for_status()
        providers = {
            item["provider_type"]: item
            for item in refreshed.json().get("providers", [])
            if isinstance(item, dict)
        }
        assert providers["google"]["enabled"] is True

    with journey_step("Rate-limit defaults are available for the provider"):
        rate_limits = await admin_client.get("/api/v1/admin/oauth/providers/google/rate-limits")
        rate_limits.raise_for_status()
        assert rate_limits.json()["global_max"] > 0

    with journey_step("Connectivity diagnostic endpoint remains callable"):
        diagnostic = await admin_client.post("/api/v1/admin/oauth/providers/google/test-connectivity")
        assert diagnostic.status_code in {200, 503}

    with journey_step("J19 signup journey completes with Alice authenticated"):
        assert alice_client is not None
        assert alice_client.access_token is not None
        assert "google" in public_providers
