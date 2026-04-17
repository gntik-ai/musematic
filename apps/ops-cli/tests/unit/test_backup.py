from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from platform_cli.backup.manifest import BackupManifestManager
from platform_cli.backup.orchestrator import BackupOrchestrator
from platform_cli.backup.stores.clickhouse import ClickHouseBackup
from platform_cli.backup.stores.common import build_artifact, sha256_file
from platform_cli.backup.stores.minio import MinIOBackup
from platform_cli.backup.stores.neo4j import Neo4jBackup
from platform_cli.backup.stores.opensearch import OpenSearchBackup
from platform_cli.backup.stores.postgresql import PostgreSQLBackup
from platform_cli.backup.stores.qdrant import QdrantBackup
from platform_cli.backup.stores.redis import RedisBackup
from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.models import BackupArtifact, BackupStatus


class FakeResponse:
    def __init__(self, text: str = "ok", payload: dict[str, object] | None = None) -> None:
        self.text = text
        self._payload = payload or {"result": {"name": "snapshot.bin"}}
        self.content = b"snapshot-data"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class FakeAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        return None

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    async def put(self, url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse(text="snapshot-created")


def test_common_backup_helpers(tmp_path: Path) -> None:
    path = tmp_path / "artifact.txt"
    path.write_text("payload", encoding="utf-8")

    checksum = sha256_file(path)
    artifact = build_artifact(
        store="test",
        display_name="Test",
        path=path,
        format_name="raw",
    )

    assert len(checksum) == 64
    assert artifact.store == "test"
    assert artifact.size_bytes == path.stat().st_size


@pytest.mark.asyncio
async def test_subprocess_based_backup_stores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if command[0] == "pg_dump":
            Path(command[3]).write_text("postgres", encoding="utf-8")
        if command[0] == "neo4j-admin":
            (tmp_path / "neo4j.dump").write_text("neo4j", encoding="utf-8")
        if command[0] == "clickhouse-backup":
            (tmp_path / "platform.clickhouse").write_text("clickhouse", encoding="utf-8")
        if command[0] == "mc":
            (tmp_path / "platform-assets").mkdir(exist_ok=True)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    pg_artifact = await PostgreSQLBackup("postgresql://db").backup(tmp_path)
    (tmp_path / "redis.rdb").write_text("redis", encoding="utf-8")
    monkeypatch.setitem(
        sys.modules,
        "redis.asyncio",
        SimpleNamespace(
            Redis=SimpleNamespace(
                from_url=lambda url, decode_responses=True: SimpleNamespace(
                    bgsave=lambda: None,
                    lastsave=lambda: 1,
                    aclose=lambda: None,
                )
            )
        ),
    )
    redis_backup = RedisBackup("redis://localhost", tmp_path / "redis.rdb")
    redis_backup.rdb_path.write_text("redis", encoding="utf-8")
    redis_restore_source = tmp_path / "redis-restore.rdb"
    redis_restore_source.write_text("redis", encoding="utf-8")
    redis_artifact = await redis_backup.restore(redis_restore_source)
    neo_artifact = await Neo4jBackup().backup(tmp_path)
    click_artifact = await ClickHouseBackup().backup(tmp_path)
    minio_artifact = await MinIOBackup().backup(tmp_path)

    assert pg_artifact.store == "postgresql"
    assert redis_artifact is True
    assert neo_artifact.store == "neo4j"
    assert click_artifact.store == "clickhouse"
    assert minio_artifact.store == "minio"
    assert any(command[0] == "pg_dump" for command in commands)


@pytest.mark.asyncio
async def test_http_backup_stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("platform_cli.backup.stores.qdrant.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("platform_cli.backup.stores.opensearch.httpx.AsyncClient", FakeAsyncClient)

    qdrant_artifact = await QdrantBackup("http://qdrant").backup(tmp_path)
    opensearch_artifact = await OpenSearchBackup("http://opensearch").backup(tmp_path)

    assert qdrant_artifact.store == "qdrant"
    assert opensearch_artifact.store == "opensearch"
    assert await QdrantBackup("http://qdrant").restore(Path(qdrant_artifact.path)) is True
    assert (
        await OpenSearchBackup("http://opensearch").restore(Path(opensearch_artifact.path)) is True
    )


def test_manifest_manager_round_trip(tmp_path: Path) -> None:
    manager = BackupManifestManager(tmp_path)
    artifact = BackupArtifact(
        store="postgresql",
        display_name="PostgreSQL",
        path="/tmp/file",
        size_bytes=1,
        checksum_sha256="a" * 64,
        format="pg_dump",
        created_at="2026-01-01T00:00:00+00:00",
    )
    manifest = manager.create(DeploymentMode.LOCAL, "daily", [artifact], BackupStatus.COMPLETED)
    loaded = manager.load(manifest.backup_id)
    listed = manager.list(limit=10)

    assert loaded.backup_id == manifest.backup_id
    assert listed[0].backup_id == manifest.backup_id


@pytest.mark.asyncio
async def test_backup_orchestrator_create_restore_and_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = InstallerConfig(deployment_mode=DeploymentMode.LOCAL, data_dir=tmp_path)
    orchestrator = BackupOrchestrator(config, storage_root=tmp_path / "backups")

    class FakeStore:
        def __init__(self, name: str) -> None:
            self.name = name

        async def backup(self, output_dir: Path) -> BackupArtifact:
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{self.name}.bin"
            path.write_text(self.name, encoding="utf-8")
            return build_artifact(
                store=self.name,
                display_name=self.name.title(),
                path=path,
                format_name="raw",
            )

        async def restore(self, artifact_path: Path) -> bool:
            return artifact_path.exists()

    monkeypatch.setattr(orchestrator, "_stores", lambda: {"redis": FakeStore("redis")})

    async def no_active_executions() -> bool:
        return False

    monkeypatch.setattr(orchestrator, "_has_active_executions", no_active_executions)

    manifest = await orchestrator.create("nightly", force=True)
    restored = await orchestrator.restore(manifest.backup_id, verify_only=True)
    listed = orchestrator.list(limit=10)

    assert manifest.status == BackupStatus.COMPLETED
    assert restored is True
    assert listed[0].backup_id == manifest.backup_id
