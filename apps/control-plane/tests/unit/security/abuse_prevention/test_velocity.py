"""UPD-050 — SignupVelocityLimiter unit tests."""

from __future__ import annotations

from platform.security.abuse_prevention.exceptions import SignupRateLimitExceededError
from platform.security.abuse_prevention.velocity import (
    SignupVelocityLimiter,
    VelocityThresholds,
)
from unittest.mock import MagicMock

import pytest


class _FakeSortedSet:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, float]] = {}

    async def zremrangebyscore(self, key: str, low: float, high: float) -> int:
        store = self.data.setdefault(key, {})
        before = len(store)
        self.data[key] = {
            k: v for k, v in store.items() if not (low <= v <= high)
        }
        return before - len(self.data[key])

    async def zcard(self, key: str) -> int:
        return len(self.data.get(key, {}))

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        store = self.data.setdefault(key, {})
        added = 0
        for k, v in mapping.items():
            if k not in store:
                added += 1
            store[k] = v
        return added

    async def zrange(
        self, key: str, start: int, end: int, *, withscores: bool = False
    ) -> list:
        items = sorted(self.data.get(key, {}).items(), key=lambda x: x[1])
        return items[start : end + 1] if withscores else [k for k, _ in items]

    async def expire(self, key: str, seconds: int) -> None:
        return None


class _FakeRedis:
    def __init__(self) -> None:
        self.client = _FakeSortedSet()


@pytest.mark.asyncio
async def test_under_cap_records_successfully() -> None:
    limiter = SignupVelocityLimiter(_FakeRedis())
    thresholds = VelocityThresholds(
        ip_threshold=5, asn_threshold=50, email_domain_threshold=20
    )
    for _ in range(5):
        await limiter.check_and_record(
            ip="1.2.3.4", asn=None, email_domain=None, thresholds=thresholds
        )


@pytest.mark.asyncio
async def test_sixth_in_window_refused_per_ip() -> None:
    limiter = SignupVelocityLimiter(_FakeRedis())
    thresholds = VelocityThresholds(
        ip_threshold=5, asn_threshold=50, email_domain_threshold=20
    )
    for _ in range(5):
        await limiter.check_and_record(
            ip="1.2.3.4", asn=None, email_domain=None, thresholds=thresholds
        )
    with pytest.raises(SignupRateLimitExceededError) as exc:
        await limiter.check_and_record(
            ip="1.2.3.4", asn=None, email_domain=None, thresholds=thresholds
        )
    assert exc.value.retry_after_seconds > 0
    assert "ip:1.2.3.4" in exc.value.details["counter_key"]


@pytest.mark.asyncio
async def test_independent_ip_counters() -> None:
    limiter = SignupVelocityLimiter(_FakeRedis())
    thresholds = VelocityThresholds(
        ip_threshold=2, asn_threshold=50, email_domain_threshold=20
    )
    await limiter.check_and_record(
        ip="1.1.1.1", asn=None, email_domain=None, thresholds=thresholds
    )
    await limiter.check_and_record(
        ip="1.1.1.1", asn=None, email_domain=None, thresholds=thresholds
    )
    # Different IP → independent counter.
    await limiter.check_and_record(
        ip="2.2.2.2", asn=None, email_domain=None, thresholds=thresholds
    )


@pytest.mark.asyncio
async def test_email_domain_window_independent() -> None:
    limiter = SignupVelocityLimiter(_FakeRedis())
    thresholds = VelocityThresholds(
        ip_threshold=999,
        asn_threshold=999,
        email_domain_threshold=2,
    )
    await limiter.check_and_record(
        ip=None, asn=None, email_domain="example.com", thresholds=thresholds
    )
    await limiter.check_and_record(
        ip=None, asn=None, email_domain="example.com", thresholds=thresholds
    )
    with pytest.raises(SignupRateLimitExceededError):
        await limiter.check_and_record(
            ip=None, asn=None, email_domain="example.com", thresholds=thresholds
        )


@pytest.mark.asyncio
async def test_redis_outage_fails_closed() -> None:
    redis = MagicMock()
    redis.client = None
    limiter = SignupVelocityLimiter(redis)
    thresholds = VelocityThresholds(
        ip_threshold=5, asn_threshold=50, email_domain_threshold=20
    )
    with pytest.raises(SignupRateLimitExceededError) as exc:
        await limiter.check_and_record(
            ip="1.2.3.4", asn=None, email_domain=None, thresholds=thresholds
        )
    assert "redis:unavailable" in exc.value.details["counter_key"]
