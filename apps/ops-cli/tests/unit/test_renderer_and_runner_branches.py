from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from platform_cli.config import InstallerConfig
from platform_cli.constants import ComponentCategory, PlatformComponent
from platform_cli.helm.renderer import render_values
from platform_cli.helm.runner import HelmRunner
from platform_cli.secrets.generator import generate_secrets


def _component(name: str) -> PlatformComponent:
    return PlatformComponent(
        name=name,
        display_name=name.title(),
        category=ComponentCategory.CONTROL_PLANE
        if name == "control-plane"
        else ComponentCategory.DATA_STORE,
        helm_chart=name,
        namespace="platform-control" if name == "control-plane" else "platform-data",
        depends_on=[],
        health_check_type="http",
        health_check_target="/health",
        has_migration=False,
        backup_supported=True,
    )


@pytest.mark.parametrize(
    ("name", "expected_key"),
    [
        ("postgresql", "auth"),
        ("redis", "auth"),
        ("neo4j", "neo4j"),
        ("clickhouse", "auth"),
        ("opensearch", "auth"),
        ("minio", "rootUser"),
        ("control-plane", "auth"),
    ],
)
def test_render_values_secret_branches(
    name: str,
    expected_key: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart_dir = tmp_path / name
    chart_dir.mkdir()
    (chart_dir / "values.yaml").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("platform_cli.helm.renderer.helm_chart_path", lambda chart_name: chart_dir)

    config = InstallerConfig()
    secrets = generate_secrets(config.secrets)
    values = render_values(_component(name), config, secrets)

    assert expected_key in values


def test_render_values_missing_chart_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "platform_cli.helm.renderer.helm_chart_path", lambda chart_name: tmp_path / chart_name
    )
    with pytest.raises(FileNotFoundError):
        render_values(
            _component("redis"), InstallerConfig(), generate_secrets(InstallerConfig().secrets)
        )


def test_helm_runner_error_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    responses = [
        subprocess.CompletedProcess(args=["helm"], returncode=1, stdout="", stderr="boom"),
        subprocess.CompletedProcess(
            args=["kubectl"], returncode=1, stdout="", stderr="rollout boom"
        ),
        subprocess.CompletedProcess(args=["helm"], returncode=1, stdout="", stderr="list boom"),
        subprocess.CompletedProcess(
            args=["helm"], returncode=1, stdout="", stderr="uninstall boom"
        ),
    ]

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return responses.pop(0)

    monkeypatch.setattr("subprocess.run", fake_run)
    runner = HelmRunner()
    values_file = tmp_path / "values.yaml"
    values_file.write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="boom"):
        runner.install(tmp_path, "release", "ns", values_file)
    with pytest.raises(RuntimeError, match="rollout boom"):
        runner.wait_for_ready("release", "ns")
    with pytest.raises(RuntimeError, match="list boom"):
        runner.list_releases("ns")
    with pytest.raises(RuntimeError, match="uninstall boom"):
        runner.uninstall("release", "ns")
