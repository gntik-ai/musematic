from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_rate_limit_within_limit(redis_client) -> None:
    results = [
        await redis_client.check_rate_limit("api", "user-1", limit=5, window_ms=10_000)
        for _ in range(5)
    ]

    assert all(result.allowed for result in results)
    assert results[-1].remaining == 0


@pytest.mark.asyncio
async def test_rate_limit_exceeded(redis_client) -> None:
    for _ in range(5):
        await redis_client.check_rate_limit("api", "user-2", limit=5, window_ms=10_000)

    result = await redis_client.check_rate_limit("api", "user-2", limit=5, window_ms=10_000)

    assert result.allowed is False
    assert result.retry_after_ms > 0


@pytest.mark.asyncio
async def test_rate_limit_window_boundary(redis_client) -> None:
    for _ in range(2):
        await redis_client.check_rate_limit("api", "user-3", limit=2, window_ms=100)

    blocked = await redis_client.check_rate_limit("api", "user-3", limit=2, window_ms=100)
    await asyncio.sleep(0.12)
    allowed = await redis_client.check_rate_limit("api", "user-3", limit=2, window_ms=100)

    assert blocked.allowed is False
    assert allowed.allowed is True

