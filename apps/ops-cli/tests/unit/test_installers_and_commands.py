from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.installers.base import AbstractInstaller, InstallerStep
from platform_cli.installers.docker import DockerComposeInstaller
from platform_cli.installers.incus import IncusInstaller
from platform_cli.installers.kubernetes import KubernetesInstaller
from platform_cli.installers.local import LocalInstaller
from platform_cli.installers.swarm import SwarmInstaller
from platform_cli.main import app
from platform_cli.models import CheckStatus, DiagnosticReport, InstallerResult
from platform_cli.output.structured import set_output_stream
from platform_cli.secrets.generator import generate_secrets


class DummyInstaller(AbstractInstaller):
    def __init__(self, config: InstallerConfig) -> None:
        super().__init__(config)
        self.calls: list[str] = []

    def build_steps(self) -> list[InstallerStep]:
        return [
            InstallerStep("preflight", "preflight", self.preflight),
            InstallerStep("migrate", "migrate", self.migrate),
        ]

    async def preflight(self) -> None:
        self.calls.append("preflight")

    async def migrate(self) -> None:
        self.calls.append("migrate")


@pytest.mark.asyncio
async def test_abstract_installer_tracks_steps(tmp_path: Path) -> None:
    config = InstallerConfig(data_dir=tmp_path)
    installer = DummyInstaller(config)

    result = await installer.run()

    assert installer.calls == ["preflight", "migrate"]
    assert result.deployment_mode == DeploymentMode.KUBERNETES
    assert result.checkpoint_path is not None


@pytest.mark.asyncio
async def test_kubernetes_installer_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = InstallerConfig(data_dir=tmp_path)
    installer = KubernetesInstaller(config, dry_run=True, skip_migrations=True)
    secrets = generate_secrets(config.secrets)

    monkeypatch.setattr(installer.lock, "acquire", lambda namespace, holder_id: True)
    monkeypatch.setattr(installer.lock, "release", lambda namespace, holder_id: None)

    async def passed_summary() -> SimpleNamespace:
        return SimpleNamespace(passed=True, results=[])

    monkeypatch.setattr(
        "platform_cli.installers.kubernetes.PreflightRunner.run",
        lambda self: passed_summary(),
    )
    monkeypatch.setattr("platform_cli.installers.kubernetes.generate_secrets", lambda cfg: secrets)
    monkeypatch.setattr(
        "platform_cli.installers.kubernetes.store_secrets_kubernetes",
        lambda bundle, namespace: None,
    )
    monkeypatch.setattr("platform_cli.installers.kubernetes._run", lambda command: None)
    monkeypatch.setattr("platform_cli.installers.kubernetes.render_values", lambda *args: {})
    monkeypatch.setattr(
        "platform_cli.installers.kubernetes.write_values_file",
        lambda values, path: path,
    )
    monkeypatch.setattr(installer.helm_runner, "install", lambda *args, **kwargs: None)
    monkeypatch.setattr(installer.helm_runner, "wait_for_ready", lambda *args, **kwargs: None)

    report = DiagnosticReport(
        deployment_mode=DeploymentMode.KUBERNETES,
        checked_at="2026-01-01T00:00:00+00:00",
        duration_seconds=1.0,
        overall_status=CheckStatus.HEALTHY,
        checks=[],
    )
    monkeypatch.setattr(
        "platform_cli.installers.kubernetes.DiagnosticRunner.run",
        lambda self: asyncio.sleep(0, result=report),
    )

    result = await installer.run()

    assert installer.generated_secrets is not None
    assert result.admin_email == config.admin.email


@pytest.mark.asyncio
async def test_local_installer_run_and_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = InstallerConfig(data_dir=tmp_path)
    installer = LocalInstaller(config, port=8010, skip_migrations=True)
    secrets = generate_secrets(config.secrets)

    monkeypatch.setattr(installer.lock, "acquire", lambda: True)
    monkeypatch.setattr(installer.lock, "release", lambda: None)

    async def passed_summary() -> SimpleNamespace:
        return SimpleNamespace(passed=True, results=[])

    monkeypatch.setattr(
        "platform_cli.installers.local.PreflightRunner.run",
        lambda self: passed_summary(),
    )
    monkeypatch.setattr("platform_cli.installers.local.generate_secrets", lambda cfg: secrets)
    monkeypatch.setattr(
        "platform_cli.installers.local.store_secrets_local",
        lambda bundle, data_dir: data_dir / "generated-secrets.json",
    )
    next_pid = 120

    def fake_which(binary: str) -> str | None:
        if binary == "docker":
            return "/usr/bin/docker"
        return None

    class FakeProcess:
        def __init__(self) -> None:
            nonlocal next_pid
            self.pid = next_pid
            next_pid += 1

    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(),
    )
    monkeypatch.setattr("platform_cli.installers.local.shutil.which", fake_which)

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> SimpleNamespace:
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr("platform_cli.installers.local.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(installer, "wait_for_jaeger", lambda timeout_seconds=30: asyncio.sleep(0))
    monkeypatch.setattr(installer.migration_runner, "run_alembic", lambda url: None)
    monkeypatch.setattr(
        installer.migration_runner,
        "create_admin_user",
        lambda api_url, email, password: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        "platform_cli.installers.local.DiagnosticRunner.run",
        lambda self: asyncio.sleep(
            0,
            result=DiagnosticReport(
                deployment_mode=DeploymentMode.LOCAL,
                checked_at="2026-01-01T00:00:00+00:00",
                duration_seconds=1.0,
                overall_status=CheckStatus.HEALTHY,
                checks=[],
            ),
        ),
    )
    killed: list[int] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))

    result = await installer.run()
    assert installer.jaeger_pid_path.exists()
    stopped = LocalInstaller.stop(tmp_path)

    assert result.admin_email == config.admin.email
    assert stopped is True
    assert installer.build_local_env()["OTEL_EXPORTER_ENDPOINT"] == "http://127.0.0.1:4318"
    assert installer.checkpoint_manager.checkpoint is not None
    assert installer.checkpoint_manager.checkpoint.metadata["jaeger_runtime"] == "docker"
    assert installer.jaeger_pid_path.exists() is False
    assert killed == [121, 120]


