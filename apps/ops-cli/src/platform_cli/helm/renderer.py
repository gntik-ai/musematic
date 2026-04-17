"""Render per-component Helm values files from repo charts and CLI config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from platform_cli.config import InstallerConfig
from platform_cli.constants import PlatformComponent
from platform_cli.paths import helm_chart_path
from platform_cli.secrets.generator import GeneratedSecrets


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _component_secret_values(
    component: PlatformComponent, secrets: GeneratedSecrets
) -> dict[str, Any]:
    if component.name == "postgresql":
        return {"auth": {"postgresPassword": secrets.postgresql_password}}
    if component.name == "redis":
        return {"auth": {"password": secrets.redis_password}}
    if component.name == "neo4j":
        return {"neo4j": {"password": secrets.neo4j_password}}
    if component.name == "clickhouse":
        return {"auth": {"password": secrets.clickhouse_password}}
    if component.name == "opensearch":
        return {"auth": {"password": secrets.opensearch_password}}
    if component.name == "minio":
        return {
            "rootUser": secrets.minio_access_key,
            "rootPassword": secrets.minio_secret_key,
        }
    if component.name == "control-plane":
        return {
            "auth": {
                "jwtPrivateKey": secrets.jwt_private_key_pem,
                "jwtPublicKey": secrets.jwt_public_key_pem,
            }
        }
    return {}


def render_values(
    component: PlatformComponent,
    config: InstallerConfig,
    secrets: GeneratedSecrets,
) -> dict[str, Any]:
    """Render merged values for one component."""

    if component.helm_chart is None:
        return {}

    values_path = helm_chart_path(component.helm_chart) / "values.yaml"
    if not values_path.exists():
        raise FileNotFoundError(f"Helm values file not found for chart {component.helm_chart}")

    raw = yaml.safe_load(values_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Chart values for {component.name} must be a YAML mapping")

    override = config.resources.get(component.name)
    overlays: dict[str, Any] = {
        "global": {
            "imageRegistry": config.local_registry if config.air_gapped else config.image_registry,
            "imageTag": config.image_tag,
            "storageClass": config.storage_class,
            "namespacePrefix": config.namespace,
        },
        "component": {"name": component.name},
    }
    if override is not None:
        overlays["resources"] = {
            key: value
            for key, value in override.model_dump(mode="json").items()
            if value is not None
        }
    if component.name == "control-plane":
        overlays["ingress"] = config.ingress.model_dump(mode="json", exclude_none=True)
        overlays["admin"] = config.admin.model_dump(mode="json", exclude_none=True)
    overlays = _deep_merge(overlays, _component_secret_values(component, secrets))
    return _deep_merge(raw, overlays)


def write_values_file(values: dict[str, Any], path: Path) -> Path:
    """Write a rendered values mapping to a YAML file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(values, sort_keys=True), encoding="utf-8")
    return path
