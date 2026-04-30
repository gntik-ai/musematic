"""Vault migration manifest helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ManifestEntry:
    """Single K8s Secret key migration result."""

    k8s_secret_namespace: str
    k8s_secret_name: str
    k8s_secret_key: str
    vault_path: str
    value_sha256: str
    success: bool
    reason: str = ""
    already_migrated: bool = False


@dataclass(slots=True)
class VaultMigrationManifest:
    """JSON manifest emitted by `platform-cli vault migrate-from-k8s`."""

    timestamp: str
    env: str
    entries: list[ManifestEntry]
    success_count: int = 0
    failure_count: int = 0
    already_migrated_count: int = 0
    new_count: int = 0

    def recalculate_totals(self) -> None:
        self.success_count = sum(1 for entry in self.entries if entry.success)
        self.failure_count = sum(1 for entry in self.entries if not entry.success)
        self.already_migrated_count = sum(1 for entry in self.entries if entry.already_migrated)
        self.new_count = sum(
            1 for entry in self.entries if entry.success and not entry.already_migrated
        )

    def to_dict(self) -> dict[str, Any]:
        self.recalculate_totals()
        return {
            "timestamp": self.timestamp,
            "env": self.env,
            "entries": [asdict(entry) for entry in self.entries],
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "already_migrated_count": self.already_migrated_count,
            "new_count": self.new_count,
        }


def sha256_value(value: bytes) -> str:
    """Return the SHA-256 hex digest for a secret value."""

    return hashlib.sha256(value).hexdigest()


def new_manifest(environment: str, entries: list[ManifestEntry]) -> VaultMigrationManifest:
    """Create a manifest with a UTC timestamp."""

    manifest = VaultMigrationManifest(
        timestamp=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        env=environment,
        entries=entries,
    )
    manifest.recalculate_totals()
    return manifest


def write_manifest(manifest: VaultMigrationManifest, output_dir: Path) -> Path:
    """Write the manifest to `vault-migration-{timestamp}.json`."""

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"vault-migration-{manifest.timestamp}.json"
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_manifest(path: Path) -> VaultMigrationManifest:
    """Read a manifest from disk."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = [ManifestEntry(**entry) for entry in payload.get("entries", [])]
    manifest = VaultMigrationManifest(
        timestamp=str(payload.get("timestamp", "")),
        env=str(payload.get("env", "")),
        entries=entries,
    )
    manifest.recalculate_totals()
    return manifest
