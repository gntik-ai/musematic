from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.constants import ComponentCategory
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.diagnostics.checks.clickhouse import ClickHouseCheck
from platform_cli.diagnostics.checks.grpc_services import GrpcServiceCheck
from platform_cli.diagnostics.checks.kafka import KafkaCheck
from platform_cli.diagnostics.checks.minio import MinIOCheck
from platform_cli.diagnostics.checks.model_providers import ModelProviderCheck
from platform_cli.diagnostics.checks.neo4j import Neo4jCheck
from platform_cli.diagnostics.checks.opensearch import OpenSearchCheck
from platform_cli.diagnostics.checks.postgresql import PostgreSQLCheck
from platform_cli.diagnostics.checks.qdrant import QdrantCheck
from platform_cli.diagnostics.checks.redis import RedisCheck
from platform_cli.models import AutoFixResult, CheckStatus, DiagnosticCheck
from platform_cli.secrets.generator import generate_secrets


class FakeResponse:
    def __init__(
        self, status_code: int = 200, json_payload: dict[str, object] | None = None
    ) -> None:
        self.status_code = status_code
        self._json_payload = json_payload or {"status": "green"}
        self.text = "ok"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self) -> dict[str, object]:
        return self._json_payload


class FakeAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.payload = kwargs.pop("payload", None)

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        if "_cluster/health" in url:
            return FakeResponse(json_payload={"status": "yellow"})
        return FakeResponse()

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    async def put(self, url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()


@pytest.mark.asyncio
async def test_core_diagnostic_checks_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeConnection:
        async def execute(self, query: str) -> None:
            return None

        async def close(self) -> None:
            return None

    async def connect(dsn: str) -> FakeConnection:
        return FakeConnection()

    class FakeRedisClient:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    class FakeRedisModule:
        @staticmethod
        def from_url(url: str, decode_responses: bool = True) -> FakeRedisClient:
            return FakeRedisClient()

    class FakeKafkaAdmin:
        async def start(self) -> None:
            return None

        async def list_topics(self) -> list[str]:
            return ["topic"]

        async def close(self) -> None:
            return None

    class FakeGraphSession:
        async def __aenter__(self) -> FakeGraphSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def run(self, query: str) -> None:
            return None

    class FakeGraphDriver:
        def session(self) -> FakeGraphSession:
            return FakeGraphSession()

        async def close(self) -> None:
            return None

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri: str, auth: tuple[str, str]) -> FakeGraphDriver:
            return FakeGraphDriver()

    class FakeClickHouseClient:
        def query(self, query: str) -> None:
            return None

        def close(self) -> None:
            return None

    class FakeS3Client:
        async def __aenter__(self) -> FakeS3Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def head_bucket(self, **kwargs: object) -> None:
            return None

    class FakeAiobotoSession:
        def client(self, *args: object, **kwargs: object) -> FakeS3Client:
            return FakeS3Client()

    monkeypatch.setitem(sys.modules, "asyncpg", SimpleNamespace(connect=connect))
    monkeypatch.setitem(
        sys.modules,
        "redis.asyncio",
        SimpleNamespace(Redis=SimpleNamespace(from_url=FakeRedisModule.from_url)),
    )
    monkeypatch.setitem(
        sys.modules,
        "aiokafka.admin",
        SimpleNamespace(AIOKafkaAdminClient=lambda **kwargs: FakeKafkaAdmin()),
    )
    monkeypatch.setitem(sys.modules, "neo4j", SimpleNamespace(AsyncGraphDatabase=FakeGraphDatabase))
    monkeypatch.setitem(
        sys.modules,
        "clickhouse_connect",
        SimpleNamespace(get_client=lambda host: FakeClickHouseClient()),
    )
    monkeypatch.setitem(
        sys.modules, "aioboto3", SimpleNamespace(Session=lambda: FakeAiobotoSession())
    )
    monkeypatch.setattr("platform_cli.diagnostics.checks.qdrant.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "platform_cli.diagnostics.checks.opensearch.httpx.AsyncClient", FakeAsyncClient
    )
    monkeypatch.setattr(
        "platform_cli.diagnostics.checks.model_providers.httpx.AsyncClient", FakeAsyncClient
    )

    secrets = generate_secrets(InstallerConfig().secrets)

    checks = [
        PostgreSQLCheck("postgresql://db"),
        RedisCheck("redis://localhost"),
        KafkaCheck("kafka:9092"),
        QdrantCheck("http://qdrant"),
        Neo4jCheck("bolt://neo4j", secrets.neo4j_password),
        ClickHouseCheck("clickhouse"),
        OpenSearchCheck("http://opensearch"),
        MinIOCheck("http://minio", secrets.minio_access_key, secrets.minio_secret_key),
        ModelProviderCheck("https://models.example.com/health"),
    ]

    results = [await check.run() for check in checks]

    assert all(item.status in {CheckStatus.HEALTHY, CheckStatus.DEGRADED} for item in results)
    assert results[6].status == CheckStatus.DEGRADED


