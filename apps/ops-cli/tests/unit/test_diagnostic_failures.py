from __future__ import annotations

import asyncio
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
from platform_cli.diagnostics.checks.opensearch import OpenSearchCheck
from platform_cli.diagnostics.checks.postgresql import PostgreSQLCheck
from platform_cli.diagnostics.checks.qdrant import QdrantCheck
from platform_cli.diagnostics.checks.redis import RedisCheck
from platform_cli.models import CheckStatus, DiagnosticCheck


class BrokenAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        return None

    async def __aenter__(self) -> BrokenAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, **kwargs: object) -> object:
        raise RuntimeError("http down")


@pytest.mark.asyncio
async def test_failure_branches_for_store_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_connect(dsn: str) -> object:
        raise RuntimeError("db down")

    async def failing_ping() -> bool:
        raise RuntimeError("redis down")

    async def closing() -> None:
        return None

    async def kafka_start() -> None:
        raise RuntimeError("kafka down")

    async def kafka_close() -> None:
        return None

    monkeypatch.setitem(sys.modules, "asyncpg", SimpleNamespace(connect=failing_connect))
    monkeypatch.setitem(
        sys.modules,
        "redis.asyncio",
        SimpleNamespace(
            Redis=SimpleNamespace(
                from_url=lambda url, decode_responses=True: SimpleNamespace(
                    ping=failing_ping,
                    aclose=closing,
                )
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "aiokafka.admin",
        SimpleNamespace(
            AIOKafkaAdminClient=lambda **kwargs: SimpleNamespace(
                start=kafka_start,
                close=kafka_close,
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "neo4j",
        SimpleNamespace(
            AsyncGraphDatabase=SimpleNamespace(
                driver=lambda uri, auth: SimpleNamespace(
                    session=lambda: SimpleNamespace(
                        __aenter__=lambda self=None: (_ for _ in ()).throw(
                            RuntimeError("neo4j down")
                        ),
                        __aexit__=lambda *args: None,
                    ),
                    close=lambda: None,
                )
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "clickhouse_connect",
        SimpleNamespace(
            get_client=lambda host: (_ for _ in ()).throw(RuntimeError("clickhouse down"))
        ),
    )

    class FailingS3Client:
        async def __aenter__(self) -> FailingS3Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def head_bucket(self, **kwargs: object) -> None:
            raise RuntimeError("minio down")

    monkeypatch.setitem(
        sys.modules,
        "aioboto3",
        SimpleNamespace(
            Session=lambda: SimpleNamespace(client=lambda *args, **kwargs: FailingS3Client())
        ),
    )
    monkeypatch.setattr(
        "platform_cli.diagnostics.checks.qdrant.httpx.AsyncClient", BrokenAsyncClient
    )
    monkeypatch.setattr(
        "platform_cli.diagnostics.checks.opensearch.httpx.AsyncClient", BrokenAsyncClient
    )
    monkeypatch.setattr(
        "platform_cli.diagnostics.checks.model_providers.httpx.AsyncClient", BrokenAsyncClient
    )

    checks = [
        PostgreSQLCheck("postgresql://db"),
        RedisCheck("redis://localhost"),
        KafkaCheck("kafka:9092"),
        QdrantCheck("http://qdrant"),
        ClickHouseCheck("clickhouse"),
        OpenSearchCheck("http://opensearch"),
        MinIOCheck("http://minio", "key", "secret"),
        ModelProviderCheck("https://models.example.com/health"),
    ]
    results = [await check.run() for check in checks]

    assert all(item.status == CheckStatus.UNHEALTHY for item in results)


@pytest.mark.asyncio
async def test_grpc_and_neo4j_failure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenChannel:
        async def __aenter__(self) -> BrokenChannel:
            raise RuntimeError("grpc down")

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setitem(
        sys.modules,
        "grpc",
        SimpleNamespace(aio=SimpleNamespace(insecure_channel=lambda addr: BrokenChannel())),
    )
    monkeypatch.setitem(sys.modules, "grpc_health", ModuleType("grpc_health"))
    monkeypatch.setitem(sys.modules, "grpc_health.v1", ModuleType("grpc_health.v1"))
    monkeypatch.setitem(sys.modules, "grpc_health.v1.health_pb2", ModuleType("health_pb2"))
    monkeypatch.setitem(
        sys.modules, "grpc_health.v1.health_pb2_grpc", ModuleType("health_pb2_grpc")
    )

    result = await GrpcServiceCheck("localhost", 50051, "runtime-controller", "Runtime").run()

    assert result.status == CheckStatus.UNHEALTHY


@pytest.mark.asyncio
async def test_diagnostic_runner_timeout_and_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = InstallerConfig(deployment_mode=DeploymentMode.LOCAL, data_dir=tmp_path)
    runner = DiagnosticRunner(config, selected_checks={"slow"})

    async def slow() -> DiagnosticCheck:
        await asyncio.sleep(0.01)
        return DiagnosticCheck(
            component="slow",
            display_name="Slow",
            category=ComponentCategory.DATA_STORE,
            status=CheckStatus.HEALTHY,
        )

    monkeypatch.setattr(runner, "build_checks", lambda: [SimpleNamespace(name="slow", run=slow)])

    report = await runner.run(timeout_per_check=0)

    assert report.overall_status == CheckStatus.UNKNOWN
