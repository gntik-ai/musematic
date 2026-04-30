"""Kubernetes Secret to Vault migration helpers."""

from __future__ import annotations

import base64
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from platform_cli.secrets.manifest import (
    ManifestEntry,
    VaultMigrationManifest,
    load_manifest,
    new_manifest,
    sha256_value,
    write_manifest,
)

VALID_ENVIRONMENTS = {"production", "staging", "dev", "test", "ci"}
VALID_DOMAINS = {
    "oauth",
    "model-providers",
    "notifications",
    "ibor",
    "audit-chain",
    "connectors",
    "accounts",
}
SECRET_NAME_RE = re.compile(
    r"^musematic-(production|staging|dev|test|ci)-"
    r"(oauth|model-providers|notifications|ibor|audit-chain|connectors|accounts)-(.+)$"
)


@dataclass(frozen=True, slots=True)
class KubernetesSecretValue:
    """Decoded Kubernetes Secret key value."""

    namespace: str
    name: str
    key: str
    value: bytes


class SecretReader(Protocol):
    """Reads decoded Kubernetes Secret values."""

    def iter_values(self, namespaces: list[str]) -> list[KubernetesSecretValue]: ...


class VaultWriter(Protocol):
    """Minimal Vault access used by migration and verification."""

    def get(self, path: str, key: str) -> bytes | None: ...

    def put(self, path: str, key: str, value: bytes) -> None: ...


