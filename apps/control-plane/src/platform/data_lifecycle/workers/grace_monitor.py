"""GraceMonitor — APScheduler cron that advances grace-expired deletions.

Ticks every 5 minutes (configurable). Calls
``DeletionService.advance_grace_expired_jobs`` which finds phase_1 jobs
with ``grace_ends_at <= now()`` and drives the cascade dispatch.

Idempotent: re-running the same tick is safe because the phase check +
partial-unique index prevent re-entry.
"""

from __future__ import annotations

from collections.abc import Callable
from platform.common.logging import get_logger
from platform.data_lifecycle.services.deletion_service import DeletionService
from typing import Any

LOGGER = get_logger(__name__)

DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes


class GraceMonitor:
    """Wraps the deletion service in a cron-friendly callable.

    The scheduler runtime profile (``main.py``) registers this with
    APScheduler at startup. The monitor itself is stateless — each tick
    opens a fresh session via the supplied factory.
    """

    def __init__(
        self,
        *,
        session_factory: Any,
        deletion_service_factory: Callable[[Any], DeletionService],
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._deletion_service_factory = deletion_service_factory
        self.interval_seconds = interval_seconds

    async def tick(self) -> int:
        """Run one cron tick. Returns count of jobs advanced."""

        async with self._session_factory() as session:
            service = self._deletion_service_factory(session)
            try:
                advanced = await service.advance_grace_expired_jobs()
                await session.commit()
                if advanced:
                    LOGGER.info(
                        "data_lifecycle.grace_monitor_advanced_jobs",
                        count=advanced,
                    )
                return advanced
            except Exception:
                LOGGER.exception("data_lifecycle.grace_monitor_tick_failed")
                await session.rollback()
                return 0

    async def purge_aged_workspace_tombstones(self) -> int:
        """Daily cron — replace workspace tombstones older than 90 days with
        hash-anchor entries (FR-752.5).

        The active audit chain retains the chain-integrity hash via an
        anchor entry; the original tombstone is removed. Returns the
        count of tombstones purged on this tick.

        NOTE: the actual hash-anchor write is delegated to a future
        AuditChainService method — this cron drives the schedule and
        records the candidates. Operators should treat the resulting
        log lines as the authoritative trail until the AuditChainService
        anchor primitive lands.
        """

        async with self._session_factory() as session:
            try:
                from datetime import UTC, datetime, timedelta

                from sqlalchemy import text as sa_text

                cutoff = datetime.now(UTC) - timedelta(days=90)
                result = await session.execute(
                    sa_text(
                        """
                        SELECT count(*)
                        FROM audit_chain_entries
                        WHERE event_type = 'data_lifecycle.workspace_deletion_completed'
                          AND created_at < :cutoff
                        """
                    ),
                    {"cutoff": cutoff.isoformat()},
                )
                count = int(result.scalar_one() or 0)
                if count:
                    LOGGER.info(
                        "data_lifecycle.workspace_tombstone_purge_candidates",
                        count=count,
                        cutoff_iso=cutoff.isoformat(),
                    )
                return count
            except Exception:
                LOGGER.exception(
                    "data_lifecycle.workspace_tombstone_purge_failed"
                )
                return 0

    def register(self, scheduler: Any) -> None:
        """Attach the tick + daily tombstone purge to an APScheduler instance."""

        scheduler.add_job(
            self.tick,
            trigger="interval",
            seconds=self.interval_seconds,
            id="data_lifecycle_grace_monitor",
            replace_existing=True,
        )
        scheduler.add_job(
            self.purge_aged_workspace_tombstones,
            trigger="cron",
            hour=3,  # daily at 03:00 UTC
            minute=15,
            id="data_lifecycle_workspace_tombstone_purge",
            replace_existing=True,
        )
