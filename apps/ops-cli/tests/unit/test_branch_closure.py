from __future__ import annotations

import asyncio
import io
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import typer
from click import Command
from typer.testing import CliRunner

from platform_cli.backup import orchestrator as orchestrator_module
from platform_cli.backup.orchestrator import BackupOrchestrator
from platform_cli.backup.stores import clickhouse as clickhouse_module
from platform_cli.backup.stores import minio as minio_module
from platform_cli.backup.stores import neo4j as neo4j_module
from platform_cli.backup.stores import postgresql as postgresql_module
from platform_cli.backup.stores import redis as redis_store_module
from platform_cli.backup.stores.clickhouse import ClickHouseBackup
from platform_cli.backup.stores.common import build_artifact
from platform_cli.backup.stores.minio import MinIOBackup
from platform_cli.backup.stores.neo4j import Neo4jBackup
from platform_cli.backup.stores.postgresql import PostgreSQLBackup
from platform_cli.backup.stores.redis import RedisBackup
from platform_cli.checkpoint.manager import CheckpointManager, InstallStepStatus
from platform_cli.commands import admin as admin_commands
from platform_cli.commands import backup as backup_commands
from platform_cli.commands import diagnose as diagnose_commands
from platform_cli.commands import install as install_commands
from platform_cli.commands import upgrade as upgrade_commands
from platform_cli.config import DeploymentMode, ExitCode, IngressConfig, InstallerConfig
from platform_cli.constants import PLATFORM_COMPONENTS, ComponentCategory
from platform_cli.diagnostics import checker as diagnostic_checker
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.installers import docker as docker_module
from platform_cli.installers import incus as incus_module
from platform_cli.installers import local as local_module
from platform_cli.installers import swarm as swarm_module
from platform_cli.installers.base import AbstractInstaller, InstallerStep
from platform_cli.installers.docker import DockerComposeInstaller
from platform_cli.installers.incus import IncusAccessCheck, IncusInstaller
from platform_cli.installers.kubernetes import KubernetesInstaller
from platform_cli.installers.local import LocalInstaller
from platform_cli.installers.swarm import SwarmInstaller
from platform_cli.locking import file as file_lock_module
from platform_cli.main import app
from platform_cli.models import (
    AutoFixResult,
    BackupArtifact,
    BackupManifest,
    BackupStatus,
    CheckStatus,
    DiagnosticCheck,
    DiagnosticReport,
    InstallerResult,
)
from platform_cli.output.structured import set_output_stream
from platform_cli.runtime import CLIState
from platform_cli.secrets.generator import generate_secrets


def _config(tmp_path: Path, **updates: object) -> InstallerConfig:
    return InstallerConfig(data_dir=tmp_path).model_copy(update=updates)


def _context(*, json_output: bool = False) -> typer.Context:
    ctx = typer.Context(Command("test"))
    ctx.obj = CLIState(config_path=None, verbose=False, json_output=json_output, no_color=False)
    return ctx


def _report(
    deployment_mode: DeploymentMode = DeploymentMode.LOCAL,
    overall_status: CheckStatus = CheckStatus.HEALTHY,
    checks: list[DiagnosticCheck] | None = None,
) -> DiagnosticReport:
    return DiagnosticReport(
        deployment_mode=deployment_mode,
        checked_at="2026-01-01T00:00:00+00:00",
        duration_seconds=0.1,
        overall_status=overall_status,
        checks=checks or [],
    )


def _check(
    component: str,
    status: CheckStatus,
    *,
    category: ComponentCategory = ComponentCategory.DATA_STORE,
    latency_ms: float | None = None,
) -> DiagnosticCheck:
    return DiagnosticCheck(
        component=component,
        display_name=component.title(),
        category=category,
        status=status,
        latency_ms=latency_ms,
        error=None if status == CheckStatus.HEALTHY else "boom",
    )


class BranchInstaller(AbstractInstaller):
    def __init__(
        self,
        config: InstallerConfig,
        *,
        fail_step: str | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        resume: bool = False,
        skip_preflight: bool = False,
        skip_migrations: bool = False,
    ) -> None:
        super().__init__(
            config,
            checkpoint_manager=checkpoint_manager,
            resume=resume,
            skip_preflight=skip_preflight,
            skip_migrations=skip_migrations,
        )
        self.calls: list[str] = []
        self.fail_step = fail_step

    def build_steps(self) -> list[InstallerStep]:
        return [
            InstallerStep("preflight", "preflight", self.preflight),
            InstallerStep("migrate", "migrate", self.migrate),
            InstallerStep("verify", "verify", self.verify),
        ]

    def preflight(self) -> None:
        self.calls.append("preflight")
        if self.fail_step == "preflight":
            raise RuntimeError("preflight failed")

    async def migrate(self) -> None:
        self.calls.append("migrate")
        if self.fail_step == "migrate":
            raise RuntimeError("migrate failed")

    async def verify(self) -> None:
        self.calls.append("verify")
        self.diagnostic_report = _report()


class _JsonResponse:
    def __init__(self, payload: object, *, status_code: int = 200, text: str = "ok") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)


def test_run_and_module_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    import platform_cli.main as main_module

    calls: list[str] = []
    monkeypatch.setattr(main_module, "app", lambda: calls.append("run"))
    main_module.run()

    entry_calls: list[str] = []
    monkeypatch.setattr(main_module, "run", lambda: entry_calls.append("entry"))
    runpy.run_module("platform_cli.__main__", run_name="__main__")

    assert calls == ["run"]
    assert entry_calls == ["entry"]


