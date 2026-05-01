from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.middleware.tenant_resolver import (
    TenantResolverMiddleware,
    _build_opaque_404_response,
)
from platform.common.tenant_context import TenantContext
from platform.tenants.resolver import TENANT_INVALIDATION_CHANNEL, TenantResolver
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


class RedisCacheStub:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.client = None
        self.initialized = False
        self.fail_get = False
        self.fail_set = False

    async def get(self, key: str) -> bytes | None:
        if self.fail_get:
            raise RuntimeError("redis get failed")
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        del ttl
        if self.fail_set:
            raise RuntimeError("redis set failed")
        self.values[key] = value

    async def initialize(self) -> None:
        self.initialized = True


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
async def test_health_paths_bypass_tenant_resolution() -> None:
    class StubResolver:
        called = False

        async def resolve(self, host: str) -> TenantContext | None:
            del host
            self.called = True
            return None

    resolver = StubResolver()
    middleware = TenantResolverMiddleware(
        app=lambda scope, receive, send: None,
        settings=PlatformSettings(PLATFORM_DOMAIN="musematic.ai"),
        session_factory=lambda: None,  # type: ignore[arg-type]
        resolver=resolver,  # type: ignore[arg-type]
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"host", b"10.244.1.12:8000")],
            "scheme": "http",
            "server": ("10.244.1.12", 8000),
            "client": ("10.244.1.1", 123),
        }
    )

    async def call_next(_: Request) -> Response:
        return Response(b"ok")

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    assert response.body == b"ok"
    assert resolver.called is False


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


@pytest.mark.asyncio
async def test_resolver_redis_cache_paths_and_invalid_host_branches() -> None:
    redis = RedisCacheStub()
    resolver = StaticTenantResolver({"acme": _tenant(slug="acme", subdomain="acme")})
    resolver.redis_client = redis  # type: ignore[assignment]
    redis.values["tenants:resolve:cached.musematic.ai"] = (
        b'{"tenant":{"id":"00000000-0000-0000-0000-000000000001","slug":"cached",'
        b'"subdomain":"cached","kind":"enterprise","status":"active","region":"eu-central",'
        b'"branding":{"accent":"blue"},"feature_flags":{"beta":true}}}'
    )
    redis.values["tenants:resolve:missing.musematic.ai"] = b'{"miss":true}'

    assert resolver.normalize_host(None) is None
    assert resolver.normalize_host("") is None
    assert resolver.normalize_host("[2001:db8::1]:443") is None
    assert await resolver.resolve("outside.example.com") is None
    assert (await resolver.resolve("cached.musematic.ai")).slug == "cached"
    assert await resolver.resolve("missing.musematic.ai") is None

    redis.fail_get = True
    assert (await resolver.resolve("acme.musematic.ai")).slug == "acme"
    redis.fail_get = False
    redis.fail_set = True
    assert await resolver.resolve("unknown2.musematic.ai") is None


@pytest.mark.asyncio
async def test_resolver_invalidation_and_pubsub_listener_paths() -> None:
    resolver = StaticTenantResolver({"acme": _tenant(slug="acme", subdomain="acme")})
    tenant = await resolver.resolve("acme.musematic.ai")
    assert tenant is not None
    assert await resolver.resolve("acme.api.musematic.ai") is not None

    await resolver.handle_invalidation_message(
        {
            "tenant_id": str(tenant.id),
            "hosts": ["acme.api.musematic.ai", 123],
        }
    )
    await resolver.handle_invalidation_message(b"not-json")
    await resolver.handle_invalidation_message("[]")

    class PubSubStub:
        def __init__(self) -> None:
            self.subscribed: list[str] = []
            self.unsubscribed: list[str] = []
            self.closed = False

        async def subscribe(self, channel: str) -> None:
            self.subscribed.append(channel)

        async def listen(self):
            yield {"type": "subscribe", "data": b"ignored"}
            yield {
                "type": "message",
                "data": b'{"tenant_id":"00000000-0000-0000-0000-000000000001"}',
            }

        async def unsubscribe(self, channel: str) -> None:
            self.unsubscribed.append(channel)

        async def close(self) -> None:
            self.closed = True

    class RedisWithPubSub(RedisCacheStub):
        def __init__(self) -> None:
            super().__init__()
            self._pubsub = PubSubStub()
            self.client = self

        def pubsub(self) -> PubSubStub:  # type: ignore[no-redef]
            return self._pubsub

    redis = RedisWithPubSub()
    listener = StaticTenantResolver({})
    listener.redis_client = redis  # type: ignore[assignment]

    await listener.listen_for_invalidations()

    assert redis.initialized is True
    assert redis._pubsub.subscribed == [TENANT_INVALIDATION_CHANNEL]
    assert redis._pubsub.unsubscribed == [TENANT_INVALIDATION_CHANNEL]
    assert redis._pubsub.closed is True


def test_local_resolver_cache_expiration_and_eviction() -> None:
    resolver = StaticTenantResolver({})
    cache = resolver._local_cache
    tenant = TenantContext(
        id=uuid4(),
        slug="acme",
        subdomain="acme",
        kind="enterprise",
        status="active",
        region="eu-central",
    )

    cache.set("expired", tenant, ttl_seconds=-1)
    assert cache.get("expired") is not tenant

    small_cache = type(cache)(maxsize=1, ttl_seconds=60)
    small_cache.set("a", tenant)
    small_cache.set("b", None)
    assert small_cache.get("a") is not tenant
    assert small_cache.get("b") is None
