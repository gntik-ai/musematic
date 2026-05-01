from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.middleware.tenant_resolver import _apply_timing_floor
from time import perf_counter

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_strict_unknown_subdomain_timing_floor_adds_no_sleep() -> None:
    settings = PlatformSettings(PLATFORM_TENANT_ENFORCEMENT_LEVEL="strict")
    durations = []
    for _ in range(100):
        started = perf_counter()
        await _apply_timing_floor(settings)
        durations.append(perf_counter() - started)

    assert max(durations) - min(durations) < 0.002
