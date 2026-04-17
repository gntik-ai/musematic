from __future__ import annotations

from pathlib import Path

import pytest

from platform_cli.config import DeploymentMode, load_config


def test_load_config_reads_yaml_and_env_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "platform-install.yaml"
    config_path.write_text(
        """
deployment_mode: kubernetes
namespace: demo
storage_class: fast
ingress:
  hostname: platform.example.com
resources:
  redis:
    replicas: 2
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("PLATFORM_CLI_NAMESPACE", "override")
    monkeypatch.setenv("PLATFORM_CLI_INGRESS__TLS_ENABLED", "true")
    monkeypatch.setenv("PLATFORM_CLI_MODEL_PROVIDER_URLS", '["https://models.example.com/health"]')

    config = load_config(config_path)

    assert config.deployment_mode == DeploymentMode.KUBERNETES
    assert config.namespace == "override"
    assert config.storage_class == "fast"
    assert config.ingress.hostname == "platform.example.com"
    assert config.ingress.tls_enabled is True
    assert config.resources["redis"].replicas == 2
    assert config.model_provider_urls == ["https://models.example.com/health"]


def test_load_config_without_file_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLATFORM_CLI_NAMESPACE", raising=False)

    config = load_config(None)

    assert config.namespace == "platform"
    assert config.data_dir.name == "data"


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(missing)


def test_load_config_requires_mapping_root(tmp_path: Path) -> None:
    config_path = tmp_path / "platform-install.yaml"
    config_path.write_text("- invalid\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(config_path)


def test_environment_prefix_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_CLI_AIR_GAPPED", "true")
    config = load_config(None)
    assert config.air_gapped is True

    monkeypatch.delenv("PLATFORM_CLI_AIR_GAPPED", raising=False)
