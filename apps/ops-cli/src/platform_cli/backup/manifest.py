"""Backup manifest persistence."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from platform_cli.config import DeploymentMode
from platform_cli.models import BackupArtifact, BackupManifest, BackupStatus, utc_now_iso


class BackupManifestManager:
    """Read and write backup manifests on local storage."""

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root
        self.manifest_dir = self.storage_root / "manifests"
        self.manifest_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        deployment_mode: DeploymentMode,
        tag: str | None,
        artifacts: list[BackupArtifact],
        status: BackupStatus,
    ) -> BackupManifest:
        """Create and persist a new manifest."""

        sequence_number = len(list(self.manifest_dir.glob("*.json"))) + 1
        backup_id = f"bkp-{uuid4()}"
        manifest = BackupManifest(
            backup_id=backup_id,
            tag=tag,
            sequence_number=sequence_number,
            deployment_mode=deployment_mode,
            status=status,
            created_at=utc_now_iso(),
            completed_at=utc_now_iso() if status != BackupStatus.IN_PROGRESS else None,
            artifacts=artifacts,
            total_size_bytes=sum(item.size_bytes for item in artifacts),
            storage_location=str(self.storage_root / backup_id),
        )
        self._write(manifest)
        return manifest

    def save(self, manifest: BackupManifest) -> BackupManifest:
        """Persist an existing manifest object."""

        self._write(manifest)
        return manifest

    def load(self, backup_id: str) -> BackupManifest:
        """Load one manifest by backup ID."""

        path = self.manifest_dir / f"{backup_id}.json"
        return BackupManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, limit: int = 20) -> list[BackupManifest]:
        """List manifests newest-first by sequence number."""

        manifests = [
            BackupManifest.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self.manifest_dir.glob("*.json")
        ]
        return sorted(manifests, key=lambda item: item.sequence_number, reverse=True)[:limit]

    def _write(self, manifest: BackupManifest) -> None:
        path = self.manifest_dir / f"{manifest.backup_id}.json"
        path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
