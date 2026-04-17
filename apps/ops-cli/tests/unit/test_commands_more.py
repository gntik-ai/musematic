from __future__ import annotations

import asyncio
import io
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.main import app
from platform_cli.models import (
    BackupManifest,
    BackupStatus,
    CheckStatus,
    DiagnosticReport,
)
from platform_cli.output.structured import set_output_stream


def _config(tmp_path: Path) -> InstallerConfig:
    return InstallerConfig(data_dir=tmp_path, deployment_mode=DeploymentMode.LOCAL)


def test_admin_commands_cover_list_create_status_stop(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "platform_cli.commands.admin.load_runtime_config",
        lambda ctx, **overrides: _config(tmp_path),
    )
    monkeypatch.setattr(
        "platform_cli.commands.admin._request",
        lambda *args, **kwargs: asyncio.sleep(
            0,
            result=SimpleNamespace(
                json=lambda: {
                    "items": [{"email": "a@example.com", "status": "pending", "roles": ["admin"]}]
                }
            ),
        ),
    )
    monkeypatch.setattr("platform_cli.commands.admin.LocalInstaller.stop", lambda path: True)
    monkeypatch.setattr(
        "platform_cli.commands.admin.DiagnosticRunner.run",
        lambda self: asyncio.sleep(
            0,
            result=DiagnosticReport(
                deployment_mode=DeploymentMode.LOCAL,
                checked_at="2026-01-01T00:00:00+00:00",
                duration_seconds=0.1,
                overall_status=CheckStatus.HEALTHY,
                checks=[],
            ),
        ),
    )

    assert runner.invoke(app, ["admin", "users", "list"]).exit_code == 0
    assert (
        runner.invoke(
            app, ["admin", "users", "create", "a@example.com", "--role", "admin"]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["admin", "status"]).exit_code == 0
    assert runner.invoke(app, ["admin", "stop"]).exit_code == 0


def test_backup_commands_cover_create_restore_and_json(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    config = _config(tmp_path)
    monkeypatch.setattr(
        "platform_cli.commands.backup.load_runtime_config", lambda ctx, **overrides: config
    )

    manifest = BackupManifest(
        backup_id="bkp-1",
        tag="nightly",
        sequence_number=1,
        deployment_mode=DeploymentMode.LOCAL,
        status=BackupStatus.COMPLETED,
        created_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:10+00:00",
        artifacts=[],
        total_size_bytes=0,
        storage_location=str(tmp_path),
    )
    monkeypatch.setattr(
        "platform_cli.commands.backup.BackupOrchestrator.create",
        lambda self, tag, stores_filter=None, force=False: asyncio.sleep(0, result=manifest),
    )
    monkeypatch.setattr(
        "platform_cli.commands.backup.BackupOrchestrator.restore",
        lambda self, backup_id, stores_filter=None, verify_only=False: asyncio.sleep(
            0, result=True
        ),
    )
    monkeypatch.setattr(
        "platform_cli.commands.backup.BackupOrchestrator.list", lambda self, limit=20: [manifest]
    )

    assert runner.invoke(app, ["backup", "create", "--tag", "nightly"]).exit_code == 0
    assert runner.invoke(app, ["backup", "restore", "bkp-1", "--verify-only"]).exit_code == 0
    stream = io.StringIO()
    set_output_stream(stream)
    assert runner.invoke(app, ["--json", "backup", "list"]).exit_code == 0
    assert '"stage": "backup-list"' in stream.getvalue()


def test_install_variants_and_upgrade_paths(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    config = _config(tmp_path)
    monkeypatch.setattr(
        "platform_cli.commands.install.load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )
    monkeypatch.setattr(
        "platform_cli.commands.upgrade.load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )

    class FakeInstaller:
        def __init__(self, *args, **kwargs) -> None:
            self.config = config

        async def run(self):
            return SimpleNamespace(
                duration_seconds=1.0,
                admin_email="admin@example.com",
                admin_password="Secret123!",
                deployment_mode=DeploymentMode.LOCAL,
                model_dump=lambda mode="json": {"ok": True},
            )

    monkeypatch.setattr("platform_cli.commands.install.KubernetesInstaller", FakeInstaller)
    monkeypatch.setattr("platform_cli.commands.install.DockerComposeInstaller", FakeInstaller)
    monkeypatch.setattr("platform_cli.commands.install.SwarmInstaller", FakeInstaller)
    monkeypatch.setattr("platform_cli.commands.install.IncusInstaller", FakeInstaller)
    monkeypatch.setattr(
        "platform_cli.commands.install.HelmRunner.uninstall", lambda self, release, namespace: None
    )

    assert runner.invoke(app, ["install", "kubernetes", "--dry-run"]).exit_code == 0
    assert runner.invoke(app, ["install", "docker"]).exit_code == 0
    assert runner.invoke(app, ["install", "swarm"]).exit_code == 0
    assert runner.invoke(app, ["install", "incus"]).exit_code == 0
    assert (
        runner.invoke(app, ["install", "uninstall", "--deployment-mode", "kubernetes"]).exit_code
        == 0
    )

    monkeypatch.setattr(
        "platform_cli.commands.upgrade._release_versions",
        lambda: {"platform-postgresql": {"app_version": "0.1.0"}},
    )
    monkeypatch.setattr(
        "platform_cli.commands.upgrade.BackupOrchestrator.create",
        lambda self, tag, force=False: asyncio.sleep(0, result=SimpleNamespace()),
    )
    monkeypatch.setattr(
        "platform_cli.commands.upgrade.HelmRunner.install", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "platform_cli.commands.upgrade.HelmRunner.wait_for_ready", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "platform_cli.commands.upgrade.DiagnosticRunner.run",
        lambda self: asyncio.sleep(
            0,
            result=DiagnosticReport(
                deployment_mode=DeploymentMode.LOCAL,
                checked_at="2026-01-01T00:00:00+00:00",
                duration_seconds=0.1,
                overall_status=CheckStatus.HEALTHY,
                checks=[],
            ),
        ),
    )

    assert runner.invoke(app, ["upgrade", "--target-version", "1.2.3"]).exit_code == 0


def test_upgrade_failure_exits_partial(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    config = _config(tmp_path)
    monkeypatch.setattr(
        "platform_cli.commands.upgrade.load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )
    monkeypatch.setattr("platform_cli.commands.upgrade._release_versions", dict)
    monkeypatch.setattr(
        "platform_cli.commands.upgrade.HelmRunner.install",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    result = runner.invoke(app, ["upgrade", "--target-version", "1.2.3"])
    assert result.exit_code == 3
