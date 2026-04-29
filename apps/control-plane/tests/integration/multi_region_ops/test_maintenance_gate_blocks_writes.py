from __future__ import annotations

from platform.common.config import PlatformSettings

import pytest

from tests.integration.multi_region_ops.support import (
    FakeRedis,
    async_client,
    build_gate_app,
    build_services,
    make_window,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_maintenance_gate_blocks_mutations_across_routes_then_reopens() -> None:
    redis = FakeRedis()
    services = build_services(seeded_repository(), redis=redis)
    window = make_window(status="active")
    await services["maintenance"]._prime_active_cache(window)
    app = build_gate_app(settings=PlatformSettings(feature_maintenance_mode=True), redis=redis)

    async with await async_client(app) as client:
        for method, path in (
            ("POST", "/api/v1/admin/regions"),
            ("PUT", "/api/v1/admin/regions/region-1"),
            ("PATCH", "/api/v1/admin/regions/region-1"),
            ("DELETE", "/api/v1/admin/regions/region-1"),
        ):
            response = await client.request(method, path)
            assert response.status_code == 503
            assert response.json()["announcement"] == "Writes are paused for maintenance"

        assert (await client.get("/api/v1/regions/replication-status")).status_code == 200
        assert (await client.head("/api/v1/regions/replication-status")).status_code == 200
        assert (await client.options("/api/v1/regions/replication-status")).status_code == 200

        await redis.delete("multi_region:active_window")
        assert (await client.post("/api/v1/admin/regions")).status_code == 200