def test_admin_request_and_authenticated_command_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request_calls: list[tuple[str, str, dict[str, str] | None, dict[str, object] | None]] = []

    class RequestClient:
        async def __aenter__(self) -> RequestClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def request(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            json: dict[str, object] | None = None,
            params: dict[str, object] | None = None,
        ) -> _JsonResponse:
            request_calls.append((method, url, headers, params))
            return _JsonResponse({"items": []})

    monkeypatch.setattr(admin_commands.httpx, "AsyncClient", lambda timeout=10.0: RequestClient())

    response = asyncio.run(
        admin_commands._request(
            "GET",
            "http://api.test/users",
            headers={"Authorization": "Bearer token"},
            params={"status": "pending"},
        )
    )
    assert response.json() == {"items": []}

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    config = _config(
        tmp_path,
        api_base_url="http://api.test",
        auth_token="token",
    )
    monkeypatch.setattr(
        admin_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )

    command_calls: list[tuple[str, str, dict[str, str] | None, dict[str, object] | None]] = []

    async def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> SimpleNamespace:
        command_calls.append((method, url, headers, params or json))
        payload = (
            {
                "items": [
                    {
                        "invitee_email": "invitee@example.com",
                        "status": "accepted",
                        "roles": ["admin"],
                    }
                ]
            }
            if method == "GET"
            else {"invited": True}
        )
        return SimpleNamespace(json=lambda: payload)

    monkeypatch.setattr(admin_commands, "_request", fake_request)
    monkeypatch.setattr(
        admin_commands,
        "generate_secrets",
        lambda secrets: SimpleNamespace(admin_password="Secret123!"),
    )

    list_result = runner.invoke(
        app,
        ["admin", "users", "list", "--role", "admin", "--status", "accepted"],
    )
    create_result = runner.invoke(
        app,
        ["admin", "users", "create", "invitee@example.com", "--role", "admin"],
    )

    assert list_result.exit_code == 0
    assert create_result.exit_code == 0
    assert admin_commands._headers(config) == {"Authorization": "Bearer token"}
    assert command_calls[0][1].endswith("/api/v1/accounts/invitations")
    assert command_calls[0][3] == {"role": "admin", "status": "accepted"}
    assert command_calls[1][2] == {"Authorization": "Bearer token"}


def test_admin_failure_and_stop_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    config = _config(tmp_path)
    monkeypatch.setattr(
        admin_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )

    async def boom(*args: object, **kwargs: object) -> SimpleNamespace:
        raise RuntimeError("request failed")

    monkeypatch.setattr(admin_commands, "_request", boom)
    list_result = runner.invoke(app, ["admin", "users", "list"])

    monkeypatch.setattr(admin_commands.LocalInstaller, "stop", lambda data_dir: False)
    stop_result = runner.invoke(app, ["admin", "stop"])

    assert list_result.exit_code == int(ExitCode.GENERAL_ERROR.value)
    assert stop_result.exit_code == int(ExitCode.GENERAL_ERROR.value)


