from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.notifications.models import DeliveryMethod
from platform.notifications.workers.channel_verification_worker import (
    build_channel_verification_scheduler,
    expire_unverified_channels,
)
from platform.notifications.workers.deadletter_threshold_worker import (
    _acquire_cooldown,
    build_dead_letter_threshold_scheduler,
    run_dead_letter_threshold_scan,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest


class ProducerStub:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def publish(self, **kwargs) -> None:
        self.events.append(kwargs)


class ChannelRepoStub:
    def __init__(self, expired: list[SimpleNamespace]) -> None:
        self.expired = expired

    async def expire_channel_verifications(self, now):
        del now
        return self.expired


class DepthRepoStub:
    def __init__(self, depths: dict[object, int]) -> None:
        self.depths = depths

    async def aggregate_dead_letter_depth_by_workspace(self):
        return self.depths


class RedisClientSetStub:
    def __init__(self, result: bool = True) -> None:
        self.result = result

    async def set(self, key, value, *, ex, nx):
        del key, value, ex, nx
        return self.result


class RedisWithClientStub:
    def __init__(self, client: RedisClientSetStub) -> None:
        self.client = client


class RedisFallbackStub:
    def __init__(self, exists: bool) -> None:
        self.exists = exists
        self.writes: list[tuple[str, bytes, int]] = []

    async def get(self, key):
        del key
        return b"1" if self.exists else None

    async def set(self, key, value, *, ttl=None, ex=None, nx=None):
        del ex, nx
        if isinstance(value, str):
            raise TypeError
        self.writes.append((key, value, ttl))


@pytest.mark.asyncio
async def test_channel_verification_worker_publishes_expired_configs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        channel_type=DeliveryMethod.email,
    )
    producer = ProducerStub()

    count = await expire_unverified_channels(ChannelRepoStub([config]), producer)

    assert count == 1
    assert producer.events[0]["event_type"] == "notifications.channel.config.changed"

    scheduler = build_channel_verification_scheduler(lambda: None)
    assert scheduler is not None

    real_import = __import__

    def _blocked_import(name, *args, **kwargs):
        if name == "apscheduler.schedulers.asyncio":
            raise RuntimeError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _blocked_import)
    assert build_channel_verification_scheduler(lambda: None) is None


@pytest.mark.asyncio
async def test_dead_letter_threshold_worker_cooldown_fallback_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    settings = PlatformSettings()
    settings.notifications.dead_letter_warning_threshold = 5
    producer = ProducerStub()

    below = await run_dead_letter_threshold_scan(
        repo=DepthRepoStub({workspace_id: 4}),
        redis=RedisWithClientStub(RedisClientSetStub()),
        settings=settings,
        producer=producer,
    )
    assert below == 0
    assert producer.events == []

    assert await _acquire_cooldown(RedisWithClientStub(RedisClientSetStub(True)), workspace_id)
    assert not await _acquire_cooldown(
        RedisWithClientStub(RedisClientSetStub(False)),
        workspace_id,
    )
    assert await _acquire_cooldown(object(), workspace_id)

    existing = RedisFallbackStub(exists=True)
    assert not await _acquire_cooldown(existing, workspace_id)
    missing = RedisFallbackStub(exists=False)
    assert await _acquire_cooldown(missing, workspace_id)
    assert missing.writes

    scheduler = build_dead_letter_threshold_scheduler(lambda: None, seconds=5)
    assert scheduler is not None

    real_import = __import__

    def _blocked_import(name, *args, **kwargs):
        if name == "apscheduler.schedulers.asyncio":
            raise RuntimeError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _blocked_import)
    assert build_dead_letter_threshold_scheduler(lambda: None) is None