class KubernetesCLISecretReader:
    """Kubernetes Secret reader backed by `kubectl get secrets -o json`."""

    def iter_values(self, namespaces: list[str]) -> list[KubernetesSecretValue]:
        values: list[KubernetesSecretValue] = []
        for namespace in namespaces:
            completed = subprocess.run(
                ["kubectl", "get", "secrets", "-n", namespace, "-o", "json"],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(completed.stdout or "{}")
            for item in payload.get("items", []):
                metadata = item.get("metadata", {})
                name = str(metadata.get("name", ""))
                data = item.get("data", {})
                if not isinstance(data, dict):
                    continue
                for key, encoded in data.items():
                    if not isinstance(encoded, str):
                        continue
                    values.append(
                        KubernetesSecretValue(
                            namespace=namespace,
                            name=name,
                            key=str(key),
                            value=base64.b64decode(encoded),
                        )
                    )
        return values


class VaultCLIProvider:
    """Vault KV v2 provider backed by the `vault` CLI."""

    def get(self, path: str, key: str) -> bytes | None:
        completed = subprocess.run(
            ["vault", "kv", "get", f"-field={key}", _vault_cli_path(path)],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout.rstrip(b"\n")

    def put(self, path: str, key: str, value: bytes) -> None:
        subprocess.run(
            ["vault", "kv", "put", _vault_cli_path(path), f"{key}={value.decode('utf-8')}"],
            check=True,
            capture_output=True,
            text=True,
        )


def vault_path_from_k8s_secret_name(name: str) -> str:
    """Map `musematic-{env}-{domain}-{resource}` to a canonical Vault path."""

    match = SECRET_NAME_RE.fullmatch(name)
    if not match:
        raise ValueError("invalid_name")
    environment, domain, resource = match.groups()
    resource = resource.replace("__", "/")
    path = f"secret/data/musematic/{environment}/{domain}/{resource}"
    validate_vault_path(path)
    return path


def validate_vault_path(path: str) -> None:
    """Validate the canonical Vault KV v2 path shape."""

    parts = path.split("/")
    if (
        len(parts) < 6
        or parts[:3] != ["secret", "data", "musematic"]
        or parts[3] not in VALID_ENVIRONMENTS
        or parts[4] not in VALID_DOMAINS
    ):
        raise ValueError("invalid_path")


def default_namespaces() -> list[str]:
    """Namespaces scanned by default for migration."""

    return [
        "platform",
        "platform-runtime",
        "platform-reasoning",
        "platform-simulation",
        "platform-sandbox",
    ]


def migrate_from_k8s(
    *,
    namespaces: list[str] | None = None,
    environment: str = "production",
    apply: bool = False,
    output_dir: Path = Path.cwd(),
    reader: SecretReader | None = None,
    vault: VaultWriter | None = None,
) -> tuple[VaultMigrationManifest, Path]:
    """Scan K8s Secrets, optionally write to Vault, and emit a SHA-256 manifest."""

    selected_namespaces = namespaces or default_namespaces()
    secret_reader = reader or KubernetesCLISecretReader()
    vault_writer = vault or VaultCLIProvider()
    entries: list[ManifestEntry] = []

    for secret in secret_reader.iter_values(selected_namespaces):
        if not secret.name.startswith("musematic-"):
            continue
        value_sha256 = sha256_value(secret.value)
        try:
            vault_path = vault_path_from_k8s_secret_name(secret.name)
        except ValueError as exc:
            entries.append(
                ManifestEntry(
                    k8s_secret_namespace=secret.namespace,
                    k8s_secret_name=secret.name,
                    k8s_secret_key=secret.key,
                    vault_path="",
                    value_sha256=value_sha256,
                    success=False,
                    reason=str(exc),
                )
            )
            continue

        if not apply:
            entries.append(
                ManifestEntry(
                    k8s_secret_namespace=secret.namespace,
                    k8s_secret_name=secret.name,
                    k8s_secret_key=secret.key,
                    vault_path=vault_path,
                    value_sha256=value_sha256,
                    success=True,
                )
            )
            continue

        try:
            existing = vault_writer.get(vault_path, secret.key)
            if existing is not None and sha256_value(existing) == value_sha256:
                entries.append(
                    ManifestEntry(
                        k8s_secret_namespace=secret.namespace,
                        k8s_secret_name=secret.name,
                        k8s_secret_key=secret.key,
                        vault_path=vault_path,
                        value_sha256=value_sha256,
                        success=True,
                        already_migrated=True,
                    )
                )
                continue
            vault_writer.put(vault_path, secret.key, secret.value)
            entries.append(
                ManifestEntry(
                    k8s_secret_namespace=secret.namespace,
                    k8s_secret_name=secret.name,
                    k8s_secret_key=secret.key,
                    vault_path=vault_path,
                    value_sha256=value_sha256,
                    success=True,
                )
            )
        except Exception as exc:
            entries.append(
                ManifestEntry(
                    k8s_secret_namespace=secret.namespace,
                    k8s_secret_name=secret.name,
                    k8s_secret_key=secret.key,
                    vault_path=vault_path,
                    value_sha256=value_sha256,
                    success=False,
                    reason=str(exc),
                )
            )

    manifest = new_manifest(environment, entries)
    return manifest, write_manifest(manifest, output_dir)


def verify_migration(
    manifest_path: Path,
    *,
    vault: VaultWriter | None = None,
) -> VaultMigrationManifest:
    """Verify Vault values against a migration manifest."""

    manifest = load_manifest(manifest_path)
    vault_writer = vault or VaultCLIProvider()
    verified_entries: list[ManifestEntry] = []
    for entry in manifest.entries:
        if not entry.success or not entry.vault_path:
            verified_entries.append(entry)
            continue
        current = vault_writer.get(entry.vault_path, entry.k8s_secret_key)
        if current is None:
            verified_entries.append(
                ManifestEntry(**{**asdict(entry), "success": False, "reason": "missing"})
            )
            continue
        matches = sha256_value(current) == entry.value_sha256
        verified_entries.append(
            ManifestEntry(
                **{
                    **asdict(entry),
                    "success": matches,
                    "reason": "" if matches else "sha256_mismatch",
                }
            )
        )
    return new_manifest(manifest.env, verified_entries)


def _vault_cli_path(path: str) -> str:
    validate_vault_path(path)
    return path.replace("secret/data/", "secret/", 1)