def test_backup_command_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert backup_commands._parse_stores(None) is None
    assert backup_commands._parse_stores(" , ") is None
    assert backup_commands._parse_stores("redis, kafka") == {"redis", "kafka"}

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    config = _config(tmp_path)
    monkeypatch.setattr(
        backup_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )

    manifest = BackupManifest(
        backup_id="bkp-1",
        tag="nightly",
        sequence_number=1,
        deployment_mode=DeploymentMode.LOCAL,
        status=BackupStatus.COMPLETED,
        created_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:05+00:00",
        artifacts=[],
        total_size_bytes=0,
        storage_location=str(tmp_path),
    )

    async def create_ok(
        tag: str | None,
        stores_filter: set[str] | None = None,
        *,
        force: bool = False,
    ) -> BackupManifest:
        assert tag == "nightly"
        assert stores_filter == {"redis"}
        assert force is True
        return manifest

    restore_calls: list[tuple[str, set[str] | None, bool]] = []

    async def restore_ok(
        backup_id: str,
        stores_filter: set[str] | None = None,
        *,
        verify_only: bool = False,
    ) -> bool:
        restore_calls.append((backup_id, stores_filter, verify_only))
        return True

    monkeypatch.setattr(
        backup_commands.BackupOrchestrator,
        "create",
        lambda self, tag, stores_filter=None, force=False: create_ok(
            tag, stores_filter, force=force
        ),
    )
    monkeypatch.setattr(
        backup_commands.BackupOrchestrator,
        "restore",
        lambda self, backup_id, stores_filter=None, verify_only=False: restore_ok(
            backup_id, stores_filter, verify_only=verify_only
        ),
    )

    create_result = runner.invoke(
        app,
        ["backup", "create", "--tag", "nightly", "--stores", "redis", "--force"],
    )
    restore_result = runner.invoke(
        app,
        ["backup", "restore", "bkp-1", "--stores", "redis,kafka"],
    )

    async def create_boom(*args: object, **kwargs: object) -> BackupManifest:
        raise RuntimeError("create failed")

    async def restore_boom(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("restore failed")

    monkeypatch.setattr(
        backup_commands.BackupOrchestrator,
        "create",
        lambda self, tag, stores_filter=None, force=False: create_boom(),
    )
    monkeypatch.setattr(
        backup_commands.BackupOrchestrator,
        "restore",
        lambda self, backup_id, stores_filter=None, verify_only=False: restore_boom(),
    )

    create_error = runner.invoke(app, ["backup", "create"])
    restore_error = runner.invoke(app, ["backup", "restore", "bkp-1"])

    assert create_result.exit_code == 0
    assert restore_result.exit_code == 0
    assert "Restore completed" in restore_result.output
    assert restore_calls == [("bkp-1", {"redis", "kafka"}, False)]
    assert create_error.exit_code == int(ExitCode.GENERAL_ERROR.value)
    assert restore_error.exit_code == int(ExitCode.GENERAL_ERROR.value)


def test_diagnose_command_fix_and_nonhealthy_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    config = _config(tmp_path)
    monkeypatch.setattr(
        diagnose_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )

    captured_selected: list[set[str] | None] = []

    class FixRunner:
        def __init__(
            self,
            config: InstallerConfig,
            *,
            deployment_mode: DeploymentMode | None = None,
            selected_checks: set[str] | None = None,
        ) -> None:
            captured_selected.append(selected_checks)

        @classmethod
        def auto_detect_mode(cls, config: InstallerConfig) -> DeploymentMode:
            return DeploymentMode.LOCAL

        async def run(self, timeout_per_check: int = 5) -> DiagnosticReport:
            return _report(
                checks=[_check("redis", CheckStatus.HEALTHY, latency_ms=12.5)],
            )

        async def auto_fix(self, report: DiagnosticReport) -> list[AutoFixResult]:
            return [
                AutoFixResult(
                    component="redis",
                    action="restart",
                    success=True,
                    message="done",
                )
            ]

    monkeypatch.setattr(diagnose_commands, "DiagnosticRunner", FixRunner)
    stream = io.StringIO()
    set_output_stream(stream)
    json_result = runner.invoke(app, ["--json", "diagnose", "--fix", "--checks", "redis, kafka"])
    payload = json.loads(stream.getvalue().strip())

    class UnhealthyRunner:
        def __init__(
            self,
            config: InstallerConfig,
            *,
            deployment_mode: DeploymentMode | None = None,
            selected_checks: set[str] | None = None,
        ) -> None:
            return None

        @classmethod
        def auto_detect_mode(cls, config: InstallerConfig) -> DeploymentMode:
            return DeploymentMode.LOCAL

        async def run(self, timeout_per_check: int = 5) -> DiagnosticReport:
            return _report(
                overall_status=CheckStatus.UNHEALTHY,
                checks=[_check("postgresql", CheckStatus.UNHEALTHY)],
            )

        async def auto_fix(self, report: DiagnosticReport) -> list[AutoFixResult]:
            return []

    monkeypatch.setattr(diagnose_commands, "DiagnosticRunner", UnhealthyRunner)
    unhealthy_result = runner.invoke(app, ["diagnose"])

    assert json_result.exit_code == 0
    assert captured_selected == [{"redis", "kafka"}]
    assert payload["details"]["auto_fix_results"][0]["action"] == "restart"
    assert unhealthy_result.exit_code == int(ExitCode.PARTIAL_FAILURE.value)
    assert "Overall: unhealthy" in unhealthy_result.output


@pytest.mark.asyncio
async def test_install_run_installer_branch_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    console_messages: list[str] = []
    credentials: list[tuple[str, str, str]] = []
    config = _config(
        tmp_path,
        deployment_mode=DeploymentMode.KUBERNETES,
        ingress=IngressConfig(hostname="cluster.example", tls_enabled=False),
    )

    class FakeInstaller:
        def __init__(self) -> None:
            self.config = config

        async def run(self) -> InstallerResult:
            return InstallerResult(
                deployment_mode=DeploymentMode.KUBERNETES,
                duration_seconds=1.2,
                admin_email="admin@example.com",
                admin_password="Secret123!",
                verification_status=CheckStatus.HEALTHY,
                checkpoint_path=str(tmp_path / "checkpoint.json"),
            )

    monkeypatch.setattr(
        install_commands,
        "get_console",
        lambda: SimpleNamespace(print=lambda message: console_messages.append(message)),
    )
    monkeypatch.setattr(
        install_commands,
        "print_credentials_panel",
        lambda email, password, url: credentials.append((email, password, url)),
    )

    await install_commands._run_installer(_context(), FakeInstaller(), "install-kubernetes")

    class BrokenInstaller(FakeInstaller):
        async def run(self) -> InstallerResult:
            raise RuntimeError("boom")

    with pytest.raises(typer.Exit) as exc_info:
        await install_commands._run_installer(_context(), BrokenInstaller(), "install-kubernetes")

    assert console_messages[0].startswith("Install-Kubernetes completed")
    assert credentials == [("admin@example.com", "Secret123!", "http://cluster.example")]
    assert exc_info.value.exit_code == int(ExitCode.GENERAL_ERROR.value)


def test_install_uninstall_mode_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    config = _config(tmp_path / "data")
    monkeypatch.setattr(
        install_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )

    local_data_dir = config.data_dir
    local_data_dir.mkdir(parents=True, exist_ok=True)
    (local_data_dir / "marker.txt").write_text("cleanup", encoding="utf-8")

    subprocess_calls: list[list[str]] = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda command, **kwargs: (
            subprocess_calls.append(command) or SimpleNamespace(returncode=0, stdout="", stderr="")
        ),
    )
    monkeypatch.setattr(install_commands.LocalInstaller, "stop", lambda data_dir: True)

    local_result = runner.invoke(
        app, ["install", "uninstall", "--deployment-mode", "local", "--force"]
    )
    docker_result = runner.invoke(app, ["install", "uninstall", "--deployment-mode", "docker"])
    swarm_result = runner.invoke(app, ["install", "uninstall", "--deployment-mode", "swarm"])
    incus_result = runner.invoke(app, ["install", "uninstall", "--deployment-mode", "incus"])

    monkeypatch.setattr(
        install_commands.HelmRunner,
        "uninstall",
        lambda self, release, namespace: (_ for _ in ()).throw(RuntimeError("helm failed")),
    )
    kubernetes_error = runner.invoke(
        app, ["install", "uninstall", "--deployment-mode", "kubernetes"]
    )

    assert local_result.exit_code == 0
    assert docker_result.exit_code == 0
    assert swarm_result.exit_code == 0
    assert incus_result.exit_code == 0
    assert not local_data_dir.exists()
    assert [
        "docker",
        "compose",
        "-f",
        str(tmp_path / "docker-compose.yml"),
        "down",
    ] in subprocess_calls
    assert ["docker", "stack", "rm", "platform"] in subprocess_calls
    assert ["incus", "delete", "--force", "platform-control-plane"] in subprocess_calls
    assert kubernetes_error.exit_code == int(ExitCode.GENERAL_ERROR.value)