@pytest.mark.asyncio
async def test_grpc_check_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeChannel:
        async def __aenter__(self) -> FakeChannel:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeHealthStub:
        def __init__(self, channel: FakeChannel) -> None:
            return None

        async def Check(self, request: object) -> object:  # noqa: N802
            return SimpleNamespace(status=1)

    health_pb2 = ModuleType("health_pb2")
    health_pb2.HealthCheckRequest = lambda: object()
    health_pb2.HealthCheckResponse = SimpleNamespace(SERVING=1)
    health_pb2_grpc = ModuleType("health_pb2_grpc")
    health_pb2_grpc.HealthStub = FakeHealthStub

    monkeypatch.setitem(
        sys.modules,
        "grpc",
        SimpleNamespace(aio=SimpleNamespace(insecure_channel=lambda addr: FakeChannel())),
    )
    monkeypatch.setitem(sys.modules, "grpc_health", ModuleType("grpc_health"))
    monkeypatch.setitem(sys.modules, "grpc_health.v1", ModuleType("grpc_health.v1"))
    monkeypatch.setitem(sys.modules, "grpc_health.v1.health_pb2", health_pb2)
    monkeypatch.setitem(sys.modules, "grpc_health.v1.health_pb2_grpc", health_pb2_grpc)

    result = await GrpcServiceCheck("localhost", 50051, "runtime-controller", "Runtime").run()

    assert result.status == CheckStatus.HEALTHY
    assert result.category == ComponentCategory.SATELLITE_SERVICE


@pytest.mark.asyncio
async def test_diagnostic_runner_aggregates_and_auto_fixes(monkeypatch: pytest.MonkeyPatch) -> None:
    config = InstallerConfig(
        deployment_mode=DeploymentMode.KUBERNETES,
        model_provider_urls=["https://models.example.com/health"],
    )
    runner = DiagnosticRunner(config)

    async def healthy() -> DiagnosticCheck:
        return DiagnosticCheck(
            component="postgresql",
            display_name="PostgreSQL",
            category=ComponentCategory.DATA_STORE,
            status=CheckStatus.HEALTHY,
        )

    async def unhealthy() -> DiagnosticCheck:
        return DiagnosticCheck(
            component="control-plane",
            display_name="Control Plane",
            category=ComponentCategory.CONTROL_PLANE,
            status=CheckStatus.UNHEALTHY,
            error="boom",
        )

    fake_checks = [
        SimpleNamespace(name="postgresql", run=healthy),
        SimpleNamespace(name="control-plane", run=unhealthy),
    ]
    monkeypatch.setattr(runner, "build_checks", lambda: fake_checks)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout="restarted"),
    )

    report = await runner.run(timeout_per_check=1)
    fixes = await runner.auto_fix(report)

    assert report.overall_status == CheckStatus.UNHEALTHY
    assert fixes == [
        AutoFixResult(
            component="control-plane",
            action="rollout_restart",
            success=True,
            message="restarted",
        )
    ]


def test_auto_detect_mode_prefers_local_pid(tmp_path: Path) -> None:
    config = InstallerConfig(data_dir=tmp_path)
    (tmp_path / "platform.pid").write_text("123", encoding="utf-8")

    assert DiagnosticRunner.auto_detect_mode(config) == DeploymentMode.LOCAL
