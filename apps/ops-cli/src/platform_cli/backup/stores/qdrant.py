"""Qdrant backup implementation."""

from __future__ import annotations

from pathlib import Path

import httpx

from platform_cli.backup.stores.common import build_artifact
from platform_cli.models import BackupArtifact


class QdrantBackup:
    """Use the Qdrant snapshots API."""

    def __init__(self, url: str, collection_name: str = "platform_documents") -> None:
        self.url = url.rstrip("/")
        self.collection_name = collection_name

    async def backup(self, output_dir: Path) -> BackupArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{self.url}/collections/{self.collection_name}/snapshots")
            response.raise_for_status()
            snapshot_name = response.json()["result"]["name"]
            download = await client.get(
                f"{self.url}/collections/{self.collection_name}/snapshots/{snapshot_name}"
            )
            download.raise_for_status()
        path = output_dir / snapshot_name
        path.write_bytes(download.content)
        return build_artifact(
            store="qdrant", display_name="Qdrant", path=path, format_name="snapshot"
        )

    async def restore(self, artifact_path: Path) -> bool:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.url}/collections/{self.collection_name}/snapshots/upload",
                files={"snapshot": artifact_path.read_bytes()},
            )
        response.raise_for_status()
        return True