def test_upgrade_release_versions_and_nonhealthy_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeHelmRunner:
        def list_releases(self, namespace: str) -> list[dict[str, str]]:
            if namespace == "ok":
                return [{"name": "platform-alpha", "app_version": "1.0.0"}]
            raise RuntimeError("ignored")

    monkeypatch.setattr(upgrade_commands, "HelmRunner", FakeHelmRunner)
    monkeypatch.setattr(
        upgrade_commands,
        "PLATFORM_COMPONENTS",
        [
            SimpleNamespace(namespace="ok"),
            SimpleNamespace(namespace="missing"),
        ],
    )
    releases = upgrade_commands._release_versions()
    assert releases == {"platform-alpha": {"name": "platform-alpha", "app_version": "1.0.0"}}

    class RuntimeHelmRunner:
        def install(
            self,
            chart_path: Path,
            release_name: str,
            namespace: str,
            values_file: Path,
        ) -> None:
            return None

        def wait_for_ready(self, component_name: str, namespace: str) -> None:
            return None

        def list_releases(self, namespace: str) -> list[dict[str, str]]:
            return []

    monkeypatch.setattr(upgrade_commands, "HelmRunner", RuntimeHelmRunner)

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
    config = _config(tmp_path)
    monkeypatch.setattr(
        upgrade_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )
    monkeypatch.setattr(
        upgrade_commands,
        "PLATFORM_COMPONENTS",
        [
            SimpleNamespace(
                name="alpha",
                namespace="alpha-ns",
                helm_chart="alpha-chart",
                has_migration=False,
            ),
            SimpleNamespace(
                name="skip-me",
                namespace="skip-ns",
                helm_chart=None,
                has_migration=False,
            ),
        ],
    )
    monkeypatch.setattr(
        upgrade_commands,
        "_release_versions",
        lambda: {"platform-alpha": {"app_version": "0.9.0"}},
    )

    backup_calls: list[str] = []
    monkeypatch.setattr(
        upgrade_commands.BackupOrchestrator,
        "create",
        lambda self, tag, force=False: backup_calls.append(tag) or asyncio.sleep(0),
    )
    install_calls: list[tuple[Path, str, str, Path]] = []
    wait_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        upgrade_commands.HelmRunner,
        "install",
        lambda self, chart_path, release_name, namespace, values_file: install_calls.append(
            (chart_path, release_name, namespace, values_file)
        ),
    )
    monkeypatch.setattr(
        upgrade_commands.HelmRunner,
        "wait_for_ready",
        lambda self, component_name, namespace: wait_calls.append((component_name, namespace)),
    )
    monkeypatch.setattr(
        upgrade_commands.DiagnosticRunner,
        "run",
        lambda self: asyncio.sleep(
            0,
            result=_report(overall_status=CheckStatus.UNHEALTHY),
        ),
    )

    result = runner.invoke(app, ["upgrade", "--target-version", "2.0.0", "--skip-backup"])

    assert result.exit_code == int(ExitCode.PARTIAL_FAILURE.value)
    assert backup_calls == []
    assert len(install_calls) == 1
    assert wait_calls == [("alpha", "alpha-ns")]


def test_diagnostic_runner_mode_detection_and_build_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(
        tmp_path,
        deployment_mode=DeploymentMode.DOCKER,
        model_provider_urls=["https://m1", "https://m2"],
    )

    (tmp_path / "platform.pid").write_text("123", encoding="utf-8")
    assert DiagnosticRunner.auto_detect_mode(config) == DeploymentMode.LOCAL
    (tmp_path / "platform.pid").unlink()

    monkeypatch.setattr(diagnostic_checker, "helm_chart_path", lambda name: tmp_path / name)
    (tmp_path / "control-plane").mkdir()
    assert DiagnosticRunner.auto_detect_mode(config) == DeploymentMode.KUBERNETES
    (tmp_path / "control-plane").rmdir()
    assert DiagnosticRunner.auto_detect_mode(config) == DeploymentMode.DOCKER

    (tmp_path / "sandbox-manager").mkdir()
    (tmp_path / "simulation-controller").mkdir()
    secrets = generate_secrets(config.secrets)
    k8s_config = config.model_copy(update={"deployment_mode": DeploymentMode.KUBERNETES})
    runner = DiagnosticRunner(k8s_config, secrets=secrets)
    checks = runner.build_checks()
    names = {check.name for check in checks}

    filtered = DiagnosticRunner(
        k8s_config,
        selected_checks={"redis", "https://m2", "simulation-controller"},
        secrets=secrets,
    ).build_checks()

    assert diagnostic_checker._service_host(k8s_config, "redis", "platform-data", 6379) == (
        "redis.platform-data.svc.cluster.local:6379"
    )
    assert "sandbox-manager" in names
    assert "simulation-controller" in names
    assert "https://m1" in names
    assert "https://m2" in names
    assert {check.name for check in filtered} == {"redis", "https://m2", "simulation-controller"}


@pytest.mark.asyncio
async def test_diagnostic_runner_empty_and_autofix_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_runner = DiagnosticRunner(_config(tmp_path, deployment_mode=DeploymentMode.LOCAL))
    monkeypatch.setattr(local_runner, "build_checks", list)
    empty_report = await local_runner.run()
    assert empty_report.overall_status == CheckStatus.UNKNOWN

    k8s_runner = DiagnosticRunner(_config(tmp_path, deployment_mode=DeploymentMode.KUBERNETES))
    monkeypatch.setattr(
        diagnostic_checker.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(returncode=1, stderr="restart failed", stdout=""),
    )
    report = _report(
        deployment_mode=DeploymentMode.KUBERNETES,
        overall_status=CheckStatus.UNHEALTHY,
        checks=[
            _check("postgresql", CheckStatus.UNHEALTHY),
            _check("unknown-component", CheckStatus.UNHEALTHY),
            _check("redis", CheckStatus.HEALTHY),
        ],
    )
    results = await k8s_runner.auto_fix(report)
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].message == "restart failed"

    non_k8s_results = await local_runner.auto_fix(report)
    assert non_k8s_results == []


@pytest.mark.asyncio
async def test_abstract_installer_resume_skip_and_failure(tmp_path: Path) -> None:
    config = _config(tmp_path)

    skip_manager = CheckpointManager(tmp_path / "skip")
    skip_installer = BranchInstaller(
        config,
        checkpoint_manager=skip_manager,
        skip_preflight=True,
        skip_migrations=True,
    )
    skip_installer._load_or_create_checkpoint(skip_installer.build_steps())
    result = await skip_installer.run()
    statuses = {step.name: step.status for step in skip_manager.checkpoint.steps}

    resume_dir = tmp_path / "resume"
    seed_manager = CheckpointManager(resume_dir)
    seed_installer = BranchInstaller(config, checkpoint_manager=seed_manager)
    seed_installer._load_or_create_checkpoint(seed_installer.build_steps())
    seed_manager.update_step("preflight", InstallStepStatus.COMPLETED)
    resumed = BranchInstaller(
        config,
        checkpoint_manager=CheckpointManager(resume_dir),
        resume=True,
    )
    await resumed.run()

    failing_dir = tmp_path / "failing"
    failing = BranchInstaller(
        config,
        checkpoint_manager=CheckpointManager(failing_dir),
        fail_step="migrate",
    )
    with pytest.raises(RuntimeError, match="migrate failed"):
        await failing.run()
    loaded = CheckpointManager(failing_dir).load_latest(
        CheckpointManager.compute_config_hash(config)
    )

    assert skip_installer.calls == ["verify"]
    assert statuses == {
        "preflight": InstallStepStatus.SKIPPED,
        "migrate": InstallStepStatus.SKIPPED,
        "verify": InstallStepStatus.COMPLETED,
    }
    assert result.verification_status == CheckStatus.HEALTHY
    assert resumed.calls == ["migrate", "verify"]
    assert loaded is not None
    assert (
        next(step for step in loaded.steps if step.name == "migrate").status
        == InstallStepStatus.FAILED
    )


