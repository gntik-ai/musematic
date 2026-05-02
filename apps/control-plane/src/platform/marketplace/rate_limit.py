"""Public-marketplace submission rate limiter (UPD-049 FR-009).

Sliding-window per-submitter cap implemented via a Redis sorted set keyed
on ``marketplace:submission_rate_limit:{user_id}``. Each entry's score is
the submission's epoch-millisecond timestamp; values are submission UUIDs.

The window is 24 hours, and the cap is read from
``MARKETPLACE_SUBMISSION_RATE_LIMIT_PER_DAY`` (default 5).

See ``specs/099-marketplace-scope/research.md`` (R5) for the design
rationale (sliding window over fixed-window counters, sorted-set choice
over Lua scripts, fail-closed on Redis outage).
"""

from __future__ import annotations

import time
from platform.common.clients.redis import AsyncRedisClient
from platform.marketplace.metrics import marketplace_rate_limit_refusals_total
from platform.registry.exceptions import SubmissionRateLimitExceededError
from uuid import UUID, uuid4

WINDOW_SECONDS: int = 24 * 60 * 60
"""Sliding-window length: 24 hours."""

KEY_TEMPLATE: str = "marketplace:submission_rate_limit:{user_id}"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _key(user_id: UUID) -> str:
    return KEY_TEMPLATE.format(user_id=user_id)


class MarketplaceSubmissionRateLimiter:
    """Per-submitter sliding-window limiter for public-marketplace submissions.

    Usage::

        limiter = MarketplaceSubmissionRateLimiter(redis_client, cap_per_day=5)
        await limiter.check_and_record(submitter_user_id)
        # → raises SubmissionRateLimitExceededError if at cap
    """

    def __init__(self, redis: AsyncRedisClient, cap_per_day: int) -> None:
        self._redis = redis
        self._cap = cap_per_day

    async def check_and_record(self, user_id: UUID) -> None:
        """Atomically evict aged-out entries, refuse if at cap, record otherwise.

        Raises ``SubmissionRateLimitExceededError`` (HTTP 429) on cap. The
        error carries ``retry_after_seconds`` derived from the oldest
        remaining entry's timestamp.
        """
        client = self._client()
        key = _key(user_id)
        now_ms = _now_ms()
        cutoff = now_ms - WINDOW_SECONDS * 1000

        # Evict aged-out entries first.
        await client.zremrangebyscore(key, 0, cutoff)

        count = int(await client.zcard(key) or 0)
        if count >= self._cap:
            retry_seconds = await self._retry_after_seconds(key, now_ms)
            marketplace_rate_limit_refusals_total.inc()
            raise SubmissionRateLimitExceededError(retry_after_seconds=retry_seconds)

        await client.zadd(key, {str(uuid4()): now_ms})
        # Slide the TTL so a long-idle key eventually GCs itself.
        await client.expire(key, WINDOW_SECONDS + 60)

    async def retry_after_seconds(self, user_id: UUID) -> int:
        """Standalone helper: how long until the next submission would succeed.

        Returns 0 if the submitter is currently below the cap.
        """
        client = self._client()
        key = _key(user_id)
        now_ms = _now_ms()
        cutoff = now_ms - WINDOW_SECONDS * 1000
        await client.zremrangebyscore(key, 0, cutoff)
        if int(await client.zcard(key) or 0) < self._cap:
            return 0
        return await self._retry_after_seconds(key, now_ms)

    async def _retry_after_seconds(self, key: str, now_ms: int) -> int:
        client = self._client()
        oldest = await client.zrange(key, 0, 0, withscores=True)
        if not oldest:
            return WINDOW_SECONDS  # defensive — shouldn't happen if cap was reached
        _, oldest_score = oldest[0]
        seconds_until_eviction = WINDOW_SECONDS - int((now_ms - int(oldest_score)) / 1000)
        return max(1, seconds_until_eviction)

    def _client(self) -> object:
        client = self._redis.client
        if client is None:
            # Fail-closed: if Redis is unreachable, surface the error rather
            # than silently allowing the submission past the cap.
            raise RuntimeError(
                "MarketplaceSubmissionRateLimiter requires an initialized Redis client"
            )
        return client
