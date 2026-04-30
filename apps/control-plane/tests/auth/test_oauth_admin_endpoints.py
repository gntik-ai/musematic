from __future__ import annotations

from datetime import UTC, datetime
from platform.auth.dependencies_oauth import get_oauth_service, rate_limit_callback
from platform.auth.exceptions import OAuthBootstrapEnvironmentError
from platform.auth.router_oauth import oauth_router
from platform.auth.schemas import (
    OAuthConfigReseedResponse,
    OAuthHistoryEntryResponse,
    OAuthHistoryListResponse,
    OAuthProviderSourceType,
    OAuthProviderStatusResponse,
    OAuthProviderType,
    OAuthRateLimitConfig,
)
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.auth_support import role_claim


class AdminOAuthServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.reseed_error: OAuthBootstrapEnvironmentError | None = None

    async def rotate_secret(self, provider: str, new_secret: str, actor_id) -> None:
        self.calls.append(("rotate_secret", (provider, new_secret), {"actor_id": actor_id}))

    async def reseed_from_env(
        self,
        provider: str,
        *,
        force_update: bool,
        actor_id,
        settings: PlatformSettings,
        secret_provider,
    ) -> OAuthConfigReseedResponse:
        del settings, secret_provider
        if self.reseed_error is not None:
            raise self.reseed_error
        self.calls.append(
            (
                "reseed_from_env",
                (provider,),
                {"force_update": force_update, "actor_id": actor_id},
            )
        )
        return OAuthConfigReseedResponse(
            diff={"status": "updated", "changed_fields": {"force_update": force_update}}
        )

    async def get_history(
        self,
        provider: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> OAuthHistoryListResponse:
        self.calls.append(("get_history", (provider,), {"limit": limit, "cursor": cursor}))
        return OAuthHistoryListResponse(
            entries=[
                OAuthHistoryEntryResponse(
                    timestamp=datetime.now(UTC),
                    admin_id=uuid4(),
                    action="provider_configured",
                    before={"enabled": False},
                    after={"enabled": True},
                )
            ],
            next_cursor="2026-04-30T00:00:00+00:00",
        )

    async def get_status(self, provider: str) -> OAuthProviderStatusResponse:
        self.calls.append(("get_status", (provider,), {}))
        return OAuthProviderStatusResponse(
            provider_type=OAuthProviderType(provider),
            source=OAuthProviderSourceType.ENV_VAR,
            last_successful_auth_at=None,
            auth_count_24h=1,
            auth_count_7d=2,
            auth_count_30d=3,
            active_linked_users=4,
        )

    async def get_rate_limits(self, provider: str) -> OAuthRateLimitConfig:
        self.calls.append(("get_rate_limits", (provider,), {}))
        return OAuthRateLimitConfig(
            per_ip_max=10,
            per_ip_window=60,
            per_user_max=8,
            per_user_window=60,
            global_max=100,
            global_window=60,
        )

    async def update_rate_limits(
        self,
        provider: str,
        body: OAuthRateLimitConfig,
        actor_id,
    ) -> OAuthRateLimitConfig:
        self.calls.append(("update_rate_limits", (provider, body), {"actor_id": actor_id}))
        return body


class SecretProviderStub:
    pass


def _admin_user() -> dict[str, object]:
    return {"sub": str(uuid4()), "roles": [role_claim("platform_admin")]}


def _member_user() -> dict[str, object]:
    return {"sub": str(uuid4()), "roles": [role_claim("member")]}


def _app(service: AdminOAuthServiceStub, current_user) -> FastAPI:
    app = FastAPI()
    app.state.settings = PlatformSettings()
    app.state.secret_provider = SecretProviderStub()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.dependency_overrides[get_oauth_service] = lambda: service
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[rate_limit_callback] = lambda: None
    app.include_router(oauth_router)
    return app


@pytest.mark.asyncio
async def test_rotate_secret_returns_204_empty_body_and_delegates() -> None:
    service = AdminOAuthServiceStub()
    app = _app(service, _admin_user)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/admin/oauth-providers/google/rotate-secret",
            json={"new_secret": "rotated-secret"},
        )

    assert response.status_code == 204
    assert response.content == b""
    assert service.calls[0][0] == "rotate_secret"
    assert service.calls[0][1] == ("google", "rotated-secret")


@pytest.mark.asyncio
async def test_reseed_history_status_and_rate_limit_endpoints_delegate() -> None:
    service = AdminOAuthServiceStub()
    app = _app(service, _admin_user)
    rate_limit_payload = {
        "per_ip_max": 20,
        "per_ip_window": 60,
        "per_user_max": 15,
        "per_user_window": 60,
        "global_max": 200,
        "global_window": 60,
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        reseed = await client.post(
            "/api/v1/admin/oauth-providers/google/reseed-from-env",
            json={"force_update": True},
        )
        history = await client.get(
            "/api/v1/admin/oauth-providers/google/history"
            "?limit=25&cursor=2026-04-01T00:00:00%2B00:00"
        )
        status = await client.get("/api/v1/admin/oauth-providers/google/status")
        rate_limits = await client.get("/api/v1/admin/oauth-providers/google/rate-limits")
        rate_limit_update = await client.put(
            "/api/v1/admin/oauth-providers/google/rate-limits",
            json=rate_limit_payload,
        )

    assert reseed.status_code == 200
    assert reseed.json()["diff"]["changed_fields"]["force_update"] is True
    assert history.status_code == 200
    assert history.json()["entries"][0]["before"] == {"enabled": False}
    assert history.json()["next_cursor"] == "2026-04-30T00:00:00+00:00"
    assert status.json()["active_linked_users"] == 4
    assert rate_limits.json()["per_user_max"] == 8
    assert rate_limit_update.json() == rate_limit_payload
    assert {call[0] for call in service.calls} >= {
        "reseed_from_env",
        "get_history",
        "get_status",
        "get_rate_limits",
        "update_rate_limits",
    }


@pytest.mark.asyncio
async def test_reseed_without_running_env_returns_400() -> None:
    service = AdminOAuthServiceStub()
    service.reseed_error = OAuthBootstrapEnvironmentError("google")
    app = _app(service, _admin_user)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/admin/oauth-providers/google/reseed-from-env",
            json={"force_update": False},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OAUTH_BOOTSTRAP_ENV_NOT_SET"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/admin/oauth-providers/google/rotate-secret", {"new_secret": "x"}),
        ("POST", "/api/v1/admin/oauth-providers/google/reseed-from-env", {"force_update": True}),
        ("GET", "/api/v1/admin/oauth-providers/google/history", None),
        ("GET", "/api/v1/admin/oauth-providers/google/status", None),
        ("GET", "/api/v1/admin/oauth-providers/google/rate-limits", None),
        (
            "PUT",
            "/api/v1/admin/oauth-providers/google/rate-limits",
            {
                "per_ip_max": 1,
                "per_ip_window": 1,
                "per_user_max": 1,
                "per_user_window": 1,
                "global_max": 1,
                "global_window": 1,
            },
        ),
    ],
)
async def test_new_admin_endpoints_reject_non_admin(
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    app = _app(AdminOAuthServiceStub(), _member_user)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.request(method, path, json=body)

    assert response.status_code == 403