@pytest.mark.asyncio
async def test_kubernetes_installer_method_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(
        tmp_path,
        ingress=IngressConfig(hostname="cluster.example", tls_enabled=True),
    )
    installer = KubernetesInstaller(config)

    monkeypatch.setattr(installer.lock, "acquire", lambda namespace, holder_id: False)
    with pytest.raises(RuntimeError, match="already running"):
        await installer.before_run()

    failed_summary = SimpleNamespace(
        passed=False,
        results=[("preflight", SimpleNamespace(passed=False, message="bad", remediation="fix me"))],
    )
    monkeypatch.setattr(
        "platform_cli.installers.kubernetes.PreflightRunner.run",
        lambda self: asyncio.sleep(0, result=failed_summary),
    )
    with pytest.raises(RuntimeError, match="fix me"):
        await installer.preflight()

    with pytest.raises(RuntimeError, match="secrets must be generated"):
        installer.deploy_component(PLATFORM_COMPONENTS[0])

    secrets = generate_secrets(config.secrets)
    installer.generated_secrets = secrets
    namespace_commands: list[list[str]] = []
    monkeypatch.setattr(
        "platform_cli.installers.kubernetes._run",
        lambda command: namespace_commands.append(command),
    )
    installer.prepare_namespaces()

    install_calls: list[tuple[str, bool]] = []
    wait_calls: list[str] = []
    monkeypatch.setattr(
        "platform_cli.installers.kubernetes.render_values", lambda *args: {"ok": True}
    )
    monkeypatch.setattr(
        "platform_cli.installers.kubernetes.write_values_file",
        lambda values, path: path,
    )
    monkeypatch.setattr(
        installer.helm_runner,
        "install",
        lambda chart_path, release_name, namespace, values_file, dry_run=False: (
            install_calls.append((release_name, dry_run))
        ),
    )
    monkeypatch.setattr(
        installer.helm_runner,
        "wait_for_ready",
        lambda component_name, namespace: wait_calls.append(component_name),
    )
    installer.deploy_component(PLATFORM_COMPONENTS[0])

    installer.dry_run = True
    await installer.migrate()
    await installer.create_admin()

    installer.dry_run = False
    admin_calls: list[str] = []
    monkeypatch.setattr(
        installer.migration_runner,
        "create_admin_user",
        lambda url, email, password: asyncio.sleep(0, result=admin_calls.append(url)),
    )
    await installer.create_admin()

    monkeypatch.setattr(
        "platform_cli.installers.kubernetes.DiagnosticRunner.run",
        lambda self: asyncio.sleep(0, result=_report(DeploymentMode.KUBERNETES)),
    )
    await installer.verify()

    assert len(namespace_commands) == 12
    assert install_calls[0][1] is False
    assert wait_calls == [PLATFORM_COMPONENTS[0].name]
    assert admin_calls == ["https://cluster.example"]
    assert installer.diagnostic_report is not None


