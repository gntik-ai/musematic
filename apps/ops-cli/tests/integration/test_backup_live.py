from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from platform_cli.backup.orchestrator import BackupOrchestrator, BackupVerificationError
from platform_cli.backup.scheduler import BackupScheduler
from platform_cli.backup.stores.common import build_artifact
from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.locking.file import FileLock
from platform_cli.models import BackupArtifact, BackupStatus


class FakeStore:
    def __init__(self, name: str, backup_calls: list[str], restore_calls: list[str]) -> None:
        self.name = name
        self.backup_calls = backup_calls
        self.restore_calls = restore_calls

    async def backup(self, output_dir: Path) -> BackupArtifact:
        self.backup_calls.append(self.name)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{self.name}.bin"
        path.write_text(self.name, encoding="utf-8")
        return build_artifact(
            store=self.name,
            display_name=self.name.title(),
            path=path,
            format_name="raw",
            duration_seconds=1.0,
        )

    async def restore(self, artifact_path: Path) -> bool:
        assert artifact_path.exists()
        self.restore_calls.append(self.name)
        return True


def _config(tmp_path: Path) -> InstallerConfig:
    return InstallerConfig(deployment_mode=DeploymentMode.LOCAL, data_dir=tmp_path)


def _stores(backup_calls: list[str], restore_calls: list[str]) -> dict[str, FakeStore]:
    return {
        name: FakeStore(name, backup_calls, restore_calls)
        for name in BackupOrchestrator.BACKUP_ORDER
    }


async def _disable_active_execution_check(
    monkeypatch: pytest.MonkeyPatch, orchestrator: BackupOrchestrator
) -> None:
    async def no_active_executions() -> bool:
        return False

    monkeypatch.setattr(orchestrator, "_has_active_executions", no_active_executions)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    backup_calls: list[str] = []
    restore_calls: list[str] = []
    orchestrator = BackupOrchestrator(_config(tmp_path), storage_root=tmp_path / "backups")
    monkeypatch.setattr(orchestrator, "_stores", lambda: _stores(backup_calls, restore_calls))
    await _disable_active_execution_check(monkeypatch, orchestrator)

    manifest = await orchestrator.create(None, force=False, headless=True)
    assert await orchestrator.restore(manifest.backup_id, verify_only=True, headless=True) is True
    assert await orchestrator.restore(manifest.backup_id, verify_only=False, headless=True) is True
    assert backup_calls == list(BackupOrchestrator.BACKUP_ORDER)
    assert restore_calls == list(BackupOrchestrator.RESTORE_ORDER)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_partial_restore(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    backup_calls: list[str] = []
    restore_calls: list[str] = []
    orchestrator = BackupOrchestrator(_config(tmp_path), storage_root=tmp_path / "backups")
    monkeypatch.setattr(orchestrator, "_stores", lambda: _stores(backup_calls, restore_calls))
    await _disable_active_execution_check(monkeypatch, orchestrator)

    manifest = await orchestrator.create("partial", force=False, headless=True)
    await orchestrator.restore(
        manifest.backup_id,
        stores_filter={"redis"},
        verify_only=False,
        headless=True,
    )

    assert restore_calls == ["redis"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_checksum_failure_aborts_restore(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backup_calls: list[str] = []
    restore_calls: list[str] = []
    orchestrator = BackupOrchestrator(_config(tmp_path), storage_root=tmp_path / "backups")
    monkeypatch.setattr(orchestrator, "_stores", lambda: _stores(backup_calls, restore_calls))
    await _disable_active_execution_check(monkeypatch, orchestrator)

    manifest = await orchestrator.create("verify-fail", force=False, headless=True)
    Path(manifest.artifacts[0].path).write_text("corrupted", encoding="utf-8")

    with pytest.raises(BackupVerificationError):
        await orchestrator.restore(manifest.backup_id, verify_only=False, headless=True)

    assert restore_calls == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lock_prevents_concurrent_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backup_calls: list[str] = []
    restore_calls: list[str] = []
    config = _config(tmp_path)
    orchestrator = BackupOrchestrator(config, storage_root=tmp_path / "backups")
    monkeypatch.setattr(orchestrator, "_stores", lambda: _stores(backup_calls, restore_calls))
    await _disable_active_execution_check(monkeypatch, orchestrator)

    held_lock = FileLock(config.data_dir / "backup.lock")
    assert held_lock.acquire() is True
    try:
        with pytest.raises(RuntimeError, match="backup lock could not be acquired"):
            await orchestrator.create("locked", force=False, headless=True)
    finally:
        held_lock.release()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scheduler_prunes_old_manifests(tmp_path: Path) -> None:
    scheduler = BackupScheduler(_config(tmp_path), storage_root=tmp_path / "backups")
    manager = scheduler.orchestrator.manifests

    for index in range(5):
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
                update={"created_at": (datetime.now(UTC) - timedelta(days=3)).isoformat()}
            )
        )

    assert await scheduler._prune(retention_days=1) == 5
