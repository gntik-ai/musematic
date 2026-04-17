"""Configuration models and loading utilities for the platform CLI."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploymentMode(StrEnum):
    """Target deployment environment."""

    KUBERNETES = "kubernetes"
    DOCKER = "docker"
    SWARM = "swarm"
    INCUS = "incus"
    LOCAL = "local"


class ExitCode(StrEnum):
    """Stable exit codes for automation consumers."""

    SUCCESS = "0"
    GENERAL_ERROR = "1"
    PREFLIGHT_FAILURE = "2"
    PARTIAL_FAILURE = "3"


class IngressConfig(BaseModel):
    """Ingress controller configuration."""

    enabled: bool = True
    hostname: str = "platform.local"
    tls_enabled: bool = False
    tls_secret_name: str | None = None


class ResourceOverride(BaseModel):
    """Per-component resource overrides."""

    replicas: int | None = None
    storage: str | None = None
    cpu_limit: str | None = None
    memory_limit: str | None = None


class AdminConfig(BaseModel):
    """Initial administrator account configuration."""

    email: str = "admin@platform.local"


class SecretsConfig(BaseModel):
    """Provided or generated secret configuration."""

    generate: bool = True
    postgresql_password: str | None = None
    redis_password: str | None = None
    neo4j_password: str | None = None
    clickhouse_password: str | None = None
    opensearch_password: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    jwt_private_key_pem: str | None = None


class InstallerConfig(BaseSettings):
    """Top-level installer configuration."""

    deployment_mode: DeploymentMode = DeploymentMode.KUBERNETES
    namespace: str = "platform"
    storage_class: str = "standard"
    ingress: IngressConfig = Field(default_factory=IngressConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    resources: dict[str, ResourceOverride] = Field(default_factory=dict)
    image_registry: str = "ghcr.io"
    image_tag: str = "latest"
    air_gapped: bool = False
    local_registry: str | None = None
    data_dir: Path = Path.home() / ".platform-cli" / "data"
    backup_storage: str | None = None
    api_base_url: str | None = None
    auth_token: str | None = None
    model_provider_urls: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        env_prefix="PLATFORM_CLI_",
        env_nested_delimiter="__",
        extra="ignore",
        validate_default=True,
    )


def _parse_env_value(value: str) -> Any:
    parsed = yaml.safe_load(value)
    if parsed is None and value.strip().lower() not in {"null", "~", ""}:
        return value
    return parsed


def _set_nested_value(target: dict[str, Any], path: list[str], value: Any) -> None:
    cursor = target
    for segment in path[:-1]:
        next_value = cursor.get(segment)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[segment] = next_value
        cursor = next_value
    cursor[path[-1]] = value


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
            continue
        merged[key] = value
    return merged


def _collect_env_overrides() -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    prefix = InstallerConfig.model_config.get("env_prefix", "PLATFORM_CLI_")
    assert isinstance(prefix, str)
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        stripped = key[len(prefix) :]
        if not stripped or stripped == "CONFIG":
            continue
        path = [segment.lower() for segment in stripped.split("__") if segment]
        if not path:
            continue
        _set_nested_value(overrides, path, _parse_env_value(value))
    return overrides


def load_config(path: Path | None) -> InstallerConfig:
    """Load configuration from YAML, then apply environment overrides."""

    yaml_values: dict[str, Any] = {}
    if path is not None:
        config_path = path.expanduser()
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if raw is None:
            yaml_values = {}
        elif isinstance(raw, dict):
            yaml_values = raw
        else:
            raise ValueError("Installer config must contain a YAML mapping at the root.")

    merged = _deep_merge(yaml_values, _collect_env_overrides())
    return InstallerConfig.model_validate(merged)
