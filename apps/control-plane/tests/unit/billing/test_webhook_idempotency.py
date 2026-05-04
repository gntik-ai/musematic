"""T078 — unit tests for the two-layer webhook idempotency guard."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from platform.billing.webhooks.idempotency import (
    WebhookIdempotency,
    webhook_lock_key,
)


class FakeRedis:
    """Minimal in-memory async Redis stand-in covering SET NX EX + DELETE."""

    def __init__(self, *, fail_on_set: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.deletes: list[str] = []
        self.fail_on_set = fail_on_set

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        del ex
        if self.fail_on_set:
            return False
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        removed = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                removed += 1
            self.deletes.append(k)
        return removed


class FakeScalar:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeSession:
    def __init__(self, *, existing: bool = False, raise_on_flush: bool = False) -> None:
        self._existing = existing
        self._raise_on_flush = raise_on_flush
        self.added: list[Any] = []
        self.flushed = 0
        self.rolled_back = 0
        self.next_existing_overrides: list[bool] = []

    async def execute(self, _stmt: Any) -> FakeScalar:
        # Honor any per-call override the test sets (used to simulate the
        # race "fresh acquire then row appears under us").
        if self.next_existing_overrides:
            return FakeScalar("row" if self.next_existing_overrides.pop(0) else None)
        return FakeScalar("row" if self._existing else None)

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushed += 1
        if self._raise_on_flush:
            raise IntegrityError("dup", {}, Exception("dup"))

    async def rollback(self) -> None:
        self.rolled_back += 1


@pytest.mark.asyncio
async def test_acquire_returns_fresh_when_no_record_and_lock_available() -> None:
    redis = FakeRedis()
    session = FakeSession()
    guard = WebhookIdempotency(redis=redis, lock_ttl_seconds=60)

    decision = await guard.acquire(session, "evt_1")

    assert decision.proceed is True
    assert decision.reason == "fresh"
    assert webhook_lock_key("evt_1") in redis.store


@pytest.mark.asyncio
async def test_acquire_returns_already_processed_when_record_exists() -> None:
    redis = FakeRedis()
    session = FakeSession(existing=True)
    guard = WebhookIdempotency(redis=redis, lock_ttl_seconds=60)

    decision = await guard.acquire(session, "evt_2")

    assert decision.proceed is False
    assert decision.reason == "already_processed"
    assert webhook_lock_key("evt_2") not in redis.store


@pytest.mark.asyncio
async def test_acquire_returns_already_processing_when_lock_taken() -> None:
    redis = FakeRedis()
    redis.store[webhook_lock_key("evt_3")] = "1"
    session = FakeSession()
    guard = WebhookIdempotency(redis=redis, lock_ttl_seconds=60)

    decision = await guard.acquire(session, "evt_3")

    assert decision.proceed is False
    assert decision.reason == "already_processing"


@pytest.mark.asyncio
async def test_acquire_rejects_empty_event_id() -> None:
    redis = FakeRedis()
    session = FakeSession()
    guard = WebhookIdempotency(redis=redis)

    decision = await guard.acquire(session, "")

    assert decision.proceed is False


@pytest.mark.asyncio
async def test_mark_processed_rolls_back_on_pk_race() -> None:
    redis = FakeRedis()
    session = FakeSession(raise_on_flush=True)
    guard = WebhookIdempotency(redis=redis)

    # Should not raise — the race is logged and swallowed.
    await guard.mark_processed(session, "evt_4", "customer.subscription.created")

    assert session.flushed == 1
    assert session.rolled_back == 1


@pytest.mark.asyncio
async def test_release_lock_removes_redis_key() -> None:
    redis = FakeRedis()
    redis.store[webhook_lock_key("evt_5")] = "1"
    guard = WebhookIdempotency(redis=redis)

    await guard.release_lock("evt_5")

    assert webhook_lock_key("evt_5") in redis.deletes
    assert webhook_lock_key("evt_5") not in redis.store
