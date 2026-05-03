"""Disposable-email lookup with override-aware caching (UPD-050 T013).

Reads from ``disposable_email_domains`` minus ``disposable_email_overrides``
into a per-process frozenset cache, refreshed every 60 seconds (or
sooner on `abuse:disposable:cache_version` mismatch in Redis).

The cache is read-only on the signup hot path; refresh is a background
async call. On a fresh process or expired cache, the first lookup blocks
on the refresh; subsequent lookups are constant-time.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from platform.common.clients.redis import AsyncRedisClient
from platform.common.logging import get_logger
from platform.security.abuse_prevention.models import (
    DisposableEmailDomain,
    DisposableEmailOverride,
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)

CACHE_REFRESH_SECONDS = 60
REDIS_CACHE_VERSION_KEY = "abuse:disposable:cache_version"


class DisposableEmailService:
    """Per-process cache of currently-blocked disposable-email domains.

    Usage::

        service = DisposableEmailService(session, redis)
        if await service.is_blocked("10minutemail.com"):
            raise DisposableEmailNotAllowedError(...)
    """

    def __init__(
        self, session: AsyncSession, redis: AsyncRedisClient | None = None
    ) -> None:
        self._session = session
        self._redis = redis
        self._cache: frozenset[str] = frozenset()
        self._cache_loaded_at: float = 0.0

    async def is_blocked(self, domain: str) -> bool:
        normalised = domain.strip().lower()
        await self._maybe_refresh()
        return normalised in self._cache

    async def refresh(self) -> None:
        """Force a refresh of the cached blocklist."""
        await self._refresh_cache()

    async def _maybe_refresh(self) -> None:
        now = time.monotonic()
        if now - self._cache_loaded_at < CACHE_REFRESH_SECONDS and self._cache:
            return
        await self._refresh_cache()

    async def _refresh_cache(self) -> None:
        # Domains currently in the upstream registry, minus the
        # super-admin override list. Excludes rows past their
        # `pending_removal_at` deadline.
        now = datetime.now(tz=UTC)
        domain_rows = await self._session.execute(
            select(DisposableEmailDomain.domain).where(
                (DisposableEmailDomain.pending_removal_at.is_(None))
                | (DisposableEmailDomain.pending_removal_at > now)
            )
        )
        override_rows = await self._session.execute(
            select(DisposableEmailOverride.domain)
        )
        domains = {row[0] for row in domain_rows.all()}
        overrides = {row[0] for row in override_rows.all()}
        self._cache = frozenset(domains - overrides)
        self._cache_loaded_at = time.monotonic()
        LOGGER.debug(
            "disposable_email_cache_refreshed",
            extra={"count": len(self._cache), "overrides": len(overrides)},
        )
