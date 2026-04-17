from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from platform_cli.config import InstallerConfig, ResourceOverride
from platform_cli.constants import ComponentCategory, PlatformComponent
from platform_cli.helm.renderer import render_values, write_values_file
from platform_cli.helm.runner import HelmRunner
from platform_cli.secrets.generator import generate_secrets


def test_render_values_merges_chart_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chart_dir = tmp_path / "deploy" / "helm" / "redis"
    chart_dir.mkdir(parents=True)
    (chart_dir / "values.yaml").write_text("auth: {}\nresources: {}\n", encoding="utf-8")
    monkeypatch.setattr("platform_cli.helm.renderer.helm_chart_path", lambda name: chart_dir)

    component = PlatformComponent(
        name="redis",
        display_name="Redis",
        category=ComponentCategory.DATA_STORE,
        helm_chart="redis",
        namespace="platform-data",
        depends_on=[],
        health_check_type="tcp",
        health_check_target="PING",
        has_migration=False,
        backup_supported=True,
    )
    config = InstallerConfig(resources={"redis": ResourceOverride(replicas=2)})
    secrets = generate_secrets(config.secrets)

    rendered = render_values(component, config, secrets)

    assert rendered["auth"]["password"] == secrets.redis_password
    assert rendered["resources"]["replicas"] == 2
    assert rendered["global"]["storageClass"] == "standard"


def test_write_values_file_writes_yaml(tmp_path: Path) -> None:
    path = write_values_file({"hello": "world"}, tmp_path / "values.yaml")
    assert path.read_text(encoding="utf-8").strip() == "hello: world"


def _cp(code: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["cmd"], returncode=code, stdout=stdout, stderr=stderr)


def test_helm_runner_install_and_listing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:2] == ["helm", "list"]:
            return _cp(stdout=json.dumps([{"name": "platform-redis"}]))
        return _cp()

    monkeypatch.setattr("subprocess.run", fake_run)
    runner = HelmRunner()
    values_file = tmp_path / "values.yaml"
    values_file.write_text("{}", encoding="utf-8")

    runner.install(tmp_path, "platform-redis", "platform-data", values_file, dry_run=True)
    runner.wait_for_ready("redis", "platform-data")
    assert runner.is_installed("platform-redis", "platform-data") is True
    runner.uninstall("platform-redis", "platform-data")

    assert calls[0][:4] == ["helm", "upgrade", "--install", "platform-redis"]
