from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_acquire_and_release(redis_client) -> None:
    lock = await redis_client.acquire_lock("scheduler", "main", ttl_seconds=10)

    assert lock.success is True
    assert lock.token is not None
    assert await redis_client.release_lock("scheduler", "main", lock.token) is True


@pytest.mark.asyncio
async def test_exclusive_lock(redis_client) -> None:
    first = await redis_client.acquire_lock("scheduler", "main", ttl_seconds=10)
    second = await redis_client.acquire_lock("scheduler", "main", ttl_seconds=10)

    assert first.success is True
    assert second.success is False


@pytest.mark.asyncio
async def test_wrong_token_release(redis_client) -> None:
    lock = await redis_client.acquire_lock("scheduler", "main", ttl_seconds=10)

    assert lock.token is not None
    assert await redis_client.release_lock("scheduler", "main", "wrong-token") is False
    assert await redis_client.release_lock("scheduler", "main", lock.token) is True


@pytest.mark.asyncio
async def test_lock_ttl_expiry(redis_client) -> None:
    first = await redis_client.acquire_lock("scheduler", "main", ttl_seconds=1)
    await asyncio.sleep(1.2)
    second = await redis_client.acquire_lock("scheduler", "main", ttl_seconds=1)

    assert first.success is True
    assert second.success is True


@pytest.mark.asyncio
async def test_lock_renewal(redis_client) -> None:
    lock = await redis_client.acquire_lock("scheduler", "renew", ttl_seconds=1)
    assert lock.token is not None

    renewed = await redis_client._eval_script(
        await redis_client._get_client(),
        "lock_acquire.lua",
        [redis_client._lock_key("scheduler", "renew")],
        [lock.token, 2],
    )
    await asyncio.sleep(1.2)
    still_held = await redis_client.acquire_lock("scheduler", "renew", ttl_seconds=1)

    assert int(renewed) == 1
    assert still_held.success is False

