from __future__ import annotations

import statistics
from platform.common.config import PlatformSettings
from platform.common.middleware.tenant_resolver import TenantResolverMiddleware
from platform.tenants.resolver import TenantResolver
from time import perf_counter
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient


class CountingTenantResolver(TenantResolver):
    def __init__(self, tenants_by_subdomain: dict[str, SimpleNamespace]) -> None:
        super().__init__(
            settings=PlatformSettings(
                PLATFORM_DOMAIN="musematic.ai",
                TENANT_RESOLVER_CACHE_TTL_SECONDS=60,
            ),
            session_factory=lambda: None,  # type: ignore[arg-type]
        )
        self.tenants_by_subdomain = tenants_by_subdomain
        self.query_count = 0

    async def _query_tenant(self, subdomain: str) -> SimpleNamespace | None:  # type: ignore[override]
        self.query_count += 1
        return self.tenants_by_subdomain.get(subdomain)


def _tenant(
    *,
    tenant_id: UUID | None = None,
    slug: str = "acme",
    subdomain: str = "acme",
    status: str = "active",
    branding: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=tenant_id or uuid4(),
        slug=slug,
        subdomain=subdomain,
        kind="enterprise",
        status=status,
        region="eu-central",
        branding_config_json=branding or {},
        feature_flags_json={},
    )


def _app(resolver: CountingTenantResolver) -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    async def probe(request: Request) -> dict[str, object]:
        tenant = request.state.tenant
        return {"slug": tenant.slug, "branding": dict(tenant.branding)}

    @app.get("/api/v1/platform/probe")
    async def platform_probe(request: Request) -> dict[str, object]:
        tenant = request.state.tenant
        return {"slug": tenant.slug, "status": tenant.status}

    app.add_middleware(
        TenantResolverMiddleware,
        settings=resolver.settings,
        session_factory=lambda: None,  # type: ignore[arg-type]
        resolver=resolver,
    )
    return app


@pytest.mark.asyncio
async def test_cache_miss_queries_backing_store_and_cache_hit_skips_it() -> None:
    resolver = CountingTenantResolver({"acme": _tenant()})

    async with AsyncClient(
        transport=ASGITransport(app=_app(resolver)),
        base_url="http://testserver",
    ) as client:
        first = await client.get("/probe", headers={"host": "acme.musematic.ai"})
        second = await client.get("/probe", headers={"host": "acme.musematic.ai"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["slug"] == "acme"
    assert second.json()["slug"] == "acme"
    assert resolver.query_count == 1


@pytest.mark.asyncio
async def test_invalidation_rebuilds_cached_tenant_context() -> None:
    tenant_id = uuid4()
    resolver = CountingTenantResolver(
        {
            "acme": _tenant(
                tenant_id=tenant_id,
                branding={"display_name_override": "Acme v1"},
            )
        }
    )

    async with AsyncClient(
        transport=ASGITransport(app=_app(resolver)),
        base_url="http://testserver",
    ) as client:
        first = await client.get("/probe", headers={"host": "acme.musematic.ai"})
        resolver.tenants_by_subdomain["acme"] = _tenant(
            tenant_id=tenant_id,
            branding={"display_name_override": "Acme v2"},
        )
        cached = await client.get("/probe", headers={"host": "acme.musematic.ai"})

        resolver.invalidate_tenant(str(tenant_id))
        rebuilt = await client.get("/probe", headers={"host": "acme.musematic.ai"})

    assert first.json()["branding"]["display_name_override"] == "Acme v1"
    assert cached.json()["branding"]["display_name_override"] == "Acme v1"
    assert rebuilt.json()["branding"]["display_name_override"] == "Acme v2"
    assert resolver.query_count == 2


@pytest.mark.asyncio
async def test_cache_resident_resolver_p95_is_under_five_ms() -> None:
    resolver = CountingTenantResolver({"acme": _tenant()})
    assert await resolver.resolve("acme.musematic.ai") is not None

    durations: list[float] = []
    for _ in range(250):
        started = perf_counter()
        assert await resolver.resolve("acme.musematic.ai") is not None
        durations.append(perf_counter() - started)

    p95 = statistics.quantiles(durations, n=20)[18]
    assert p95 < 0.005
    assert resolver.query_count == 1


@pytest.mark.asyncio
async def test_platform_staff_request_bypasses_pending_deletion_opacity() -> None:
    resolver = CountingTenantResolver(
        {"acme": _tenant(slug="acme", subdomain="acme", status="pending_deletion")}
    )

    async with AsyncClient(
        transport=ASGITransport(app=_app(resolver)),
        base_url="http://testserver",
    ) as client:
        non_staff = await client.get("/probe", headers={"host": "acme.musematic.ai"})
        platform_staff = await client.get(
            "/api/v1/platform/probe",
            headers={"host": "acme.musematic.ai"},
        )

    assert non_staff.status_code == 404
    assert non_staff.content == b'{"detail":"Not Found"}'
    assert platform_staff.status_code == 200
    assert platform_staff.json() == {"slug": "acme", "status": "pending_deletion"}
