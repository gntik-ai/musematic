"""MinIO backup implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from platform_cli.backup.stores.common import build_artifact
from platform_cli.models import BackupArtifact


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "minio backup failed")


class MinIOBackup:
    """Mirror MinIO buckets with the ``mc`` CLI."""

    def __init__(self, source_alias: str = "platform", bucket: str = "platform-assets") -> None:
        self.source_alias = source_alias
        self.bucket = bucket

    async def backup(self, output_dir: Path) -> BackupArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / self.bucket
        _run(["mc", "mirror", f"{self.source_alias}/{self.bucket}", str(destination)])
        manifest = output_dir / "minio.mirror"
        manifest.write_text(str(destination), encoding="utf-8")
        return build_artifact(
            store="minio", display_name="MinIO", path=manifest, format_name="mirror"
        )

    async def restore(self, artifact_path: Path) -> bool:
        destination = artifact_path.read_text(encoding="utf-8").strip()
        _run(["mc", "mirror", destination, f"{self.source_alias}/{self.bucket}"])
        return True