def test_container_installers_render_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config = InstallerConfig(data_dir=tmp_path)

    docker = DockerComposeInstaller(config)
    swarm = SwarmInstaller(config)
    incus = IncusInstaller(config)

    docker.render_compose()
    swarm.render_stack()
    incus.render_profile()

    assert (tmp_path / "docker-compose.yml").exists()
    assert (tmp_path / "platform.stack.yml").exists()
    assert (tmp_path / "platform.incus.yml").exists()


def test_local_installer_steps_include_jaeger(tmp_path: Path) -> None:
    installer = LocalInstaller(InstallerConfig(data_dir=tmp_path))

    assert [step.name for step in installer.build_steps()] == [
        "preflight",
        "directories",
        "database",
        "qdrant",
        "jaeger",
        "secrets",
        "control-plane",
        "migrate",
        "admin",
        "verify",
    ]


def test_cli_commands_use_runtime_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")

    fake_result = InstallerResult(
        deployment_mode=DeploymentMode.LOCAL,
        duration_seconds=1.2,
        admin_email="admin@example.com",
        admin_password="Secret123!",
        verification_status=CheckStatus.HEALTHY,
        checkpoint_path=str(tmp_path / "checkpoint.json"),
    )

    class FakeLocalInstaller:
        def __init__(self, config: InstallerConfig, port: int, foreground: bool) -> None:
            self.config = config

        async def run(self) -> InstallerResult:
            return fake_result

    monkeypatch.setattr("platform_cli.commands.install.LocalInstaller", FakeLocalInstaller)
    install_result = runner.invoke(
        app,
        ["install", "local", "--data-dir", str(tmp_path), "--port", "8001"],
    )
    assert install_result.exit_code == 0
    assert "Install-Local completed".lower()[:7] in install_result.output.lower()

    diag_report = DiagnosticReport(
        deployment_mode=DeploymentMode.LOCAL,
        checked_at="2026-01-01T00:00:00+00:00",
        duration_seconds=0.1,
        overall_status=CheckStatus.HEALTHY,
        checks=[],
    )
    monkeypatch.setattr(
        "platform_cli.commands.diagnose.DiagnosticRunner.run",
        lambda self, timeout_per_check=5: asyncio.sleep(0, result=diag_report),
    )
    monkeypatch.setattr(
        "platform_cli.commands.diagnose.DiagnosticRunner.auto_detect_mode",
        lambda config: DeploymentMode.LOCAL,
    )
    stream = __import__("io").StringIO()
    set_output_stream(stream)
    diagnose_result = runner.invoke(app, ["--json", "diagnose"])
    assert diagnose_result.exit_code == 0
    assert '"stage": "diagnose"' in stream.getvalue()

    monkeypatch.setattr(
        "platform_cli.commands.backup.BackupOrchestrator.list",
        lambda self, limit=20: [],
    )
    monkeypatch.setattr(
        "platform_cli.commands.backup.load_runtime_config",
        lambda ctx, **overrides: InstallerConfig(data_dir=tmp_path),
    )
    backup_result = runner.invoke(app, ["backup", "list"])
    assert backup_result.exit_code == 0

    monkeypatch.setattr(
        "platform_cli.commands.upgrade._release_versions",
        dict,
    )
    upgrade_result = runner.invoke(app, ["upgrade", "--dry-run", "--target-version", "1.2.3"])
    assert upgrade_result.exit_code == 0

    monkeypatch.setattr(
        "platform_cli.commands.admin.DiagnosticRunner.run",
        lambda self: asyncio.sleep(0, result=diag_report),
    )
    status_result = runner.invoke(app, ["admin", "status"])
    assert status_result.exit_code == 0


def test_install_uninstall_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "platform.pid").write_text("123", encoding="utf-8")

    monkeypatch.setattr("platform_cli.commands.install.LocalInstaller.stop", lambda path: True)

    result = runner.invoke(
        app,
        ["install", "uninstall", "--deployment-mode", "local", "--force"],
    )

    assert result.exit_code == 0
