from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from platform_cli.backup.manifest import BackupManifestManager
from platform_cli.backup.orchestrator import BackupOrchestrator, BackupVerificationError
from platform_cli.backup.stores.clickhouse import ClickHouseBackup
from platform_cli.backup.stores.common import build_artifact, sha256_file
from platform_cli.backup.stores.kafka import KafkaBackup
from platform_cli.backup.stores.minio import MinIOBackup
from platform_cli.backup.stores.neo4j import Neo4jBackup
from platform_cli.backup.stores.opensearch import OpenSearchBackup
from platform_cli.backup.stores.postgresql import PostgreSQLBackup
from platform_cli.backup.stores.qdrant import QdrantBackup
from platform_cli.backup.stores.redis import RedisBackup
from platform_cli.commands import backup as backup_commands
from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.main import app
from platform_cli.models import (
    CURRENT_SCHEMA_VERSION,
    BackupArtifact,
    BackupManifest,
    BackupStatus,
)


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
        if "snapshots/upload" in url:
            return FakeResponse(text="uploaded")
        return FakeResponse()

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    async def put(self, url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse(text="snapshot-created")


class FakeRedisClient:
    def __init__(self) -> None:
        self._lastsave = 1

    async def lastsave(self) -> int:
        return self._lastsave

    async def bgsave(self) -> None:
        self._lastsave = 2

    async def aclose(self) -> None:
        return None


@dataclass(frozen=True)
class FakeTopicPartition:
    topic: str
    partition: int


@dataclass
class FakeOffsetAndMetadata:
    offset: int
    metadata: str


class FakeKafkaAdminClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.alter_calls: list[tuple[str, dict[object, object]]] = []

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def list_consumer_groups(self) -> list[tuple[str, str]]:
        return [("group-a", "consumer")]

    async def list_consumer_group_offsets(
        self, group_id: str
    ) -> dict[FakeTopicPartition, FakeOffsetAndMetadata]:
        assert group_id == "group-a"
        return {FakeTopicPartition("platform.events", 0): FakeOffsetAndMetadata(42, "")}

    async def alter_consumer_group_offsets(
        self, group_id: str, offsets: dict[object, object]
    ) -> None:
        self.alter_calls.append((group_id, offsets))


class FakeStore:
    def __init__(
        self,
        name: str,
        backup_calls: list[str],
        restore_calls: list[str],
        *,
        duration_seconds: float = 1.25,
    ) -> None:
        self.name = name
        self.backup_calls = backup_calls
        self.restore_calls = restore_calls
        self.duration_seconds = duration_seconds

    async def backup(self, output_dir: Path) -> BackupArtifact:
        self.backup_calls.append(self.name)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{self.name}.bin"
        path.write_text(self.name, encoding="utf-8")
        return build_artifact(
            store=self.name,
            display_name=self.name.title(),
            path=path,
            format_name="raw",
            duration_seconds=self.duration_seconds,
        )

    async def restore(self, artifact_path: Path) -> bool:
        assert artifact_path.exists()
        self.restore_calls.append(self.name)
        return True


def _config(tmp_path: Path) -> InstallerConfig:
    return InstallerConfig(deployment_mode=DeploymentMode.LOCAL, data_dir=tmp_path)


def _store_map(backup_calls: list[str], restore_calls: list[str]) -> dict[str, FakeStore]:
    return {
        name: FakeStore(name, backup_calls, restore_calls)
        for name in BackupOrchestrator.BACKUP_ORDER
    }


def _install_fake_aiokafka(monkeypatch: pytest.MonkeyPatch) -> FakeKafkaAdminClient:
    admin = FakeKafkaAdminClient()
    monkeypatch.setitem(
        sys.modules,
        "aiokafka",
        SimpleNamespace(TopicPartition=FakeTopicPartition),
    )
    monkeypatch.setitem(
        sys.modules,
        "aiokafka.admin",
        SimpleNamespace(AIOKafkaAdminClient=lambda *args, **kwargs: admin),
    )
    monkeypatch.setitem(
        sys.modules,
        "aiokafka.structs",
        SimpleNamespace(OffsetAndMetadata=FakeOffsetAndMetadata),
    )
    return admin


def test_common_backup_helpers(tmp_path: Path) -> None:
    path = tmp_path / "artifact.txt"
    path.write_text("payload", encoding="utf-8")

    checksum = sha256_file(path)
    artifact = build_artifact(
        store="test",
        display_name="Test",
        path=path,
        format_name="raw",
        duration_seconds=3.5,
    )

    assert len(checksum) == 64
    assert artifact.store == "test"
    assert artifact.size_bytes == path.stat().st_size
    assert artifact.duration_seconds == pytest.approx(3.5)


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
    monkeypatch.setitem(
        sys.modules,
        "redis.asyncio",
        SimpleNamespace(
            Redis=SimpleNamespace(from_url=lambda url, decode_responses=True: FakeRedisClient())
        ),
    )

    pg_artifact = await PostgreSQLBackup("postgresql://db").backup(tmp_path)
    redis_backup = RedisBackup("redis://localhost", tmp_path / "redis.rdb")
    redis_backup.rdb_path.write_text("redis", encoding="utf-8")
    redis_artifact = await redis_backup.backup(tmp_path / "redis-store")
    neo_artifact = await Neo4jBackup().backup(tmp_path)
    click_artifact = await ClickHouseBackup().backup(tmp_path)
    minio_artifact = await MinIOBackup().backup(tmp_path)

    assert pg_artifact.store == "postgresql"
    assert redis_artifact.store == "redis"
    assert neo_artifact.store == "neo4j"
    assert click_artifact.store == "clickhouse"
    assert minio_artifact.store == "minio"
    assert all(artifact.duration_seconds >= 0.0 for artifact in [pg_artifact, redis_artifact])
    assert any(command[0] == "pg_dump" for command in commands)


@pytest.mark.asyncio
async def test_http_and_kafka_backup_stores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("platform_cli.backup.stores.qdrant.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("platform_cli.backup.stores.opensearch.httpx.AsyncClient", FakeAsyncClient)
    fake_admin = _install_fake_aiokafka(monkeypatch)

    qdrant_artifact = await QdrantBackup("http://qdrant").backup(tmp_path / "qdrant")
    opensearch_artifact = await OpenSearchBackup("http://opensearch").backup(tmp_path / "search")
    kafka_artifact = await KafkaBackup("127.0.0.1:9092").backup(tmp_path / "kafka")

    payload = json.loads(Path(kafka_artifact.path).read_text(encoding="utf-8"))
    assert qdrant_artifact.store == "qdrant"
    assert opensearch_artifact.store == "opensearch"
    assert kafka_artifact.store == "kafka"
    assert payload["consumer_groups"][0]["group_id"] == "group-a"
    assert await QdrantBackup("http://qdrant").restore(Path(qdrant_artifact.path)) is True
    assert (
        await OpenSearchBackup("http://opensearch").restore(Path(opensearch_artifact.path)) is True
    )
    assert await KafkaBackup("127.0.0.1:9092").restore(Path(kafka_artifact.path)) is True
    assert fake_admin.alter_calls[0][0] == "group-a"


def test_manifest_manager_round_trip_and_resolution(tmp_path: Path) -> None:
    manager = BackupManifestManager(tmp_path)
    artifact = BackupArtifact(
        store="postgresql",
        display_name="PostgreSQL",
        path="/tmp/file",
        size_bytes=1,
        checksum_sha256="a" * 64,
        format="pg_dump",
        created_at="2026-01-01T00:00:00+00:00",
        duration_seconds=1.0,
    )
    manifest = manager.create(
        DeploymentMode.LOCAL,
        "daily-backup",
        [artifact],
        BackupStatus.COMPLETED,
    )

    loaded = manager.load(manifest.backup_id)
    by_prefix = manager.load("daily")
    listed = manager.list(limit=10)

    assert loaded.backup_id == manifest.backup_id
    assert by_prefix.backup_id == manifest.backup_id
    assert listed[0].backup_id == manifest.backup_id
    assert loaded.schema_version == CURRENT_SCHEMA_VERSION
    assert loaded.total_duration_seconds == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_backup_orchestrator_create_restore_and_verify(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    orchestrator = BackupOrchestrator(config, storage_root=tmp_path / "backups")
    backup_calls: list[str] = []
    restore_calls: list[str] = []
    lock_events: list[str] = []

    monkeypatch.setattr(orchestrator, "_stores", lambda: _store_map(backup_calls, restore_calls))

    async def no_active_executions() -> bool:
        return False

    monkeypatch.setattr(orchestrator, "_has_active_executions", no_active_executions)

    class FakeLock:
        def acquire(self, timeout_minutes: int = 30) -> bool:
            lock_events.append("acquire")
            return True

        def release(self) -> None:
            lock_events.append("release")

    monkeypatch.setattr("platform_cli.backup.orchestrator.FileLock", lambda path: FakeLock())

    manifest = await orchestrator.create(None, force=False, headless=True)
    assert manifest.status == BackupStatus.COMPLETED
    assert manifest.tag is not None
    assert manifest.tag.startswith("backup-")
    assert [artifact.store for artifact in manifest.artifacts] == list(
        BackupOrchestrator.BACKUP_ORDER
    )
    assert backup_calls == list(BackupOrchestrator.BACKUP_ORDER)
    assert lock_events == ["acquire", "release"]
    assert all(artifact.duration_seconds == pytest.approx(1.25) for artifact in manifest.artifacts)
    assert manifest.schema_version == CURRENT_SCHEMA_VERSION
    assert manifest.total_duration_seconds >= 0.0

    assert await orchestrator.restore(manifest.backup_id, verify_only=True, headless=True) is True
    assert await orchestrator.restore(manifest.backup_id, verify_only=False, headless=True) is True
    assert restore_calls == list(BackupOrchestrator.RESTORE_ORDER)


@pytest.mark.asyncio
async def test_backup_orchestrator_restore_variants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    orchestrator = BackupOrchestrator(config, storage_root=tmp_path / "backups")
    backup_calls: list[str] = []
    restore_calls: list[str] = []
    monkeypatch.setattr(orchestrator, "_stores", lambda: _store_map(backup_calls, restore_calls))
    monkeypatch.setattr(orchestrator, "_acquire_lock", lambda holder_id: lambda: None)

    async def no_active_executions() -> bool:
        return False

    monkeypatch.setattr(orchestrator, "_has_active_executions", no_active_executions)
    manifest = await orchestrator.create("nightly", force=False, headless=True)

    restore_calls.clear()
    assert (
        await orchestrator.restore(
            manifest.backup_id,
            stores_filter={"redis"},
            verify_only=False,
            headless=True,
        )
        is True
    )
    assert restore_calls == ["redis"]

    manifest = manifest.model_copy(update={"schema_version": CURRENT_SCHEMA_VERSION + 1})
    orchestrator.manifests.save(manifest)
    with pytest.raises(RuntimeError, match="upgrade platform-cli"):
        await orchestrator.restore(manifest.backup_id, verify_only=True, headless=True)


@pytest.mark.asyncio
async def test_backup_orchestrator_rejects_invalid_tag_and_checksum_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    orchestrator = BackupOrchestrator(config, storage_root=tmp_path / "backups")
    backup_calls: list[str] = []
    restore_calls: list[str] = []
    monkeypatch.setattr(orchestrator, "_stores", lambda: _store_map(backup_calls, restore_calls))
    monkeypatch.setattr(orchestrator, "_acquire_lock", lambda holder_id: lambda: None)

    async def no_active_executions() -> bool:
        return False

    monkeypatch.setattr(orchestrator, "_has_active_executions", no_active_executions)

    with pytest.raises(ValueError, match="backup tag"):
        await orchestrator.create("bad tag!", force=False, headless=True)

    manifest = await orchestrator.create("good-tag", force=False, headless=True)
    Path(manifest.artifacts[0].path).write_text("corrupted", encoding="utf-8")

    with pytest.raises(BackupVerificationError) as exc_info:
        await orchestrator.restore(manifest.backup_id, verify_only=False, headless=True)

    assert restore_calls == []
    assert any(result.error == "checksum mismatch" for result in exc_info.value.results)


def test_restore_command_yes_bypasses_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    manifest = BackupManifest(
        backup_id="bkp-1",
        tag="backup-1",
        sequence_number=1,
        deployment_mode=DeploymentMode.LOCAL,
        status=BackupStatus.COMPLETED,
        created_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:01:00+00:00",
        artifacts=[
            BackupArtifact(
                store="redis",
                display_name="Redis",
                path="/tmp/redis.rdb",
                size_bytes=1,
                checksum_sha256="a" * 64,
                format="rdb",
                created_at="2026-01-01T00:00:00+00:00",
                duration_seconds=1.0,
            )
        ],
        total_size_bytes=1,
        storage_location=str(tmp_path / "backups" / "bkp-1"),
    )

    class FakeOrchestrator:
        RESTORE_ORDER = BackupOrchestrator.RESTORE_ORDER

        def __init__(self, config: InstallerConfig) -> None:
            self.manifests = SimpleNamespace(load=lambda backup_id: manifest)

        async def restore(
            self,
            backup_id: str,
            stores_filter: set[str] | None = None,
            *,
            verify_only: bool = False,
            headless: bool = False,
        ) -> bool:
            return True

    monkeypatch.setattr(backup_commands, "BackupOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        backup_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )
    monkeypatch.setattr(
        backup_commands.typer,
        "confirm",
        lambda message: (_ for _ in ()).throw(AssertionError("confirm should not run")),
    )

    result = CliRunner().invoke(app, ["backup", "restore", "bkp-1", "--yes"])
    assert result.exit_code == 0


def test_restore_command_invalid_store_lists_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    manifest = BackupManifest(
        backup_id="bkp-1",
        tag="backup-1",
        sequence_number=1,
        deployment_mode=DeploymentMode.LOCAL,
        status=BackupStatus.COMPLETED,
        created_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:01:00+00:00",
        artifacts=[
            BackupArtifact(
                store="redis",
                display_name="Redis",
                path="/tmp/redis.rdb",
                size_bytes=1,
                checksum_sha256="a" * 64,
                format="rdb",
                created_at="2026-01-01T00:00:00+00:00",
                duration_seconds=1.0,
            )
        ],
        total_size_bytes=1,
        storage_location=str(tmp_path / "backups" / "bkp-1"),
    )

    class FakeOrchestrator:
        def __init__(self, config: InstallerConfig) -> None:
            self.manifests = SimpleNamespace(load=lambda backup_id: manifest)

    monkeypatch.setattr(backup_commands, "BackupOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        backup_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )

    result = CliRunner().invoke(app, ["backup", "restore", "bkp-1", "--stores", "redis,kafka"])
    assert result.exit_code == 1
    assert "Available stores" in result.output


def test_verify_command_reports_failures_and_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    storage_root = tmp_path / "backups"
    manager = BackupManifestManager(storage_root)
    artifact_path = storage_root / "bkp-1" / "redis" / "redis.rdb"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("redis", encoding="utf-8")
    artifact = build_artifact(
        store="redis",
        display_name="Redis",
        path=artifact_path,
        format_name="rdb",
        duration_seconds=1.0,
    )
    manifest = manager.create(DeploymentMode.LOCAL, "verify", [artifact], BackupStatus.COMPLETED)

    monkeypatch.setattr(
        backup_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )

    runner = CliRunner()
    ok_result = runner.invoke(app, ["--json", "backup", "verify", manifest.backup_id])
    ok_payload = json.loads(ok_result.output.strip().splitlines()[-1])
    assert ok_result.exit_code == 0
    assert ok_payload["status"] == "completed"

    artifact_path.unlink()
    fail_result = runner.invoke(app, ["--json", "backup", "verify", manifest.backup_id])
    fail_payload = json.loads(fail_result.output.strip().splitlines()[-1])
    assert fail_result.exit_code == 1
    assert fail_payload["details"]["results"][0]["error"] == "file missing"


def test_list_command_includes_store_count_and_total_size(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    manager = BackupManifestManager(tmp_path / "backups")
    first_path = tmp_path / "backups" / "bkp-1" / "redis" / "redis.rdb"
    first_path.parent.mkdir(parents=True, exist_ok=True)
    first_path.write_text("redis", encoding="utf-8")
    artifact = build_artifact(
        store="redis",
        display_name="Redis",
        path=first_path,
        format_name="rdb",
        duration_seconds=1.0,
    )
    manager.create(DeploymentMode.LOCAL, "list-test", [artifact], BackupStatus.COMPLETED)

    monkeypatch.setattr(
        backup_commands,
        "load_runtime_config",
        lambda ctx, **overrides: config.model_copy(update=overrides),
    )

    result = CliRunner().invoke(app, ["--json", "backup", "list"])
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert result.exit_code == 0
    assert payload["details"]["items"][0]["store_count"] == 1
    assert payload["details"]["items"][0]["total_size_bytes"] == artifact.size_bytes
