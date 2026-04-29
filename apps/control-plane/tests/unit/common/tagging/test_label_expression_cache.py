from __future__ import annotations

from platform.common.tagging.constants import REDIS_KEY_AST_TEMPLATE
from platform.common.tagging.label_expression.cache import LabelExpressionCache
from uuid import uuid4

import pytest


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.get_calls = 0
        self.set_calls: list[tuple[str, bytes, int | None]] = []
        self.deleted: list[str] = []

    async def get(self, key: str) -> bytes | None:
        self.get_calls += 1
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self.values[key] = value
        self.set_calls.append((key, value, ttl))

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.deleted.append(key)


@pytest.mark.asyncio
async def test_cache_uses_lru_before_redis_and_invalidates() -> None:
    redis = FakeRedis()
    cache = LabelExpressionCache(redis, lru_size=2, ttl_seconds=123)
    policy_id = uuid4()
    key = REDIS_KEY_AST_TEMPLATE.format(policy_id=policy_id, version=1)

    first = await cache.get_or_compile(policy_id, 1, "env=production")
    second = await cache.get_or_compile(policy_id, 1, "env=production")

    assert first is second
    assert redis.get_calls == 1
    assert redis.set_calls[0][0] == key
    assert redis.set_calls[0][2] == 123

    await cache.invalidate(policy_id, 1)

    assert redis.deleted == [key]
    assert await cache.get_or_compile(policy_id, 1, None) is None


@pytest.mark.asyncio
async def test_cache_hydrates_lru_from_redis_and_evicts_old_entries() -> None:
    redis = FakeRedis()
    seed = LabelExpressionCache(redis, lru_size=1)
    policy_a = uuid4()
    policy_b = uuid4()
    await seed.get_or_compile(policy_a, 1, "env=production")

    cache = LabelExpressionCache(redis, lru_size=1)
    from_redis = await cache.get_or_compile(policy_a, 1, "env=production")
    await cache.get_or_compile(policy_b, 1, "tier=critical")
    reloaded = await cache.get_or_compile(policy_a, 1, "env=production")

    assert from_redis.evaluate({"env": "production"}) is True
    assert reloaded.evaluate({"env": "production"}) is True
    assert redis.get_calls >= 2
