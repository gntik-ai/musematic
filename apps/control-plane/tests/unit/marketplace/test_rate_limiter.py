"""UPD-049 — MarketplaceSubmissionRateLimiter unit tests.

Verifies the sliding-window cap, eviction, and Retry-After behaviour
without touching a real Redis (uses an in-memory fake of the sorted-set
ops the limiter needs).
"""

from __future__ import annotations

from platform.marketplace.rate_limit import MarketplaceSubmissionRateLimiter
from platform.registry.exceptions import SubmissionRateLimitExceededError
from typing import Any
from uuid import uuid4

import pytest


class _FakeSortedSet:
    """Minimal in-memory sorted set with the four ops the limiter calls."""

    def __init__(self) -> None:
        self._entries: dict[str, float] = {}

    async def zremrangebyscore(self, _key: str, low: float, high: float) -> int:
        before = len(self._entries)
        self._entries = {k: v for k, v in self._entries.items() if not (low <= v <= high)}
        return before - len(self._entries)

    async def zcard(self, _key: str) -> int:
        return len(self._entries)

    async def zadd(self, _key: str, mapping: dict[str, float]) -> int:
        added = 0
        for member, score in mapping.items():
            if member not in self._entries:
                added += 1
            self._entries[member] = score
        return added

    async def zrange(
        self, _key: str, start: int, end: int, *, withscores: bool = False
    ) -> list[Any]:
        sorted_items = sorted(self._entries.items(), key=lambda x: x[1])
        slice_ = sorted_items[start : end + 1] if end >= 0 else sorted_items[start:]
        return slice_ if withscores else [m for m, _ in slice_]

    async def expire(self, _key: str, _seconds: int) -> None:
        return None


class _FakeRedis:
    def __init__(self) -> None:
        self.client = _FakeSortedSet()


@pytest.mark.asyncio
async def test_under_cap_records_successfully() -> None:
    limiter = MarketplaceSubmissionRateLimiter(_FakeRedis(), cap_per_day=5)  # type: ignore[arg-type]
    user_id = uuid4()
    for _ in range(5):
        await limiter.check_and_record(user_id)


@pytest.mark.asyncio
async def test_sixth_in_window_refused() -> None:
    limiter = MarketplaceSubmissionRateLimiter(_FakeRedis(), cap_per_day=5)  # type: ignore[arg-type]
    user_id = uuid4()
    for _ in range(5):
        await limiter.check_and_record(user_id)
    with pytest.raises(SubmissionRateLimitExceededError) as exc:
        await limiter.check_and_record(user_id)
    assert exc.value.retry_after_seconds > 0


@pytest.mark.asyncio
async def test_clearing_resets_counter() -> None:
    fake = _FakeRedis()
    limiter = MarketplaceSubmissionRateLimiter(fake, cap_per_day=5)  # type: ignore[arg-type]
    user_id = uuid4()
    for _ in range(5):
        await limiter.check_and_record(user_id)
    fake.client._entries.clear()  # simulate key eviction
    # First post-eviction submission should pass without raising.
    await limiter.check_and_record(user_id)


@pytest.mark.asyncio
async def test_window_slides_past_cutoff() -> None:
    """Entries older than 24h are evicted; a 6th submission then succeeds."""
    fake = _FakeRedis()
    limiter = MarketplaceSubmissionRateLimiter(fake, cap_per_day=5)  # type: ignore[arg-type]
    user_id = uuid4()
    # Pre-seed 5 entries with timestamps just outside the 24h window
    far_past_ms = 0  # epoch — definitely outside the window
    for _ in range(5):
        await fake.client.zadd(f"key", {str(uuid4()): far_past_ms})
    # The next check_and_record should evict the stale entries and succeed.
    await limiter.check_and_record(user_id)


@pytest.mark.asyncio
async def test_retry_after_zero_when_under_cap() -> None:
    limiter = MarketplaceSubmissionRateLimiter(_FakeRedis(), cap_per_day=5)  # type: ignore[arg-type]
    user_id = uuid4()
    await limiter.check_and_record(user_id)
    assert await limiter.retry_after_seconds(user_id) == 0