@pytest.mark.asyncio
async def test_local_installer_method_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installer = LocalInstaller(_config(tmp_path), port=8123)

    monkeypatch.setattr(installer.lock, "acquire", lambda: False)
    with pytest.raises(RuntimeError, match="already running"):
        await installer.before_run()

    failed_summary = SimpleNamespace(
        passed=False,
        results=[
            ("preflight", SimpleNamespace(passed=False, message="bad", remediation="free disk"))
        ],
    )
    monkeypatch.setattr(
        "platform_cli.installers.local.PreflightRunner.run",
        lambda self: asyncio.sleep(0, result=failed_summary),
    )
    with pytest.raises(RuntimeError, match="free disk"):
        await installer.preflight()

    monkeypatch.setenv("PYTHONPATH", "existing")
    env = installer.build_local_env()
    assert env["PYTHONPATH"].endswith("existing")

    class FakeProcess:
        pid = 321

    monkeypatch.setattr(local_module.shutil, "which", lambda name: "/usr/bin/qdrant")
    monkeypatch.setattr(local_module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    installer.start_qdrant()

    class FailingClient:
        async def __aenter__(self) -> FailingClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> object:
            raise httpx.ReadTimeout("timeout")

    times = iter([0.0, 0.05, 0.1, 0.2])
    monkeypatch.setattr(local_module.httpx, "AsyncClient", lambda timeout=2.0: FailingClient())
    monkeypatch.setattr(local_module, "monotonic", lambda: next(times))

    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(local_module.asyncio, "sleep", no_sleep)
    with pytest.raises(RuntimeError, match="did not become healthy"):
        await installer.wait_for_health(timeout_seconds=0.15)

    with pytest.raises(RuntimeError, match="secrets must be generated"):
        await installer.create_admin()

    async def verify_report() -> DiagnosticReport:
        return _report()

    monkeypatch.setattr(
        "platform_cli.installers.local.DiagnosticRunner.run",
        lambda self: verify_report(),
    )
    await installer.verify()

    assert installer.qdrant_process is not None
    assert installer.diagnostic_report is not None
    assert LocalInstaller.stop(tmp_path) is False


@pytest.mark.asyncio
async def test_container_installers_and_incus_access_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def failing_process(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stderr="bad", stdout="")

    monkeypatch.setattr(docker_module.subprocess, "run", failing_process)
    with pytest.raises(RuntimeError, match="bad"):
        docker_module._run(["docker"])
    monkeypatch.setattr(swarm_module.subprocess, "run", failing_process)
    with pytest.raises(RuntimeError, match="bad"):
        swarm_module._run(["docker"])
    monkeypatch.setattr(incus_module.subprocess, "run", failing_process)
    with pytest.raises(RuntimeError, match="bad"):
        incus_module._run(["incus"])

    access_results = [
        SimpleNamespace(returncode=0, stdout="6.0", stderr=""),
        SimpleNamespace(returncode=1, stdout="", stderr="missing"),
    ]
    monkeypatch.setattr(
        incus_module.subprocess,
        "run",
        lambda *args, **kwargs: access_results.pop(0),
    )
    assert (await IncusAccessCheck().check()).passed is True
    assert (await IncusAccessCheck().check()).passed is False

    config = _config(tmp_path)
    secrets = generate_secrets(config.secrets)
    failed_summary = SimpleNamespace(
        passed=False,
        results=[
            ("check", SimpleNamespace(passed=False, message="bad", remediation="fix container"))
        ],
    )
    passed_summary = SimpleNamespace(passed=True, results=[])

    docker = DockerComposeInstaller(config, compose_file=tmp_path / "docker-compose.yml")
    monkeypatch.setattr(
        "platform_cli.installers.docker.PreflightRunner.run",
        lambda self: asyncio.sleep(0, result=failed_summary),
    )
    with pytest.raises(RuntimeError, match="fix container"):
        await docker.preflight()
    with pytest.raises(RuntimeError):
        await docker.migrate()
    with pytest.raises(RuntimeError):
        await docker.create_admin()
    stored_paths: list[Path] = []
    monkeypatch.setattr(docker_module, "generate_secrets", lambda cfg: secrets)
    monkeypatch.setattr(
        docker_module, "store_secrets_env_file", lambda bundle, path: stored_paths.append(path)
    )
    docker.generate_and_store_secrets()
    docker_calls: list[list[str]] = []
    monkeypatch.setattr(docker_module, "_run", lambda command: docker_calls.append(command))
    docker.deploy()
    monkeypatch.setattr(
        docker.migration_runner,
        "run_all",
        lambda cfg, generated: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        docker.migration_runner,
        "create_admin_user",
        lambda url, email, password: asyncio.sleep(0),
    )
    await docker.migrate()
    await docker.create_admin()
    monkeypatch.setattr(
        "platform_cli.installers.docker.DiagnosticRunner.run",
        lambda self: asyncio.sleep(0, result=_report(DeploymentMode.DOCKER)),
    )
    await docker.verify()

    swarm = SwarmInstaller(config, stack_name="demo")
    monkeypatch.setattr(
        "platform_cli.installers.swarm.PreflightRunner.run",
        lambda self: asyncio.sleep(0, result=passed_summary),
    )
    swarm_calls: list[list[str]] = []
    monkeypatch.setattr(swarm_module, "_run", lambda command: swarm_calls.append(command))
    await swarm.preflight()
    with pytest.raises(RuntimeError):
        await SwarmInstaller(config).migrate()
    with pytest.raises(RuntimeError):
        await SwarmInstaller(config).create_admin()
    monkeypatch.setattr(swarm_module, "generate_secrets", lambda cfg: secrets)
    monkeypatch.setattr(
        swarm_module, "store_secrets_env_file", lambda bundle, path: stored_paths.append(path)
    )
    swarm.generate_and_store_secrets()
    swarm.render_stack()
    swarm.deploy()
    monkeypatch.setattr(
        swarm.migration_runner,
        "run_all",
        lambda cfg, generated: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        swarm.migration_runner,
        "create_admin_user",
        lambda url, email, password: asyncio.sleep(0),
    )
    await swarm.migrate()
    await swarm.create_admin()
    monkeypatch.setattr(
        "platform_cli.installers.swarm.DiagnosticRunner.run",
        lambda self: asyncio.sleep(0, result=_report(DeploymentMode.SWARM)),
    )
    await swarm.verify()

    incus = IncusInstaller(config, profile="demo")
    monkeypatch.setattr(
        "platform_cli.installers.incus.PreflightRunner.run",
        lambda self: asyncio.sleep(0, result=failed_summary),
    )
    with pytest.raises(RuntimeError, match="fix container"):
        await incus.preflight()
    with pytest.raises(RuntimeError):
        await incus.migrate()
    with pytest.raises(RuntimeError):
        await incus.create_admin()
    monkeypatch.setattr(incus_module, "generate_secrets", lambda cfg: secrets)
    monkeypatch.setattr(
        incus_module, "store_secrets_local", lambda bundle, path: stored_paths.append(path)
    )
    incus.generate_and_store_secrets()
    incus.render_profile()
    incus_calls: list[list[str]] = []
    monkeypatch.setattr(incus_module, "_run", lambda command: incus_calls.append(command))
    incus.deploy()
    monkeypatch.setattr(
        incus.migration_runner,
        "run_all",
        lambda cfg, generated: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        incus.migration_runner,
        "create_admin_user",
        lambda url, email, password: asyncio.sleep(0),
    )
    await incus.migrate()
    await incus.create_admin()
    monkeypatch.setattr(
        "platform_cli.installers.incus.DiagnosticRunner.run",
        lambda self: asyncio.sleep(0, result=_report(DeploymentMode.INCUS)),
    )
    await incus.verify()

    assert stored_paths[0].name == ".env"
    assert any(command[:3] == ["docker", "compose", "-p"] for command in docker_calls)
    assert swarm_calls[0][:2] == ["docker", "info"]
    assert any(command[:3] == ["docker", "stack", "deploy"] for command in swarm_calls)
    assert incus_calls[0][:3] == ["incus", "profile", "create"]
    assert incus.profile_file.exists()


@pytest.mark.asyncio
async def test_backup_orchestrator_store_mapping_and_activity_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = BackupOrchestrator(
        _config(tmp_path, deployment_mode=DeploymentMode.LOCAL), storage_root=tmp_path / "local"
    )
    cluster = BackupOrchestrator(
        _config(tmp_path, deployment_mode=DeploymentMode.KUBERNETES, namespace="demo"),
        storage_root=tmp_path / "cluster",
    )
    local_stores = local._stores()
    cluster_stores = cluster._stores()

    assert local_stores["redis"].url == "redis://127.0.0.1:6379/0"
    assert "demo-data" in cluster_stores["postgresql"].database_url

    responses: list[object] = [
        httpx.ReadTimeout("boom"),
        _JsonResponse({}, status_code=503),
        _JsonResponse(["not-a-dict"]),
        _JsonResponse({"items": [1]}),
    ]

    class ExecutionClient:
        async def __aenter__(self) -> ExecutionClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> _JsonResponse:
            current = responses.pop(0)
            if isinstance(current, Exception):
                raise current
            return current

    monkeypatch.setattr(
        orchestrator_module.httpx, "AsyncClient", lambda timeout=5.0: ExecutionClient()
    )

    assert await local._has_active_executions() is False
    assert await local._has_active_executions() is False
    assert await local._has_active_executions() is False
    assert await local._has_active_executions() is True

    async def busy() -> bool:
        return True

    monkeypatch.setattr(local, "_has_active_executions", busy)
    with pytest.raises(RuntimeError, match="active executions"):
        await local.create("nightly")


@pytest.mark.asyncio
async def test_backup_orchestrator_partial_failed_and_restore_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    orchestrator = BackupOrchestrator(
        _config(tmp_path, deployment_mode=DeploymentMode.LOCAL),
        storage_root=tmp_path / "backups",
    )

    class GoodStore:
        def __init__(self, name: str, restored: list[Path]) -> None:
            self.name = name
            self.restored = restored

        async def backup(self, output_dir: Path) -> BackupArtifact:
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{self.name}.bin"
            path.write_text(self.name, encoding="utf-8")
            return build_artifact(
                store=self.name,
                display_name=self.name.title(),
                path=path,
                format_name="raw",
            )

        async def restore(self, artifact_path: Path) -> bool:
            self.restored.append(artifact_path)
            return True

    class BadStore:
        async def backup(self, output_dir: Path) -> BackupArtifact:
            raise RuntimeError("backup failed")

        async def restore(self, artifact_path: Path) -> bool:
            raise RuntimeError("restore failed")

    async def idle() -> bool:
        return False

    monkeypatch.setattr(orchestrator, "_has_active_executions", idle)
    restored: list[Path] = []
    monkeypatch.setattr(
        orchestrator,
        "_stores",
        lambda: {"good": GoodStore("good", restored), "bad": BadStore()},
    )
    partial_manifest = await orchestrator.create("partial", force=True)
    assert partial_manifest.status == BackupStatus.PARTIAL

    failed_orchestrator = BackupOrchestrator(
        _config(tmp_path, deployment_mode=DeploymentMode.LOCAL),
        storage_root=tmp_path / "failed",
    )
    monkeypatch.setattr(failed_orchestrator, "_has_active_executions", idle)
    monkeypatch.setattr(failed_orchestrator, "_stores", lambda: {"bad": BadStore()})
    failed_manifest = await failed_orchestrator.create("failed", force=True)
    assert failed_manifest.status == BackupStatus.FAILED

    corrupted_path = Path(partial_manifest.artifacts[0].path)
    corrupted_path.write_text("corrupted", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        await orchestrator.restore(partial_manifest.backup_id, stores_filter={"good"})

    restored.clear()
    success_orchestrator = BackupOrchestrator(
        _config(tmp_path, deployment_mode=DeploymentMode.LOCAL),
        storage_root=tmp_path / "success",
    )
    monkeypatch.setattr(success_orchestrator, "_has_active_executions", idle)
    monkeypatch.setattr(
        success_orchestrator,
        "_stores",
        lambda: {
            "good": GoodStore("good", restored),
            "ignored": GoodStore("ignored", restored),
        },
    )
    success_manifest = await success_orchestrator.create(
        "success", stores_filter={"good"}, force=True
    )
    assert [artifact.store for artifact in success_manifest.artifacts] == ["good"]
    assert (
        await success_orchestrator.restore(success_manifest.backup_id, stores_filter={"good"})
        is True
    )
    assert restored == [Path(success_manifest.artifacts[0].path)]


def test_file_lock_blocking_and_stale_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lock = file_lock_module.FileLock(tmp_path / "install.lock")
    lock.release()

    monkeypatch.setattr(
        file_lock_module.fcntl,
        "flock",
        lambda fd, flags: (_ for _ in ()).throw(BlockingIOError()),
    )
    assert lock.acquire() is False
    assert lock.is_locked() is True

    stale_lock = file_lock_module.FileLock(tmp_path / "stale.lock")
    stale_lock.path.write_text(json.dumps({"pid": 1}), encoding="utf-8")
    assert stale_lock._is_stale(timeout_minutes=30) is True


@pytest.mark.asyncio
async def test_migration_runner_error_paths_and_cluster_run_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from platform_cli.migrations import runner as migration_module
    from platform_cli.migrations.runner import MigrationRunner

    monkeypatch.setattr(
        migration_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(RuntimeError, match="bad"):
        migration_module._run(["alembic"])

    runner = MigrationRunner()

    class ErrorClient:
        async def __aenter__(self) -> ErrorClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def put(self, url: str, **kwargs: object) -> _JsonResponse:
            return _JsonResponse({}, status_code=500, text="broken")

        async def post(self, url: str, **kwargs: object) -> _JsonResponse:
            return _JsonResponse({}, status_code=500, text="broken")

    monkeypatch.setattr(migration_module.httpx, "AsyncClient", lambda timeout=10.0: ErrorClient())
    with pytest.raises(RuntimeError, match="qdrant init failed"):
        await runner.init_qdrant("http://qdrant")
    with pytest.raises(RuntimeError, match="opensearch init failed"):
        await runner.init_opensearch("http://opensearch")
    with pytest.raises(RuntimeError, match="admin creation failed"):
        await runner.create_admin_user("http://api", "admin@example.com", "Secret123!")

    class TopicExistsAdmin:
        async def start(self) -> None:
            return None

        async def create_topics(self, topics: list[object], validate_only: bool = False) -> None:
            raise RuntimeError("TopicAlreadyExistsError")

        async def close(self) -> None:
            return None

    class BrokenAdmin:
        async def start(self) -> None:
            return None

        async def create_topics(self, topics: list[object], validate_only: bool = False) -> None:
            raise RuntimeError("boom")

        async def close(self) -> None:
            return None

    monkeypatch.setitem(
        sys.modules,
        "aiokafka.admin",
        SimpleNamespace(
            AIOKafkaAdminClient=lambda **kwargs: TopicExistsAdmin(),
            NewTopic=lambda name, num_partitions, replication_factor: SimpleNamespace(name=name),
        ),
    )
    await runner.init_kafka("kafka:9092")
    monkeypatch.setitem(
        sys.modules,
        "aiokafka.admin",
        SimpleNamespace(
            AIOKafkaAdminClient=lambda **kwargs: BrokenAdmin(),
            NewTopic=lambda name, num_partitions, replication_factor: SimpleNamespace(name=name),
        ),
    )
    with pytest.raises(RuntimeError, match="boom"):
        await runner.init_kafka("kafka:9092")

    class OwnedBucketClient:
        async def __aenter__(self) -> OwnedBucketClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def create_bucket(self, **kwargs: object) -> None:
            raise RuntimeError("BucketAlreadyOwnedByYou")

    class BrokenBucketClient(OwnedBucketClient):
        async def create_bucket(self, **kwargs: object) -> None:
            raise RuntimeError("no bucket")

    monkeypatch.setitem(
        sys.modules,
        "aioboto3",
        SimpleNamespace(
            Session=lambda: SimpleNamespace(client=lambda *args, **kwargs: OwnedBucketClient())
        ),
    )
    await runner.init_minio("http://minio", "key", "secret")
    monkeypatch.setitem(
        sys.modules,
        "aioboto3",
        SimpleNamespace(
            Session=lambda: SimpleNamespace(client=lambda *args, **kwargs: BrokenBucketClient())
        ),
    )
    with pytest.raises(RuntimeError, match="no bucket"):
        await runner.init_minio("http://minio", "key", "secret")

    cluster_runner = MigrationRunner()
    calls: dict[str, str] = {}
    monkeypatch.setattr(
        cluster_runner, "run_alembic", lambda url: calls.__setitem__("alembic", url)
    )
    monkeypatch.setattr(
        cluster_runner,
        "init_qdrant",
        lambda url: asyncio.sleep(0, result=calls.__setitem__("qdrant", url)),
    )
    monkeypatch.setattr(
        cluster_runner,
        "init_neo4j",
        lambda uri, password: asyncio.sleep(0, result=calls.__setitem__("neo4j", uri)),
    )
    monkeypatch.setattr(
        cluster_runner,
        "init_clickhouse",
        lambda host: asyncio.sleep(0, result=calls.__setitem__("clickhouse", host)),
    )
    monkeypatch.setattr(
        cluster_runner,
        "init_opensearch",
        lambda url: asyncio.sleep(0, result=calls.__setitem__("opensearch", url)),
    )
    monkeypatch.setattr(
        cluster_runner,
        "init_kafka",
        lambda bootstrap: asyncio.sleep(0, result=calls.__setitem__("kafka", bootstrap)),
    )
    monkeypatch.setattr(
        cluster_runner,
        "init_minio",
        lambda endpoint, access_key, secret_key: asyncio.sleep(
            0, result=calls.__setitem__("minio", endpoint)
        ),
    )
    monkeypatch.setattr(
        cluster_runner,
        "create_admin_user",
        lambda api_url, email, password: asyncio.sleep(
            0, result=calls.__setitem__("admin", api_url)
        ),
    )

    config = _config(tmp_path, deployment_mode=DeploymentMode.KUBERNETES, namespace="demo")
    secrets = generate_secrets(config.secrets)
    await cluster_runner.run_all(config, secrets)

    assert "demo-data" in calls["alembic"]
    assert calls["qdrant"] == "http://qdrant.demo-data.svc.cluster.local:6333"
    assert calls["neo4j"] == "bolt://neo4j.demo-data.svc.cluster.local:7687"
    assert calls["clickhouse"] == "clickhouse.demo-data.svc.cluster.local"
    assert calls["opensearch"] == "http://opensearch.demo-data.svc.cluster.local:9200"
    assert calls["kafka"] == "kafka.demo-data.svc.cluster.local:9092"
    assert calls["minio"] == "http://minio.demo-data.svc.cluster.local:9000"
    assert calls["admin"] == "http://platform.local"


@pytest.mark.asyncio
async def test_backup_store_restore_helpers_and_redis_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for module in (clickhouse_module, minio_module, neo4j_module, postgresql_module):
        monkeypatch.setattr(
            module.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
        )
        with pytest.raises(RuntimeError, match="bad"):
            module._run(["bad"])  # type: ignore[attr-defined]

    click_commands: list[list[str]] = []
    monkeypatch.setattr(clickhouse_module, "_run", lambda command: click_commands.append(command))
    clickhouse_backup = ClickHouseBackup()
    clickhouse_source = tmp_path / "platform.clickhouse"
    clickhouse_source.write_text("platform", encoding="utf-8")
    assert await clickhouse_backup.restore(clickhouse_source) is True

    neo_commands: list[list[str]] = []
    monkeypatch.setattr(neo4j_module, "_run", lambda command: neo_commands.append(command))
    neo_path = tmp_path / "neo4j.dump"
    neo_path.write_text("neo4j", encoding="utf-8")
    assert await Neo4jBackup().restore(neo_path) is True

    minio_commands: list[list[str]] = []
    monkeypatch.setattr(minio_module, "_run", lambda command: minio_commands.append(command))
    minio_manifest = tmp_path / "minio.mirror"
    minio_manifest.write_text("/tmp/source", encoding="utf-8")
    assert await MinIOBackup().restore(minio_manifest) is True

    pg_commands: list[list[str]] = []
    monkeypatch.setattr(postgresql_module, "_run", lambda command: pg_commands.append(command))
    pg_artifact = tmp_path / "postgresql.dump"
    pg_artifact.write_text("pg", encoding="utf-8")
    assert await PostgreSQLBackup("postgresql://db").restore(pg_artifact) is True

    rdb_path = tmp_path / "redis.rdb"
    rdb_path.write_text("redis", encoding="utf-8")
    closed: list[bool] = []

    class FakeRedisClient:
        def __init__(self) -> None:
            self._calls = 0

        async def lastsave(self) -> int:
            self._calls += 1
            return 100 if self._calls < 3 else 101

        async def bgsave(self) -> None:
            return None

        async def aclose(self) -> None:
            closed.append(True)

    fake_client = FakeRedisClient()
    monkeypatch.setitem(
        sys.modules,
        "redis.asyncio",
        SimpleNamespace(
            Redis=SimpleNamespace(from_url=lambda url, decode_responses=True: fake_client)
        ),
    )

    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(redis_store_module.asyncio, "sleep", no_sleep)
    artifact = await RedisBackup("redis://localhost", rdb_path).backup(tmp_path / "redis-backup")

    assert Path(artifact.path).exists()
    assert click_commands[0][0] == "clickhouse-backup"
    assert neo_commands[0][:3] == ["neo4j-admin", "database", "load"]
    assert minio_commands[0][:2] == ["mc", "mirror"]
    assert pg_commands[0][0] == "pg_restore"
    assert closed == [True]
