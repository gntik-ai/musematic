from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from uuid import uuid4

import httpx
import pytest

PASSWORD = "SignupPass1!23"
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def unique_email(prefix: str, domain: str = "e2e.test") -> str:
    return f"{prefix}-{uuid4().hex[:10]}@{domain}"


def unique_login(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def clear_signup_rate_limits(admin_client: Any) -> None:
    response = await admin_client.delete("/api/v1/_e2e/accounts/signup-rate-limits")
    assert response.status_code == 204, response.text


async def set_signup_mode(
    admin_client: Any,
    mode: Literal["open", "invite_only", "admin_approval"],
) -> str:
    response = await admin_client.put(
        "/api/v1/_e2e/accounts/signup-mode",
        json={"signup_mode": mode},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["previous"])


async def register_email_user(
    client: httpx.AsyncClient,
    email: str,
    *,
    display_name: str = "Signup E2E User",
    password: str = PASSWORD,
) -> httpx.Response:
    return await client.post(
        "/api/v1/accounts/register",
        json={"email": email, "display_name": display_name, "password": password},
    )


async def fetch_verification_token(admin_client: Any, email: str) -> str:
    for _ in range(30):
        response = await admin_client.get(
            "/api/v1/_e2e/accounts/verification-token",
            params={"email": email},
        )
        if response.status_code == 404:
            pytest.skip("FEATURE_E2E_MODE is required for verification-token capture")
        assert response.status_code == 200, response.text
        token = response.json().get("token")
        if isinstance(token, str) and token:
            return token
        await asyncio.sleep(0.5)
    raise AssertionError(f"verification token for {email} was not captured")


async def register_verify_and_login(
    client: httpx.AsyncClient,
    admin_client: Any,
    email: str,
    *,
    password: str = PASSWORD,
) -> dict[str, Any]:
    register = await register_email_user(client, email, password=password)
    assert register.status_code == 202, register.text
    token = await fetch_verification_token(admin_client, email)
    verify = await client.post("/api/v1/accounts/verify-email", json={"token": token})
    assert verify.status_code == 200, verify.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return login.json()


def oauth_provider_payload(
    provider: Literal["google", "github"],
    platform_api_url: str,
    *,
    domain_restrictions: list[str] | None = None,
    org_restrictions: list[str] | None = None,
    default_role: str = "workspace_member",
) -> dict[str, Any]:
    if provider == "google":
        return {
            "display_name": "Mock Google",
            "enabled": True,
            "client_id": "mock-google-client-id",
            "client_secret_ref": "plain:mock-google-client-secret",
            "redirect_uri": f"{platform_api_url.rstrip('/')}/api/v1/auth/oauth/google/callback",
            "scopes": ["openid", "email", "profile"],
            "domain_restrictions": domain_restrictions or [],
            "org_restrictions": [],
            "group_role_mapping": {},
            "default_role": default_role,
            "require_mfa": False,
        }
    return {
        "display_name": "Mock GitHub",
        "enabled": True,
        "client_id": "mock-github-client-id",
        "client_secret_ref": "plain:mock-github-client-secret",
        "redirect_uri": f"{platform_api_url.rstrip('/')}/api/v1/auth/oauth/github/callback",
        "scopes": ["read:user", "user:email"],
        "domain_restrictions": [],
        "org_restrictions": org_restrictions or [],
        "group_role_mapping": {},
        "default_role": default_role,
        "require_mfa": False,
    }


async def configure_oauth_provider(
    admin_client: Any,
    platform_api_url: str,
    provider: Literal["google", "github"],
    *,
    domain_restrictions: list[str] | None = None,
    org_restrictions: list[str] | None = None,
    default_role: str = "workspace_member",
) -> None:
    response = await admin_client.put(
        f"/api/v1/admin/oauth/providers/{provider}",
        json=oauth_provider_payload(
            provider,
            platform_api_url,
            domain_restrictions=domain_restrictions,
            org_restrictions=org_restrictions,
            default_role=default_role,
        ),
    )
    assert response.status_code in {200, 201}, response.text


def mock_authorize_url(provider: str, mock_server: str, redirect_url: str, login: str) -> str:
    parsed = urlparse(redirect_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if provider == "google":
        query["login_hint"] = [login]
        path = "/authorize"
    else:
        query["login"] = [login]
        path = "/login/oauth/authorize"
    target = urlparse(mock_server)
    return urlunparse(
        (target.scheme, target.netloc, path, "", urlencode(query, doseq=True), "")
    )


async def complete_oauth_redirect(
    client: httpx.AsyncClient,
    *,
    provider: Literal["google", "github"],
    mock_server: str,
    redirect_url: str,
    login: str,
) -> str:
    mock_response = await client.get(
        mock_authorize_url(provider, mock_server, redirect_url, login),
        follow_redirects=False,
    )
    if mock_response.status_code not in REDIRECT_STATUSES:
        mock_response.raise_for_status()
    callback_url = mock_response.headers.get("location")
    assert callback_url, f"{provider} mock authorize response missing redirect"

    callback = await client.get(callback_url, follow_redirects=False)
    if callback.status_code not in REDIRECT_STATUSES:
        callback.raise_for_status()
    location = callback.headers.get("location")
    assert location, f"{provider} callback response missing redirect"
    return location


async def oauth_authorize_flow(
    client: httpx.AsyncClient,
    *,
    provider: Literal["google", "github"],
    mock_server: str,
    login: str,
    params: dict[str, str] | None = None,
) -> str:
    authorize = await client.get(
        f"/api/v1/auth/oauth/{provider}/authorize",
        params=params,
    )
    assert authorize.status_code == 200, authorize.text
    return await complete_oauth_redirect(
        client,
        provider=provider,
        mock_server=mock_server,
        redirect_url=authorize.json()["redirect_url"],
        login=login,
    )


async def oauth_link_flow(
    client: httpx.AsyncClient,
    *,
    provider: Literal["google", "github"],
    mock_server: str,
    login: str,
    access_token: str,
) -> str:
    authorize = await client.post(
        f"/api/v1/auth/oauth/{provider}/link",
        headers=auth_headers(access_token),
    )
    assert authorize.status_code == 200, authorize.text
    return await complete_oauth_redirect(
        client,
        provider=provider,
        mock_server=mock_server,
        redirect_url=authorize.json()["redirect_url"],
        login=login,
    )


def decode_oauth_session(location: str) -> dict[str, Any]:
    fragment = location.split("#oauth_session=", 1)
    assert len(fragment) == 2, f"OAuth redirect did not include session fragment: {location}"
    token = fragment[1]
    padding = "=" * (-len(token) % 4)
    decoded = base64.urlsafe_b64decode((token + padding).encode("utf-8")).decode("utf-8")
    payload = json.loads(decoded)
    assert isinstance(payload, dict)
    return payload


async def complete_profile_if_required(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    *,
    display_name: str = "Signup OAuth User",
) -> dict[str, Any]:
    if payload.get("user", {}).get("status") != "pending_profile_completion":
        return payload
    token_pair = payload["token_pair"]
    response = await client.patch(
        "/api/v1/accounts/me",
        headers=auth_headers(str(token_pair["access_token"])),
        json={"display_name": display_name, "locale": "en", "timezone": "UTC"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    payload["user"]["status"] = "active"
    return payload


async def oauth_audit_actions(
    admin_client: Any,
    *,
    provider_type: Literal["google", "github"],
    user_id: str,
) -> set[str]:
    response = await admin_client.get(
        "/api/v1/admin/oauth/audit",
        params={"provider_type": provider_type, "user_id": user_id, "limit": 50},
    )
    assert response.status_code == 200, response.text
    return {str(item["action"]) for item in response.json().get("items", [])}
