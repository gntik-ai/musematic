"""Repository helpers for the abuse-prevention bounded context (UPD-050 T024).

Today this module exposes the trusted-source allowlist read path with a
60-second in-memory cache. The cache uses the same pattern as
``DisposableEmailService`` so every read on the signup hot path is a
constant-time frozenset lookup.
"""

from __future__ import annotations

import time
from platform.common.logging import get_logger
from platform.security.abuse_prevention.models import TrustedSourceAllowlistEntry

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)
CACHE_REFRESH_SECONDS = 60


class TrustedSourceAllowlistRepository:
    """Per-process cache of trusted IPs and ASNs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cache: frozenset[tuple[str, str]] = frozenset()
        self._cache_loaded_at: float = 0.0

    async def is_trusted_ip(self, ip: str | None) -> bool:
        if not ip:
            return False
        await self._maybe_refresh()
        return ("ip", ip) in self._cache

    async def is_trusted_asn(self, asn: str | None) -> bool:
        if not asn:
            return False
        await self._maybe_refresh()
        return ("asn", asn) in self._cache

    async def refresh(self) -> None:
        await self._refresh_cache()

    async def _maybe_refresh(self) -> None:
        now = time.monotonic()
        if now - self._cache_loaded_at < CACHE_REFRESH_SECONDS and self._cache_loaded_at > 0:
            return
        await self._refresh_cache()

    async def _refresh_cache(self) -> None:
        result = await self._session.execute(
            select(
                TrustedSourceAllowlistEntry.kind,
                TrustedSourceAllowlistEntry.value,
            )
        )
        self._cache = frozenset((row[0], row[1]) for row in result.all())
        self._cache_loaded_at = time.monotonic()
        LOGGER.debug(
            "trusted_source_allowlist_refreshed",
            extra={"count": len(self._cache)},
        )
