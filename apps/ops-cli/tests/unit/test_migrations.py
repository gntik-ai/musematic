from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.migrations.runner import MigrationRunner
from platform_cli.secrets.generator import generate_secrets


class FakeResponse:
    def __init__(
        self, status_code: int = 200, json_payload: dict[str, object] | None = None
    ) -> None:
        self.status_code = status_code
        self._json_payload = json_payload or {"ok": True}
        self.text = "ok"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self) -> dict[str, object]:
        return self._json_payload


class FakeAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.calls: list[tuple[str, str]] = []

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def put(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("PUT", url))
        return FakeResponse()

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("POST", url))
        return FakeResponse(status_code=202)

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("GET", url))
        return FakeResponse()


def test_run_alembic_invokes_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(
        command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
    ) -> None:
        calls.append((command, env["DATABASE_URL"] if env else None))

    monkeypatch.setattr("platform_cli.migrations.runner._run", fake_run)

    runner = MigrationRunner()
    runner.run_alembic("sqlite+aiosqlite:///tmp/platform.db")

    assert calls[0][0][:4] == ["alembic", "-c", "migrations/alembic.ini", "upgrade"]
    assert calls[0][1] == "sqlite+aiosqlite:///tmp/platform.db"


@pytest.mark.asyncio
async def test_async_migration_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform_cli.migrations.runner.httpx.AsyncClient", FakeAsyncClient)

    class FakeKafkaAdmin:
        def __init__(self, **kwargs: object) -> None:
            self.started = False

        async def start(self) -> None:
            self.started = True

        async def create_topics(self, topics: list[object], validate_only: bool = False) -> None:
            return None

        async def close(self) -> None:
            return None

    class FakeNewTopic:
        def __init__(self, name: str, num_partitions: int, replication_factor: int) -> None:
            self.name = name

    class FakeDriver:
        async def __aenter__(self) -> FakeDriver:
            return self

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def run(self, query: str) -> None:
            return None

    class FakeNeo4jDriver:
        def session(self) -> FakeSession:
            return FakeSession()

        async def close(self) -> None:
            return None

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri: str, auth: tuple[str, str]) -> FakeNeo4jDriver:
            return FakeNeo4jDriver()

    class FakeClickHouseClient:
        def command(self, command: str) -> None:
            return None

        def close(self) -> None:
            return None

    fake_clickhouse = SimpleNamespace(get_client=lambda host: FakeClickHouseClient())

    class FakeS3Client:
        async def __aenter__(self) -> FakeS3Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def create_bucket(self, **kwargs: object) -> None:
            return None

    class FakeAioboto3Session:
        def client(self, *args: object, **kwargs: object) -> FakeS3Client:
            return FakeS3Client()

    monkeypatch.setitem(
        sys.modules,
        "aiokafka.admin",
        SimpleNamespace(AIOKafkaAdminClient=FakeKafkaAdmin, NewTopic=FakeNewTopic),
    )
    monkeypatch.setitem(sys.modules, "neo4j", SimpleNamespace(AsyncGraphDatabase=FakeGraphDatabase))
    monkeypatch.setitem(sys.modules, "clickhouse_connect", fake_clickhouse)
    monkeypatch.setitem(
        sys.modules, "aioboto3", SimpleNamespace(Session=lambda: FakeAioboto3Session())
    )

    runner = MigrationRunner()
    await runner.init_qdrant("http://qdrant:6333")
    await runner.init_neo4j("bolt://neo4j:7687", "secret")
    await runner.init_clickhouse("clickhouse")
    await runner.init_opensearch("http://opensearch:9200")
    await runner.init_kafka("kafka:9092")
    await runner.init_minio("http://minio:9000", "key", "secret")
    await runner.create_admin_user("http://localhost:8000", "admin@example.com", "Secret123!")


@pytest.mark.asyncio
async def test_run_all_delegates_to_all_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = MigrationRunner()
    calls: list[str] = []
    monkeypatch.setattr(runner, "run_alembic", lambda url: calls.append("alembic"))

    async def qdrant(url: str) -> None:
        calls.append("qdrant")

    async def neo4j(uri: str, password: str) -> None:
        calls.append("neo4j")

    async def clickhouse(url: str) -> None:
        calls.append("clickhouse")

    async def opensearch(url: str) -> None:
        calls.append("opensearch")

    async def kafka(bootstrap: str) -> None:
        calls.append("kafka")

    async def minio(endpoint: str, access_key: str, secret_key: str) -> None:
        calls.append("minio")

    async def admin(api_url: str, email: str, password: str) -> None:
        calls.append("admin")

    monkeypatch.setattr(runner, "init_qdrant", qdrant)
    monkeypatch.setattr(runner, "init_neo4j", neo4j)
    monkeypatch.setattr(runner, "init_clickhouse", clickhouse)
    monkeypatch.setattr(runner, "init_opensearch", opensearch)
    monkeypatch.setattr(runner, "init_kafka", kafka)
    monkeypatch.setattr(
        runner,
        "init_minio",
        minio,
    )
    monkeypatch.setattr(
        runner,
        "create_admin_user",
        admin,
    )

    config = InstallerConfig(deployment_mode=DeploymentMode.LOCAL)
    secrets = generate_secrets(config.secrets)
    await runner.run_all(config, secrets)

    assert calls == [
        "alembic",
        "qdrant",
        "neo4j",
        "clickhouse",
        "opensearch",
        "kafka",
        "minio",
        "admin",
    ]
