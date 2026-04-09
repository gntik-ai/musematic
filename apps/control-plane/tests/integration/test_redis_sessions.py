from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_set_get_session(redis_client) -> None:
    payload = {"email": "alice@example.com", "roles": ["member"]}
    await redis_client.set_session("u1", "s1", payload, ttl_seconds=5)

    stored = await redis_client.get_session("u1", "s1")

    assert stored == payload


@pytest.mark.asyncio
async def test_session_ttl_expiry(redis_client) -> None:
    await redis_client.set_session("u1", "s1", {"ok": True}, ttl_seconds=1)
    await asyncio.sleep(1.2)

    assert await redis_client.get_session("u1", "s1") is None


@pytest.mark.asyncio
async def test_delete_session(redis_client) -> None:
    await redis_client.set_session("u1", "s1", {"ok": True})

    assert await redis_client.delete_session("u1", "s1") is True
    assert await redis_client.get_session("u1", "s1") is None


@pytest.mark.asyncio
async def test_invalidate_user_sessions(redis_client) -> None:
    await redis_client.set_session("u1", "s1", {"a": 1})
    await redis_client.set_session("u1", "s2", {"a": 2})
    await redis_client.set_session("u2", "s3", {"a": 3})

    deleted = await redis_client.invalidate_user_sessions("u1")

    assert deleted == 2
    assert await redis_client.get_session("u1", "s1") is None
    assert await redis_client.get_session("u1", "s2") is None
    assert await redis_client.get_session("u2", "s3") == {"a": 3}

