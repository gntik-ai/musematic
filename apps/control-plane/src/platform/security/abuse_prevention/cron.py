"""Background jobs for the abuse-prevention bounded context (UPD-050).

Two jobs:

1. ``snapshot_velocity_counters`` (every 60 s) — read each Redis
   sorted-set into the ``signup_velocity_counters`` PostgreSQL table
   so a Redis restart can be warmed from the durable record per
   research R2.

2. ``sync_disposable_email_list`` (weekly) — pull
   `disposable-email-domains/index.json` and update the database
   per research R3, with the 7-day soak window for removals.

Both jobs are registered into the FastAPI lifespan by the runtime
profile selector (T077 hand-off). They are wired here as plain async
functions so they can be unit-tested without APScheduler.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.logging import get_logger
from platform.security.abuse_prevention.disposable_emails import DisposableEmailService
from platform.security.abuse_prevention.models import DisposableEmailDomain

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)

UPSTREAM_INDEX_URL = (
    "https://raw.githubusercontent.com/disposable-email-domains/"
    "disposable-email-domains/main/disposable_email_blocklist.conf"
)
SOAK_WINDOW = timedelta(days=7)


async def snapshot_velocity_counters() -> None:
    """Periodic snapshot of Redis velocity counters into PostgreSQL.

    Phase-2 placeholder — full implementation lands when the runtime
    profile selector wires it. Intentionally a no-op here so the cron
    table is operationally observable from day 1.
    """
    LOGGER.debug("abuse.velocity.snapshot.tick")
    # TODO(UPD-050 follow-up): scan Redis keys with `KEYS abuse:vel:*`
    # (or SCAN), call ZCARD on each, upsert into signup_velocity_counters
    # with the current window-start. The current Redis-only path is
    # production-safe; the snapshot is for durability across Redis
    # restarts. Operators can disable this cron if Redis HA is in
    # place and the PostgreSQL snapshot is not required.


async def sync_disposable_email_list(
    session: AsyncSession,
    *,
    disposable: DisposableEmailService,
    timeout_seconds: float = 30.0,
) -> dict[str, int]:
    """Pull the upstream disposable-email list and apply diffs.

    Returns a counts dict ``{added, marked_for_removal, removed}`` for
    structured logging / metrics.
    """
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(UPSTREAM_INDEX_URL)
        response.raise_for_status()
    upstream: set[str] = {
        line.strip().lower()
        for line in response.text.splitlines()
        if line.strip() and not line.startswith("#")
    }

    existing_result = await session.execute(
        select(
            DisposableEmailDomain.domain,
            DisposableEmailDomain.pending_removal_at,
        )
    )
    existing: dict[str, datetime | None] = {
        row[0]: row[1] for row in existing_result.all()
    }

    now = datetime.now(tz=UTC)
    counts = {"added": 0, "marked_for_removal": 0, "removed": 0}

    # Adds — domains in upstream but not yet recorded.
    for domain in sorted(upstream - existing.keys()):
        session.add(
            DisposableEmailDomain(
                domain=domain, source="upstream"
            )
        )
        counts["added"] += 1

    # Removals: mark with pending_removal_at if absent from upstream
    # (and not already pending). Drop rows whose pending_removal_at is
    # in the past (the 7-day soak window has elapsed).
    for domain, pending in list(existing.items()):
        if domain in upstream:
            # If it had been marked for removal but is back upstream,
            # clear the pending marker.
            if pending is not None:
                row = await _get_row(session, domain)
                if row is not None:
                    row.pending_removal_at = None
            continue
        if pending is None:
            row = await _get_row(session, domain)
            if row is not None:
                row.pending_removal_at = now + SOAK_WINDOW
                counts["marked_for_removal"] += 1
        elif pending < now:
            row = await _get_row(session, domain)
            if row is not None:
                await session.delete(row)
                counts["removed"] += 1

    await session.commit()
    await disposable.refresh()
    LOGGER.info("abuse.disposable_email.sync_complete", extra=counts)
    return counts


async def _get_row(
    session: AsyncSession, domain: str
) -> DisposableEmailDomain | None:
    result = await session.execute(
        select(DisposableEmailDomain).where(
            DisposableEmailDomain.domain == domain
        )
    )
    return result.scalar_one_or_none()
