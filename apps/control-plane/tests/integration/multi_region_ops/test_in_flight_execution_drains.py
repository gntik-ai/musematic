from __future__ import annotations

import asyncio
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


async def test_in_flight_execution_progresses_while_gate_blocks_new_writes() -> None:
    redis = FakeRedis()
    services = build_services(seeded_repository(), redis=redis)
    await services["maintenance"]._prime_active_cache(make_window(status="active"))
    app = build_gate_app(settings=PlatformSettings(feature_maintenance_mode=True), redis=redis)
    progress: list[str] = []

    async def long_running_execution() -> None:
        for step in ("started", "checkpoint", "completed"):
            await asyncio.sleep(0.01)
            progress.append(step)

    task = asyncio.create_task(long_running_execution())
    async with await async_client(app) as client:
        blocked = await client.post("/api/v1/admin/regions")
    await task

    assert blocked.status_code == 503
    assert progress == ["started", "checkpoint", "completed"]
    assert await redis.get("multi_region:active_window") is not None
