from __future__ import annotations

import statistics
from platform.common.config import PlatformSettings
from platform.tenants.resolver import TenantResolver
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


class CountingResolver(TenantResolver):
    def __init__(self) -> None:
        super().__init__(
            settings=PlatformSettings(
                PLATFORM_DOMAIN="musematic.ai",
                TENANT_RESOLVER_CACHE_TTL_SECONDS=60,
            ),
            session_factory=lambda: None,  # type: ignore[arg-type]
        )
        self.query_count = 0

    async def _query_tenant(self, subdomain: str) -> SimpleNamespace | None:  # type: ignore[override]
        self.query_count += 1
        if subdomain != "acme":
            return None
        return SimpleNamespace(
            id=uuid4(),
            slug="acme",
            subdomain="acme",
            kind="enterprise",
            status="active",
            region="eu-central",
            branding_config_json={},
            feature_flags_json={},
        )


@pytest.mark.asyncio
async def test_resolver_cache_resident_p95_under_five_ms() -> None:
    resolver = CountingResolver()
    assert await resolver.resolve("acme.musematic.ai") is not None

    durations = []
    for _ in range(10_000):
        started = perf_counter()
        assert await resolver.resolve("acme.musematic.ai") is not None
        durations.append(perf_counter() - started)

    assert statistics.quantiles(durations, n=20)[18] < 0.005
    assert resolver.query_count == 1
