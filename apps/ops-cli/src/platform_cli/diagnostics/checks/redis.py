"""Redis diagnostic check."""

from __future__ import annotations

import inspect
from time import perf_counter

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class RedisCheck:
    """Verify Redis connectivity with ``PING``."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.name = "redis"

    async def run(self) -> DiagnosticCheck:
        from redis.asyncio import Redis

        started = perf_counter()
        client = Redis.from_url(self.url, decode_responses=True)
        try:
            ping_result = client.ping()
            if inspect.isawaitable(ping_result):
                await ping_result
        except Exception as exc:
            return DiagnosticCheck(
                component="redis",
                display_name="Redis",
                category=ComponentCategory.DATA_STORE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation="Check Redis service health and network access.",
            )
        finally:
            await client.aclose()
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component="redis",
            display_name="Redis",
            category=ComponentCategory.DATA_STORE,
            status=CheckStatus.HEALTHY,
            latency_ms=latency_ms,
        )
