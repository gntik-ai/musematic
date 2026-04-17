from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from platform_cli.backup.manifest import BackupManifestManager
from platform_cli.backup.scheduler import BackupScheduler
from platform_cli.backup.stores.common import build_artifact
from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.models import BackupStatus


def _config(tmp_path: Path) -> InstallerConfig:
    return InstallerConfig(deployment_mode=DeploymentMode.LOCAL, data_dir=tmp_path)


@pytest.mark.asyncio
async def test_backup_scheduler_run_once_creates_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scheduler = BackupScheduler(_config(tmp_path), storage_root=tmp_path / "backups")

    artifact_path = tmp_path / "backups" / "bkp-1" / "redis" / "redis.rdb"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("redis", encoding="utf-8")
    artifact = build_artifact(
        store="redis",
        display_name="Redis",
        path=artifact_path,
        format_name="rdb",
        duration_seconds=1.0,
    )
    manifest = scheduler.orchestrator.manifests.create(
        DeploymentMode.LOCAL,
        "scheduled",
        [artifact],
        BackupStatus.COMPLETED,
    )

    async def fake_create(
        tag: str | None,
        stores_filter: set[str] | None = None,
        *,
        force: bool = False,
        headless: bool = False,
    ) -> object:
        return manifest.model_copy(update={"tag": tag})

    monkeypatch.setattr(scheduler.orchestrator, "create", fake_create)

    async def fake_prune(retention_days: int, excluded_ids: set[str]) -> int:
        assert excluded_ids == {manifest.backup_id}
        return 2

    monkeypatch.setattr(scheduler, "_prune_with_exclusions", fake_prune)

    result = await scheduler.run_once(retention_days=30)

    assert result.backup_id == manifest.backup_id
    assert result.status == BackupStatus.COMPLETED
    assert result.pruned_count == 2


@pytest.mark.asyncio
async def test_backup_scheduler_prune_deletes_old_manifests(tmp_path: Path) -> None:
    scheduler = BackupScheduler(_config(tmp_path), storage_root=tmp_path / "backups")
    manager = BackupManifestManager(tmp_path / "backups")

    for index in range(3):
        artifact_path = tmp_path / "backups" / f"bkp-{index}" / "redis" / "redis.rdb"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("redis", encoding="utf-8")
        artifact = build_artifact(
            store="redis",
            display_name="Redis",
            path=artifact_path,
            format_name="rdb",
            duration_seconds=1.0,
        )
        manifest = manager.create(
            DeploymentMode.LOCAL,
            f"old-{index}",
            [artifact],
            BackupStatus.COMPLETED,
        )
        manager.save(
            manifest.model_copy(
                update={"created_at": (datetime.now(UTC) - timedelta(days=5)).isoformat()}
            )
        )

    pruned = await scheduler._prune(retention_days=1)

    assert pruned == 3
    assert manager.list(limit=10_000) == []


@pytest.mark.asyncio
async def test_backup_scheduler_lock_failure_returns_failed_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scheduler = BackupScheduler(_config(tmp_path), storage_root=tmp_path / "backups")

    async def fake_create(
        tag: str | None,
        stores_filter: set[str] | None = None,
        *,
        force: bool = False,
        headless: bool = False,
    ) -> object:
        raise RuntimeError("backup lock could not be acquired")

    monkeypatch.setattr(scheduler.orchestrator, "create", fake_create)

    result = await scheduler.run_once(retention_days=30)

    assert result.status == BackupStatus.FAILED
    assert "lock could not be acquired" in (result.error or "")
