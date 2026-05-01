from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.middleware.tenant_resolver import (
    TenantResolverMiddleware,
    _build_opaque_404_response,
)
from platform.common.tenant_context import TenantContext
from platform.tenants.resolver import TenantResolver
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from starlette.requests import Request
from starlette.responses import Response


class StaticTenantResolver(TenantResolver):
    def __init__(self, tenants_by_subdomain: dict[str, SimpleNamespace]) -> None:
        super().__init__(
            settings=PlatformSettings(PLATFORM_DOMAIN="musematic.ai"),
            session_factory=lambda: None,  # type: ignore[arg-type]
        )
        self.tenants_by_subdomain = tenants_by_subdomain

    async def _query_tenant(self, subdomain: str) -> SimpleNamespace | None:  # type: ignore[override]
        return self.tenants_by_subdomain.get(subdomain)


def _tenant(
    *,
    slug: str,
    subdomain: str,
    kind: str = "enterprise",
    status: str = "active",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000001") if kind == "default" else uuid4(),
        slug=slug,
        subdomain=subdomain,
        kind=kind,
        status=status,
        region="eu-central",
        branding_config_json={},
        feature_flags_json={},
    )


@pytest.mark.asyncio
async def test_default_tenant_lookup_and_port_strip() -> None:
    resolver = StaticTenantResolver(
        {"app": _tenant(slug="default", subdomain="app", kind="default")}
    )

    assert (await resolver.resolve("app.musematic.ai")).slug == "default"
    assert (await resolver.resolve("APP.MUSEMATIC.AI:443")).slug == "default"
    assert (await resolver.resolve("app.musematic.ai:8080")).slug == "default"


@pytest.mark.asyncio
async def test_enterprise_tenant_lookup_and_surfaces() -> None:
    resolver = StaticTenantResolver({"acme": _tenant(slug="acme", subdomain="acme")})

    assert (await resolver.resolve("acme.musematic.ai")).slug == "acme"
    assert (await resolver.resolve("acme.api.musematic.ai")).slug == "acme"
    assert (await resolver.resolve("acme.grafana.musematic.ai")).slug == "acme"


@pytest.mark.asyncio
async def test_unknown_and_suspended_tenants() -> None:
    resolver = StaticTenantResolver(
        {"paused": _tenant(slug="paused", subdomain="paused", status="suspended")}
    )

    assert await resolver.resolve("unknown.musematic.ai") is None
    suspended = await resolver.resolve("paused.musematic.ai")
    assert suspended is not None
    assert suspended.status == "suspended"


def test_opaque_404_is_byte_stable() -> None:
    first = _build_opaque_404_response()
    second = _build_opaque_404_response()

    assert first.status_code == 404
    assert first.body == second.body == b'{"detail":"Not Found"}'
    assert first.headers["content-length"] == second.headers["content-length"]
    assert "set-cookie" not in first.headers


@pytest.mark.asyncio
async def test_pending_deletion_tenant_returns_opaque_404_for_non_staff() -> None:
    pending = TenantContext(
        id=uuid4(),
        slug="deleted",
        subdomain="deleted",
        kind="enterprise",
        status="pending_deletion",
        region="eu-central",
    )

    class StubResolver:
        async def resolve(self, host: str) -> TenantContext:
            del host
            return pending

    middleware = TenantResolverMiddleware(
        app=lambda scope, receive, send: None,
        settings=PlatformSettings(PLATFORM_DOMAIN="musematic.ai"),
        session_factory=lambda: None,  # type: ignore[arg-type]
        resolver=StubResolver(),  # type: ignore[arg-type]
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"host", b"deleted.musematic.ai")],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        }
    )

    async def call_next(_: Request) -> Response:
        return Response(b"ok")

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 404
    assert response.body == b'{"detail":"Not Found"}'
