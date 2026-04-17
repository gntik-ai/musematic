"""Sequential backup and restore orchestration."""

from __future__ import annotations

import builtins
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from re import Pattern
from re import compile as re_compile
from time import monotonic
from typing import Any, ClassVar, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

from platform_cli.backup.manifest import BackupManifestManager
from platform_cli.backup.stores.clickhouse import ClickHouseBackup
from platform_cli.backup.stores.common import sha256_file
from platform_cli.backup.stores.kafka import KafkaBackup
from platform_cli.backup.stores.minio import MinIOBackup
from platform_cli.backup.stores.neo4j import Neo4jBackup
from platform_cli.backup.stores.opensearch import OpenSearchBackup
from platform_cli.backup.stores.postgresql import PostgreSQLBackup
from platform_cli.backup.stores.qdrant import QdrantBackup
from platform_cli.backup.stores.redis import RedisBackup
from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.locking.file import FileLock
from platform_cli.locking.kubernetes import KubernetesLock
from platform_cli.models import (
    CURRENT_SCHEMA_VERSION,
    BackupArtifact,
    BackupManifest,
    BackupStatus,
    utc_now_iso,
)
from platform_cli.runtime import inferred_api_base_url


class BackupStore(Protocol):
    """Common protocol implemented by per-store backup adapters."""

    async def backup(self, output_dir: Path) -> BackupArtifact:
        """Write a backup artifact into ``output_dir``."""

    async def restore(self, artifact_path: Path) -> bool:
        """Restore a previously created artifact."""


@dataclass(slots=True)
class VerificationResult:
    """Verification outcome for one store artifact."""

    store: str
    ok: bool
    path: str
    expected_checksum: str
    actual_checksum: str | None = None
    error: str | None = None


class BackupVerificationError(RuntimeError):
    """Raised when one or more artifacts fail integrity verification."""

    def __init__(self, results: list[VerificationResult]) -> None:
        self.results = results
        failures = [result for result in results if not result.ok]
        message = (
            failures[0].error
            if failures and failures[0].error
            else "backup verification failed"
        )
        super().__init__(message)


