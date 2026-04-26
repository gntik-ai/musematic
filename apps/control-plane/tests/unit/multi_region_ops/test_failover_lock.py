from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.multi_region_ops.services.failover_service import FailoverService

import pytest


class FakeRedisCore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        assert ex > 0
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True


class FakeRedis:
    def __init__(self) -> None:
        self.core = FakeRedisCore()

    async def _get_client(self) -> FakeRedisCore:
        return self.core

    async def get(self, key: str) -> bytes | None:
        value = self.core.values.get(key)
        return value.encode() if value is not None else None

    async def delete(self, key: str) -> None:
        self.core.values.pop(key, None)


@pytest.mark.asyncio
async def test_failover_lock_is_set_nx_and_token_verified() -> None:
    redis = FakeRedis()
    service = FailoverService(
        repository=None,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        redis_client=redis,  # type: ignore[arg-type]
    )

    token = await service.acquire_failover_lock("eu-west", "us-east")
    second = await service.acquire_failover_lock("eu-west", "us-east")

    assert token is not None
    assert second is None
    assert await service.release_failover_lock("eu-west", "us-east", "wrong") is False
    assert await service.release_failover_lock("eu-west", "us-east", token) is True
    assert await service.acquire_failover_lock("eu-west", "us-east") is not None
