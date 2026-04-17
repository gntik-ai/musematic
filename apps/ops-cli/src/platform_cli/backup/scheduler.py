"""Scheduled backup execution and retention pruning."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from platform_cli.backup.orchestrator import BackupOrchestrator
from platform_cli.config import InstallerConfig
from platform_cli.models import BackupStatus, utc_now_iso
from platform_cli.output.console import get_console


@dataclass(slots=True)
class ScheduledBackupResult:
    """Outcome of one scheduled backup execution."""

    run_at: str
    backup_id: str | None
    status: BackupStatus
    error: str | None
    pruned_count: int


class BackupScheduler:
    """Run backups on a schedule and prune expired manifests."""

    def __init__(self, config: InstallerConfig, storage_root: Path | None = None) -> None:
        self.config = config
        self.orchestrator = BackupOrchestrator(config, storage_root=storage_root)

    async def run_once(self, retention_days: int) -> ScheduledBackupResult:
        """Execute one scheduled backup and prune expired manifests."""

        run_at = utc_now_iso()
        sequence_number = len(self.orchestrator.manifests.list(limit=10_000)) + 1
        tag = f"scheduled-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{sequence_number:03d}"

        try:
            manifest = await self.orchestrator.create(tag, force=False, headless=True)
        except Exception as exc:
            return ScheduledBackupResult(
                run_at=run_at,
                backup_id=None,
                status=BackupStatus.FAILED,
                error=str(exc),
                pruned_count=0,
            )

        pruned_count = await self._prune_with_exclusions(retention_days, {manifest.backup_id})
        return ScheduledBackupResult(
            run_at=run_at,
            backup_id=manifest.backup_id,
            status=manifest.status,
            error=None,
            pruned_count=pruned_count,
        )

    def start(self, cron_expression: str, retention_days: int) -> None:
        """Start the blocking APScheduler loop."""

        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            self._run_scheduled_job,
            trigger=CronTrigger.from_crontab(cron_expression),
            kwargs={"retention_days": retention_days},
            id="platform-backup-schedule",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        get_console().print(
            f"Backup scheduler started with cron '{cron_expression}' "
            f"and retention {retention_days}d"
        )
        scheduler.start()

    async def _prune(self, retention_days: int) -> int:
        """Delete manifests older than the retention window."""

        return await self._prune_with_exclusions(retention_days, set())

    def _run_scheduled_job(self, retention_days: int) -> None:
        result = asyncio.run(self.run_once(retention_days=retention_days))
        message = (
            f"scheduled backup {result.backup_id or '-'} "
            f"finished with status {result.status.value}; "
            f"pruned {result.pruned_count}"
        )
        if result.error:
            message = f"{message}; error: {result.error}"
        get_console().print(message)

    async def _prune_with_exclusions(self, retention_days: int, excluded_ids: set[str]) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=max(retention_days, 0))
        pruned_count = 0
        for manifest in self.orchestrator.manifests.list(limit=10_000):
            if manifest.backup_id in excluded_ids:
                continue
            created_at = datetime.fromisoformat(manifest.created_at)
            if created_at >= cutoff:
                continue
            self.orchestrator.manifests.delete(manifest.backup_id)
            shutil.rmtree(self.orchestrator.storage_root / manifest.backup_id, ignore_errors=True)
            pruned_count += 1
        return pruned_count
