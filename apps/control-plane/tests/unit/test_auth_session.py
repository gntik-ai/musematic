from __future__ import annotations

from platform.auth.session import RedisSessionStore
from uuid import uuid4

import pytest

from tests.auth_support import FakeAsyncRedisClient


@pytest.mark.asyncio
async def test_create_and_get_session(auth_settings) -> None:
    redis_client = FakeAsyncRedisClient()
    store = RedisSessionStore(redis_client, auth_settings.auth)
    user_id = uuid4()
    session_id = uuid4()
    roles = [{"role": "viewer", "workspace_id": None}]

    await store.create_session(
        user_id=user_id,
        session_id=session_id,
        email="user@example.com",
        roles=roles,
        ip="127.0.0.1",
        device="pytest",
        refresh_jti="refresh-1",
    )

    session = await store.get_session(user_id, session_id)
    client = await redis_client._get_client()

    assert session is not None
    assert session["email"] == "user@example.com"
    assert session["roles"] == roles
    assert session["refresh_jti"] == "refresh-1"
    assert await client.ttl(f"session:{user_id}:{session_id}") == auth_settings.auth.session_ttl
    assert str(session_id) in await client.smembers(f"user_sessions:{user_id}")


@pytest.mark.asyncio
async def test_delete_session_updates_index(auth_settings) -> None:
    redis_client = FakeAsyncRedisClient()
    store = RedisSessionStore(redis_client, auth_settings.auth)
    user_id = uuid4()
    session_id = uuid4()

    await store.create_session(
        user_id=user_id,
        session_id=session_id,
        email="user@example.com",
        roles=[],
        ip="127.0.0.1",
        device="pytest",
        refresh_jti="refresh-1",
    )
    await store.delete_session(user_id, session_id)

    client = await redis_client._get_client()
    assert await store.get_session(user_id, session_id) is None
    assert str(session_id) not in await client.smembers(f"user_sessions:{user_id}")


@pytest.mark.asyncio
async def test_delete_all_sessions_returns_deleted_count(auth_settings) -> None:
    redis_client = FakeAsyncRedisClient()
    store = RedisSessionStore(redis_client, auth_settings.auth)
    user_id = uuid4()
    session_ids = [uuid4(), uuid4()]

    for session_id in session_ids:
        await store.create_session(
            user_id=user_id,
            session_id=session_id,
            email="user@example.com",
            roles=[],
            ip="127.0.0.1",
            device="pytest",
            refresh_jti=str(session_id),
        )

    deleted = await store.delete_all_sessions(user_id)

    assert deleted == 2
    for session_id in session_ids:
        assert await store.get_session(user_id, session_id) is None


@pytest.mark.asyncio
async def test_delete_all_sessions_returns_zero_when_empty(auth_settings) -> None:
    store = RedisSessionStore(FakeAsyncRedisClient(), auth_settings.auth)

    assert await store.delete_all_sessions(uuid4()) == 0