class BackupOrchestrator:
    """Coordinate per-store backup and restore workflows."""

    BACKUP_ORDER: ClassVar[tuple[str, ...]] = (
        "postgresql",
        "qdrant",
        "neo4j",
        "clickhouse",
        "redis",
        "opensearch",
        "kafka",
        "minio",
    )
    RESTORE_ORDER: ClassVar[tuple[str, ...]] = tuple(reversed(BACKUP_ORDER))
    LOCK_NAME: ClassVar[str] = "platform-backup-lock"
    TAG_PATTERN: ClassVar[Pattern[str]] = re_compile(r"^[a-zA-Z0-9_-]+$")

    def __init__(self, config: InstallerConfig, storage_root: Path | None = None) -> None:
        self.config = config
        self.storage_root = storage_root or (config.data_dir / "backups")
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.manifests = BackupManifestManager(self.storage_root)
        self.remote_storage_url = self._normalize_remote_storage(config.backup_storage)
        self.last_verification_results: list[VerificationResult] = []

    def _stores(self) -> dict[str, BackupStore]:
        if self.config.deployment_mode == DeploymentMode.LOCAL:
            sqlite_dsn = f"sqlite+aiosqlite:///{self.config.data_dir / 'db' / 'platform.db'}"
            return {
                "postgresql": PostgreSQLBackup(sqlite_dsn),
                "qdrant": QdrantBackup("http://127.0.0.1:6333"),
                "neo4j": Neo4jBackup(),
                "clickhouse": ClickHouseBackup(),
                "redis": RedisBackup(
                    "redis://127.0.0.1:6379/0",
                    self.config.data_dir / "redis.rdb",
                ),
                "opensearch": OpenSearchBackup("http://127.0.0.1:9200"),
                "kafka": KafkaBackup("127.0.0.1:9092"),
                "minio": MinIOBackup(),
            }

        namespace = f"{self.config.namespace}-data"
        return {
            "postgresql": PostgreSQLBackup(
                f"postgresql://postgres:password@postgresql.{namespace}.svc.cluster.local:5432/platform"
            ),
            "qdrant": QdrantBackup(f"http://qdrant.{namespace}.svc.cluster.local:6333"),
            "neo4j": Neo4jBackup(),
            "clickhouse": ClickHouseBackup(),
            "redis": RedisBackup(
                f"redis://redis.{namespace}.svc.cluster.local:6379/0",
                self.config.data_dir / "redis.rdb",
            ),
            "opensearch": OpenSearchBackup(f"http://opensearch.{namespace}.svc.cluster.local:9200"),
            "kafka": KafkaBackup(f"kafka.{namespace}.svc.cluster.local:9092"),
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
        headless: bool = False,
    ) -> BackupManifest:
        """Create a backup manifest and store artifacts sequentially."""

        sequence_number = len(self.manifests.list(limit=10_000)) + 1
        backup_id = f"bkp-{uuid4()}"
        selected_tag = self._validated_tag(tag, sequence_number)
        artifacts: builtins.list[BackupArtifact] = []
        status = BackupStatus.COMPLETED
        created_at = utc_now_iso()
        started_at = monotonic()
        release_lock = self._acquire_lock(backup_id)
        stores = self._stores()
        selected = self._ordered_names(stores_filter or set(stores.keys()), self.BACKUP_ORDER)
        progress, tasks = self._progress(selected, headless=headless)

        try:
            if not force and await self._has_active_executions():
                raise RuntimeError("active executions detected; rerun with --force to continue")

            if progress is None:
                manifest = await self._create_without_progress(
                    backup_id=backup_id,
                    selected=selected,
                    stores=stores,
                    artifacts=artifacts,
                    status=status,
                )
                status = manifest.status
            else:
                with progress:
                    manifest = await self._create_with_progress(
                        progress=progress,
                        tasks=tasks,
                        backup_id=backup_id,
                        selected=selected,
                        stores=stores,
                        artifacts=artifacts,
                        status=status,
                    )
                    status = manifest.status

            manifest = manifest.model_copy(
                update={
                    "tag": selected_tag,
                    "sequence_number": sequence_number,
                    "created_at": created_at,
                    "completed_at": utc_now_iso(),
                    "total_size_bytes": sum(item.size_bytes for item in artifacts),
                    "storage_location": self._storage_location_for_manifest(backup_id),
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "total_duration_seconds": monotonic() - started_at,
                    "status": status,
                }
            )
            return self.manifests.save(manifest)
        finally:
            release_lock()

    async def restore(
        self,
        backup_id: str,
        stores_filter: set[str] | None = None,
        *,
        verify_only: bool = False,
        headless: bool = False,
    ) -> bool:
        """Verify and restore a backup manifest."""

        manifest = self.manifests.load(backup_id)
        if manifest.schema_version > CURRENT_SCHEMA_VERSION:
            raise RuntimeError(
                "backup schema version is newer than this CLI supports; upgrade platform-cli"
            )

        available = {artifact.store for artifact in manifest.artifacts}
        if stores_filter is not None:
            missing = sorted(stores_filter - available)
            if missing:
                available_list = ", ".join(sorted(available))
                missing_list = ", ".join(missing)
                raise RuntimeError(
                    f"unknown stores requested: {missing_list}. Available stores: {available_list}"
                )

        selected = stores_filter or available
        ordered_artifacts = [
            artifact
            for store_name in self.RESTORE_ORDER
            for artifact in manifest.artifacts
            if artifact.store == store_name and artifact.store in selected
        ]

        verification_results: list[VerificationResult] = []
        staged_paths: dict[str, Path] = {}
        for artifact in ordered_artifacts:
            result, local_path = await self._verify_artifact(manifest, artifact)
            verification_results.append(result)
            if local_path is not None:
                staged_paths[artifact.store] = local_path

        self.last_verification_results = verification_results
        failures = [result for result in verification_results if not result.ok]
        if failures:
            raise BackupVerificationError(verification_results)
        if verify_only:
            return True

        stores = self._stores()
        progress, tasks = self._progress(
            [artifact.store for artifact in ordered_artifacts],
            headless=headless,
        )
        if progress is None:
            for artifact in ordered_artifacts:
                await stores[artifact.store].restore(staged_paths[artifact.store])
            return True

        with progress:
            for artifact in ordered_artifacts:
                task_id = tasks[artifact.store]
                progress.start_task(task_id)
                progress.update(task_id, state="restoring")
                await stores[artifact.store].restore(staged_paths[artifact.store])
                progress.update(
                    task_id,
                    completed=1,
                    icon="[green]✓[/green]",
                    state="restored",
                )
        return True

    def list(self, limit: int = 20) -> list[BackupManifest]:
        """List known manifests."""

        return self.manifests.list(limit=limit)

    async def _create_without_progress(
        self,
        *,
        backup_id: str,
        selected: builtins.list[str],
        stores: dict[str, BackupStore],
        artifacts: builtins.list[BackupArtifact],
        status: BackupStatus,
    ) -> BackupManifest:
        for name in selected:
            try:
                artifact = await stores[name].backup(self.storage_root / backup_id / name)
                if self.remote_storage_url is not None:
                    artifact = await self._upload_artifact(backup_id, artifact)
                artifacts.append(artifact)
            except Exception:
                status = BackupStatus.PARTIAL if artifacts else BackupStatus.FAILED

        return BackupManifest(
            backup_id=backup_id,
            tag=None,
            sequence_number=0,
            deployment_mode=self.config.deployment_mode,
            status=status if artifacts else BackupStatus.FAILED,
            created_at=utc_now_iso(),
            artifacts=artifacts,
            storage_location="",
        )

    async def _create_with_progress(
        self,
        *,
        progress: Progress,
        tasks: dict[str, TaskID],
        backup_id: str,
        selected: builtins.list[str],
        stores: dict[str, BackupStore],
        artifacts: builtins.list[BackupArtifact],
        status: BackupStatus,
    ) -> BackupManifest:
        for name in selected:
            task_id = tasks[name]
            progress.start_task(task_id)
            progress.update(task_id, state="running")
            try:
                artifact = await stores[name].backup(self.storage_root / backup_id / name)
                if self.remote_storage_url is not None:
                    artifact = await self._upload_artifact(backup_id, artifact)
                artifacts.append(artifact)
                progress.update(
                    task_id,
                    completed=1,
                    icon="[green]✓[/green]",
                    state="completed",
                )
            except Exception as exc:
                status = BackupStatus.PARTIAL if artifacts else BackupStatus.FAILED
                progress.update(
                    task_id,
                    completed=1,
                    icon="[red]✗[/red]",
                    state=str(exc) or "failed",
                )

        return BackupManifest(
            backup_id=backup_id,
            tag=None,
            sequence_number=0,
            deployment_mode=self.config.deployment_mode,
            status=status if artifacts else BackupStatus.FAILED,
            created_at=utc_now_iso(),
            artifacts=artifacts,
            storage_location="",
        )

    def _validated_tag(self, tag: str | None, sequence_number: int) -> str:
        if tag is None:
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            return f"backup-{timestamp}-{sequence_number:03d}"
        if not self.TAG_PATTERN.fullmatch(tag):
            raise ValueError(
                "backup tag may only contain letters, numbers, hyphens, and underscores"
            )
        return tag

    def _acquire_lock(self, holder_id: str) -> Callable[[], None]:
        if self.config.deployment_mode == DeploymentMode.KUBERNETES:
            kubernetes_lock = KubernetesLock()
            kubernetes_lock.lock_name = self.LOCK_NAME
            namespace = f"{self.config.namespace}-control"
            if not kubernetes_lock.acquire(namespace, holder_id):
                raise RuntimeError("backup lock could not be acquired")
            return lambda: kubernetes_lock.release(namespace, holder_id)

        file_lock = FileLock(self.config.data_dir / "backup.lock")
        if not file_lock.acquire(timeout_minutes=30):
            raise RuntimeError("backup lock could not be acquired")
        return lambda: file_lock.release()

    def _ordered_names(
        self, selected: set[str], order: tuple[str, ...]
    ) -> builtins.list[str]:
        return [name for name in order if name in selected]

    def _storage_location_for_manifest(self, backup_id: str) -> str:
        if self.remote_storage_url is None:
            return str(self.storage_root / backup_id)
        scheme, bucket, prefix = self._remote_parts(self.remote_storage_url)
        base = f"{scheme}://{bucket}"
        if prefix:
            return f"{base}/{prefix}/{backup_id}"
        return f"{base}/{backup_id}"

    def _normalize_remote_storage(self, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"s3", "minio"}:
            return None
        return value.rstrip("/")

    def _remote_parts(self, value: str) -> tuple[str, str, str]:
        parsed = urlsplit(value)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/").rstrip("/")
        return parsed.scheme, bucket, prefix

    def _progress(
        self, stores: builtins.list[str], *, headless: bool
    ) -> tuple[Progress | None, dict[str, TaskID]]:
        if headless:
            return None, {}

        progress = Progress(
            SpinnerColumn(),
            TextColumn("{task.fields[icon]} {task.fields[store]}"),
            TextColumn("{task.fields[state]}"),
            TimeElapsedColumn(),
        )
        tasks = {
            store: progress.add_task(
                "",
                total=1,
                start=False,
                icon="[dim]•[/dim]",
                store=store,
                state="pending",
            )
            for store in stores
        }
        return progress, tasks

    async def _upload_artifact(self, backup_id: str, artifact: BackupArtifact) -> BackupArtifact:
        import aioboto3

        scheme, bucket, prefix = self._remote_parts(self.remote_storage_url or "")
        artifact_path = Path(artifact.path)
        remote_key = "/".join(
            part for part in [prefix, backup_id, artifact.store, artifact_path.name] if part
        )
        session = aioboto3.Session()
        client_kwargs = self._s3_client_kwargs(scheme)
        async with session.client("s3", **client_kwargs) as client:
            await client.put_object(
                Bucket=bucket,
                Key=remote_key,
                Body=artifact_path.read_bytes(),
            )
        return artifact.model_copy(update={"path": remote_key})

    async def _verify_artifact(
        self,
        manifest: BackupManifest,
        artifact: BackupArtifact,
    ) -> tuple[VerificationResult, Path | None]:
        try:
            local_path = await self._materialize_artifact(manifest, artifact)
        except FileNotFoundError:
            return (
                VerificationResult(
                    store=artifact.store,
                    ok=False,
                    path=artifact.path,
                    expected_checksum=artifact.checksum_sha256,
                    error="file missing",
                ),
                None,
            )
        except Exception as exc:
            return (
                VerificationResult(
                    store=artifact.store,
                    ok=False,
                    path=artifact.path,
                    expected_checksum=artifact.checksum_sha256,
                    error=str(exc),
                ),
                None,
            )

        actual_checksum = sha256_file(local_path)
        if actual_checksum != artifact.checksum_sha256:
            return (
                VerificationResult(
                    store=artifact.store,
                    ok=False,
                    path=artifact.path,
                    expected_checksum=artifact.checksum_sha256,
                    actual_checksum=actual_checksum,
                    error="checksum mismatch",
                ),
                local_path,
            )
        return (
            VerificationResult(
                store=artifact.store,
                ok=True,
                path=artifact.path,
                expected_checksum=artifact.checksum_sha256,
                actual_checksum=actual_checksum,
            ),
            local_path,
        )

    async def _materialize_artifact(
        self, manifest: BackupManifest, artifact: BackupArtifact
    ) -> Path:
        path = Path(artifact.path)
        if path.exists():
            return path
        if not manifest.storage_location.startswith(("s3://", "minio://")):
            raise FileNotFoundError(artifact.path)

        import aioboto3

        scheme, bucket, _prefix = self._remote_parts(manifest.storage_location.rsplit("/", 1)[0])
        session = aioboto3.Session()
        client_kwargs = self._s3_client_kwargs(scheme)
        local_path = (
            self.storage_root / ".downloads" / manifest.backup_id / artifact.store / path.name
        )
        local_path.parent.mkdir(parents=True, exist_ok=True)
        async with session.client("s3", **client_kwargs) as client:
            response = await client.get_object(Bucket=bucket, Key=artifact.path)
            body = response["Body"]
            payload = await body.read()
        local_path.write_bytes(payload)
        return local_path

    def _s3_client_kwargs(self, scheme: str) -> dict[str, Any]:
        if scheme == "s3":
            return {}
        return {
            "endpoint_url": self._minio_endpoint(),
            "aws_access_key_id": self.config.secrets.minio_access_key or "minio",
            "aws_secret_access_key": self.config.secrets.minio_secret_key or "minio-secret",
        }

    def _minio_endpoint(self) -> str:
        if self.config.deployment_mode == DeploymentMode.LOCAL:
            return "http://127.0.0.1:9000"
        return f"http://minio.{self.config.namespace}-data.svc.cluster.local:9000"
