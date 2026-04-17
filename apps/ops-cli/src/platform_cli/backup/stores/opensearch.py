"""OpenSearch snapshot backup implementation."""

from __future__ import annotations

from pathlib import Path
from time import monotonic

import httpx

from platform_cli.backup.stores.common import build_artifact
from platform_cli.models import BackupArtifact


class OpenSearchBackup:
    """Use the OpenSearch snapshot API."""

    def __init__(self, url: str, repository: str = "platform_backup") -> None:
        self.url = url.rstrip("/")
        self.repository = repository

    async def backup(self, output_dir: Path) -> BackupArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        snapshot_name = output_dir.name
        started = monotonic()
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.put(
                f"{self.url}/_snapshot/{self.repository}/{snapshot_name}",
                json={"indices": "*", "include_global_state": True},
            )
        response.raise_for_status()
        path = output_dir / f"{snapshot_name}.json"
        path.write_text(response.text, encoding="utf-8")
        return build_artifact(
            store="opensearch",
            display_name="OpenSearch",
            path=path,
            format_name="snapshot",
            duration_seconds=monotonic() - started,
        )

    async def restore(self, artifact_path: Path) -> bool:
        snapshot_name = artifact_path.stem
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.url}/_snapshot/{self.repository}/{snapshot_name}/_restore"
            )
        response.raise_for_status()
        return True
