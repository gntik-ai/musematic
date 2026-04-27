from __future__ import annotations

import base64
import json
from platform.auth.dependencies_oauth import get_oauth_service, rate_limit_callback
from platform.auth.router_oauth import oauth_router
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.auth_support import role_claim


class OAuthRouterServiceStub:
    def __init__(self) -> None:
        self.created = True
        self.calls: list[tuple[str, tuple, dict]] = []

    async def list_public_providers(self):
        from platform.auth.schemas import (
            OAuthProviderPublic,
            OAuthProviderPublicListResponse,
            OAuthProviderType,
        )

        self.calls.append(("list_public_providers", (), {}))
        return OAuthProviderPublicListResponse(
            providers=[
                OAuthProviderPublic(provider_type=OAuthProviderType.GOOGLE, display_name="Google")
            ],
        )

    async def list_links(self, user_id):
        from platform.auth.schemas import OAuthLinkListResponse

        self.calls.append(("list_links", (user_id,), {}))
        return OAuthLinkListResponse(items=[])

    async def get_authorization_url(self, provider, link_for_user_id=None, dry_run=False):
        from platform.auth.schemas import OAuthAuthorizeResponse

        self.calls.append(
            (
                "get_authorization_url",
                (provider,),
                {"link_for_user_id": link_for_user_id, "dry_run": dry_run},
            )
        )
        return OAuthAuthorizeResponse(redirect_url=f"https://oauth.example.com/{provider}")

    async def handle_callback(self, **kwargs):
        self.calls.append(("handle_callback", (), kwargs))
        if kwargs["code"] == "link-code":
            return {"linked": True, "link": {"provider_type": "google"}}
        return {
            "token_pair": SimpleNamespace(
                access_token="access-token", refresh_token="refresh-token", expires_in=900
            ),
            "user": {"id": "user-1", "email": "alex@example.com"},
        }

    async def list_admin_providers(self):
        from platform.auth.schemas import OAuthProviderAdminListResponse

        self.calls.append(("list_admin_providers", (), {}))
        return OAuthProviderAdminListResponse(providers=[])

    async def upsert_provider(self, **kwargs):
        from datetime import UTC, datetime
        from platform.auth.schemas import OAuthProviderAdminResponse, OAuthProviderType

        self.calls.append(("upsert_provider", (), kwargs))
        return OAuthProviderAdminResponse(
            id=uuid4(),
            provider_type=OAuthProviderType.GOOGLE,
            display_name=kwargs["display_name"],
            enabled=kwargs["enabled"],
            client_id=kwargs["client_id"],
            client_secret_ref=kwargs["client_secret_ref"],
            redirect_uri=kwargs["redirect_uri"],
            scopes=kwargs["scopes"],
            domain_restrictions=kwargs["domain_restrictions"],
            org_restrictions=kwargs["org_restrictions"],
            group_role_mapping=kwargs["group_role_mapping"],
            default_role=kwargs["default_role"],
            require_mfa=kwargs["require_mfa"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ), self.created

    async def list_audit_entries(self, **kwargs):
        from platform.auth.schemas import OAuthAuditEntryListResponse

        self.calls.append(("list_audit_entries", (), kwargs))
        return OAuthAuditEntryListResponse(items=[])

    async def unlink_account(self, user_id, provider):
        self.calls.append(("unlink_account", (user_id, provider), {}))


def _app(service: OAuthRouterServiceStub) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.dependency_overrides[get_oauth_service] = lambda: service
    app.dependency_overrides[rate_limit_callback] = lambda: None
    app.include_router(oauth_router)
    return app


def _admin_user() -> dict[str, object]:
    return {"sub": str(uuid4()), "roles": [role_claim("platform_admin")]}


def _member_user() -> dict[str, object]:
    return {"sub": str(uuid4()), "roles": [role_claim("workspace_member")]}


@pytest.mark.asyncio
async def test_oauth_router_callback_redirects_with_fragment_and_cookie() -> None:
    service = OAuthRouterServiceStub()
    app = _app(service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/auth/oauth/google/callback?code=oauth-code&state=signed-state",
            headers={"origin": "https://app.example.com"},
        )

    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "https://app.example.com/auth/oauth/google/callback#oauth_session="
    )
    assert "session=access-token" in response.headers.get("set-cookie", "")
    fragment = response.headers["location"].split("#oauth_session=", 1)[1]
    payload = json.loads(base64.urlsafe_b64decode(fragment + "==").decode("utf-8"))
    assert payload["token_pair"]["access_token"] == "access-token"


@pytest.mark.asyncio
async def test_oauth_router_callback_redirects_link_flow_and_errors() -> None:
    service = OAuthRouterServiceStub()
    app = _app(service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        link_response = await client.get(
            "/api/v1/auth/oauth/google/callback?code=link-code&state=signed-state",
            headers={"origin": "https://app.example.com"},
        )
        error_response = await client.get(
            "/api/v1/auth/oauth/google/callback?error=access_denied",
            headers={"origin": "https://app.example.com"},
        )

    assert (
        link_response.headers["location"] == "https://app.example.com/profile?message=oauth_linked"
    )
    assert (
        error_response.headers["location"]
        == "https://app.example.com/auth/oauth/google/callback?error=access_denied"
    )


@pytest.mark.asyncio
async def test_oauth_router_admin_and_link_endpoints_delegate() -> None:
    service = OAuthRouterServiceStub()
    app = _app(service)
    app.dependency_overrides[get_current_user] = _admin_user

    payload = {
        "display_name": "Google Workspace",
        "enabled": True,
        "client_id": "google-client",
        "client_secret_ref": "plain:secret",
        "redirect_uri": "https://app.example.com/callback",
        "scopes": ["openid", "email"],
        "domain_restrictions": ["example.com"],
        "org_restrictions": [],
        "group_role_mapping": {"admins": "platform_admin"},
        "default_role": "viewer",
        "require_mfa": False,
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        providers = await client.get("/api/v1/auth/oauth/providers")
        links = await client.get("/api/v1/auth/oauth/links")
        authorize = await client.get("/api/v1/auth/oauth/google/authorize")
        link_begin = await client.post("/api/v1/auth/oauth/google/link")
        unlink = await client.delete("/api/v1/auth/oauth/google/link")
        admin_list = await client.get("/api/v1/admin/oauth/providers")
        admin_upsert = await client.put("/api/v1/admin/oauth/providers/google", json=payload)
        connectivity = await client.post(
            "/api/v1/admin/oauth-providers/google/test-connectivity"
        )
        audit = await client.get("/api/v1/admin/oauth/audit?limit=10")

    assert providers.status_code == 200
    assert links.status_code == 200
    assert authorize.json()["redirect_url"].endswith("/google")
    assert link_begin.status_code == 200
    assert unlink.status_code == 204
    assert admin_list.status_code == 200
    assert admin_upsert.status_code == 201
    assert connectivity.status_code == 200
    assert connectivity.json()["auth_url_returned"] is True
    assert audit.status_code == 200
    assert {name for name, _, _ in service.calls} >= {
        "list_public_providers",
        "list_links",
        "get_authorization_url",
        "unlink_account",
        "list_admin_providers",
        "upsert_provider",
        "list_audit_entries",
    }


@pytest.mark.asyncio
async def test_oauth_router_rejects_non_admin_for_admin_endpoints() -> None:
    service = OAuthRouterServiceStub()
    app = _app(service)
    app.dependency_overrides[get_current_user] = _member_user

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/admin/oauth/providers")

    assert response.status_code == 403
