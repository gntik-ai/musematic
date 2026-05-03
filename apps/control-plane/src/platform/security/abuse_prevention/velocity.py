"""Per-IP / per-ASN / per-email-domain signup velocity limiter (UPD-050 T023).

Redis hot path with sliding-window sorted sets, mirroring the
``marketplace/rate_limit.py`` pattern. Three independent counters per
signup attempt; the first to exceed its configured threshold raises
``SignupRateLimitExceededError``.

Per research R2 the path **fails closed** on Redis outage — any
exception bubbling out of the Redis client is wrapped in a fail-closed
error so the signup is refused rather than silently allowed past the
cap.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from platform.common.clients.redis import AsyncRedisClient
from platform.common.logging import get_logger
from platform.security.abuse_prevention.exceptions import SignupRateLimitExceededError
from platform.security.abuse_prevention.metrics import (
    abuse_velocity_hits_total,
    abuse_velocity_redis_errors_total,
)
from typing import Any
from uuid import uuid4

LOGGER = get_logger(__name__)

KEY_TEMPLATES: dict[str, str] = {
    "ip": "abuse:vel:ip:{value}",
    "asn": "abuse:vel:asn:{value}",
    "email_domain": "abuse:vel:domain:{value}",
}


@dataclass(frozen=True, slots=True)
class VelocityThresholds:
    """Resolved thresholds + window lengths for the three counters.

    Window length is in seconds; threshold is the cap (exclusive — the
    Nth attempt is the one refused, where N == threshold + 1).
    """

    ip_threshold: int
    asn_threshold: int
    email_domain_threshold: int
    ip_window_seconds: int = 3600
    asn_window_seconds: int = 3600
    email_domain_window_seconds: int = 86400


class SignupVelocityLimiter:
    """Sliding-window per-IP / per-ASN / per-email-domain signup limiter."""

    def __init__(self, redis: AsyncRedisClient) -> None:
        self._redis = redis

    async def check_and_record(
        self,
        *,
        ip: str | None,
        asn: str | None,
        email_domain: str | None,
        thresholds: VelocityThresholds,
    ) -> None:
        """Increment counters and refuse if any one exceeds its threshold.

        On Redis outage, raises a fail-closed
        ``SignupRateLimitExceededError`` with retry_after_seconds=60 —
        signups are refused for the duration of the outage by design.
        """
        client = self._client()
        now_ms = int(time.time() * 1000)

        for kind, value, threshold, window in (
            ("ip", ip, thresholds.ip_threshold, thresholds.ip_window_seconds),
            ("asn", asn, thresholds.asn_threshold, thresholds.asn_window_seconds),
            (
                "email_domain",
                email_domain,
                thresholds.email_domain_threshold,
                thresholds.email_domain_window_seconds,
            ),
        ):
            if not value:
                continue
            key = KEY_TEMPLATES[kind].format(value=value)
            cutoff = now_ms - window * 1000
            try:
                await client.zremrangebyscore(key, 0, cutoff)
                count = int(await client.zcard(key) or 0)
                if count >= threshold:
                    abuse_velocity_hits_total.labels(counter=kind).inc()
                    retry = await self._retry_after_seconds(
                        key, now_ms, window
                    )
                    raise SignupRateLimitExceededError(
                        counter_key=f"{kind}:{value}",
                        retry_after_seconds=retry,
                    )
                await client.zadd(key, {str(uuid4()): now_ms})
                await client.expire(key, window + 60)
            except SignupRateLimitExceededError:
                raise
            except Exception:
                abuse_velocity_redis_errors_total.inc()
                LOGGER.exception(
                    "abuse.velocity.redis_error",
                    extra={"counter": kind, "value": value},
                )
                raise SignupRateLimitExceededError(
                    counter_key=f"{kind}:fail_closed",
                    retry_after_seconds=60,
                ) from None

    async def _retry_after_seconds(
        self, key: str, now_ms: int, window_seconds: int
    ) -> int:
        client = self._client()
        oldest = await client.zrange(key, 0, 0, withscores=True)
        if not oldest:
            return window_seconds
        _, oldest_score = oldest[0]
        seconds_until_eviction = window_seconds - int(
            (now_ms - int(oldest_score)) / 1000
        )
        return max(1, seconds_until_eviction)

    def _client(self) -> Any:
        client = self._redis.client
        if client is None:
            abuse_velocity_redis_errors_total.inc()
            raise SignupRateLimitExceededError(
                counter_key="redis:unavailable",
                retry_after_seconds=60,
            )
        return client
