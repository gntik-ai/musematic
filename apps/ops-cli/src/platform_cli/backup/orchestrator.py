"""Sequential backup and restore orchestration."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx

from platform_cli.backup.manifest import BackupManifestManager
from platform_cli.backup.stores.clickhouse import ClickHouseBackup
from platform_cli.backup.stores.common import sha256_file
from platform_cli.backup.stores.minio import MinIOBackup
from platform_cli.backup.stores.neo4j import Neo4jBackup
from platform_cli.backup.stores.opensearch import OpenSearchBackup
from platform_cli.backup.stores.postgresql import PostgreSQLBackup
from platform_cli.backup.stores.qdrant import QdrantBackup
from platform_cli.backup.stores.redis import RedisBackup
from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.models import BackupArtifact, BackupManifest, BackupStatus, utc_now_iso
from platform_cli.runtime import inferred_api_base_url


class BackupOrchestrator:
    """Coordinate per-store backup and restore workflows."""

    def __init__(self, config: InstallerConfig, storage_root: Path | None = None) -> None:
        self.config = config
        self.storage_root = storage_root or Path(
            config.backup_storage or (config.data_dir / "backups")
        )
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.manifests = BackupManifestManager(self.storage_root)

    def _stores(self) -> dict[str, object]:
        if self.config.deployment_mode == DeploymentMode.LOCAL:
            sqlite_dsn = f"sqlite+aiosqlite:///{self.config.data_dir / 'db' / 'platform.db'}"
            return {
                "postgresql": PostgreSQLBackup(sqlite_dsn),
                "redis": RedisBackup(
                    "redis://127.0.0.1:6379/0",
                    self.config.data_dir / "redis.rdb",
                ),
                "qdrant": QdrantBackup("http://127.0.0.1:6333"),
                "neo4j": Neo4jBackup(),
                "clickhouse": ClickHouseBackup(),
                "opensearch": OpenSearchBackup("http://127.0.0.1:9200"),
                "minio": MinIOBackup(),
            }
        namespace = f"{self.config.namespace}-data"
        return {
            "postgresql": PostgreSQLBackup(
                f"postgresql://postgres:password@postgresql.{namespace}.svc.cluster.local:5432/platform"
            ),
            "redis": RedisBackup(
                f"redis://redis.{namespace}.svc.cluster.local:6379/0",
                self.config.data_dir / "redis.rdb",
            ),
            "qdrant": QdrantBackup(f"http://qdrant.{namespace}.svc.cluster.local:6333"),
            "neo4j": Neo4jBackup(),
            "clickhouse": ClickHouseBackup(),
            "opensearch": OpenSearchBackup(f"http://opensearch.{namespace}.svc.cluster.local:9200"),
            "minio": MinIOBackup(),
        }

    async def _has_active_executions(self) -> bool:
        api_url = inferred_api_base_url(self.config)
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{api_url}/api/v1/executions?status=running&limit=1")
            except httpx.HTTPError:
                return False
        if response.status_code != 200:
            return False
        payload = response.json()
        if isinstance(payload, dict):
            items = payload.get("items", [])
            return isinstance(items, list) and len(items) > 0
        return False

    async def create(
        self,
        tag: str | None,
        stores_filter: set[str] | None = None,
        *,
        force: bool = False,
    ) -> BackupManifest:
        """Create a backup manifest and store artifacts sequentially."""

        if not force and await self._has_active_executions():
            raise RuntimeError("active executions detected; rerun with --force to continue")

        artifacts: list[BackupArtifact] = []
        selected = stores_filter or set(self._stores().keys())
        status = BackupStatus.COMPLETED
        backup_id = f"bkp-{uuid4()}"
        created_at = utc_now_iso()
        sequence_number = len(self.manifests.list(limit=10_000)) + 1
        for name, store in self._stores().items():
            if name not in selected:
                continue
            target_dir = self.storage_root / backup_id / name
            try:
                artifact = await store.backup(target_dir)  # type: ignore[attr-defined]
                artifacts.append(artifact)
            except Exception:
                status = BackupStatus.PARTIAL if artifacts else BackupStatus.FAILED
        manifest = BackupManifest(
            backup_id=backup_id,
            tag=tag,
            sequence_number=sequence_number,
            deployment_mode=self.config.deployment_mode,
            status=status,
            created_at=created_at,
            completed_at=utc_now_iso(),
            artifacts=artifacts,
            total_size_bytes=sum(item.size_bytes for item in artifacts),
            storage_location=str(self.storage_root / backup_id),
        )
        return self.manifests.save(manifest)

    async def restore(
        self,
        backup_id: str,
        stores_filter: set[str] | None = None,
        *,
        verify_only: bool = False,
    ) -> bool:
        """Verify and restore a backup manifest."""

        manifest = self.manifests.load(backup_id)
        selected = stores_filter or {artifact.store for artifact in manifest.artifacts}
        artifacts = [artifact for artifact in manifest.artifacts if artifact.store in selected]
        for artifact in artifacts:
            if sha256_file(Path(artifact.path)) != artifact.checksum_sha256:
                raise RuntimeError(f"checksum mismatch for {artifact.store}")
        if verify_only:
            return True
        stores = self._stores()
        for artifact in artifacts:
            await stores[artifact.store].restore(Path(artifact.path))  # type: ignore[attr-defined]
        return True

    def list(self, limit: int = 20) -> list[BackupManifest]:
        """List known manifests."""

        return self.manifests.list(limit=limit)
