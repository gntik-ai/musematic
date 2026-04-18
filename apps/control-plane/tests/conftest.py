from __future__ import annotations

import importlib.util
import os
import socket
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings, Settings
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock
from urllib import request
from uuid import uuid4

import boto3
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.core.container import DockerContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from helpers import make_async_database_url, run_alembic
from tests.trust_support import FakeObjectStorage, FakeTrustRedisClient

REPO_ROOT = Path(__file__).resolve().parents[3]
NEO4J_INIT_CYPHER = REPO_ROOT / "deploy" / "neo4j" / "init.cypher"
CLICKHOUSE_INIT_DIR = REPO_ROOT / "deploy" / "clickhouse" / "init"
OPENSEARCH_INIT_SCRIPT = REPO_ROOT / "deploy" / "opensearch" / "init" / "init_opensearch.py"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that depend on containers or external services.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return

    skip_marker = pytest.mark.skip(reason="integration tests require --run-integration")
    for item in items:
        if "tests/integration/" in str(item.path):
            item.add_marker(pytest.mark.integration)
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16") as container:
        yield container


@pytest.fixture
def migrated_database_url(postgres_container: PostgresContainer) -> Iterator[str]:
    database_url = make_async_database_url(postgres_container.get_connection_url())
    run_alembic(database_url, "upgrade", "head")
    yield database_url
    run_alembic(database_url, "downgrade", "base")


@pytest.fixture
async def async_engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database_url, future=True)
    async with engine.begin() as connection:
        await connection.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(
    async_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7") as container:
        yield container


@pytest_asyncio.fixture
async def redis_client(request: pytest.FixtureRequest) -> AsyncIterator[AsyncRedisClient]:
    redis_url = os.environ.get("REDIS_URL")

    if redis_url is None:
        redis_container = request.getfixturevalue("redis_container")
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        redis_url = f"redis://{host}:{port}"

    client = AsyncRedisClient(nodes=[redis_url.removeprefix("redis://")])
    previous_mode = os.environ.get("REDIS_TEST_MODE")
    previous_url = os.environ.get("REDIS_URL")
    os.environ["REDIS_TEST_MODE"] = "standalone"
    os.environ["REDIS_URL"] = redis_url
    await client.initialize()
    assert client.client is not None
    await client.client.flushdb()
    yield client
    await client.close()
    if previous_mode is None:
        os.environ.pop("REDIS_TEST_MODE", None)
    else:
        os.environ["REDIS_TEST_MODE"] = previous_mode
    if previous_url is None:
        os.environ.pop("REDIS_URL", None)
    else:
        os.environ["REDIS_URL"] = previous_url


@pytest.fixture(scope="session")
def minio_server() -> Iterator[dict[str, object]]:
    if os.environ.get("MINIO_TEST_MODE") == "external":
        endpoint = os.environ["MINIO_TEST_ENDPOINT"]
        access_key = os.environ["MINIO_TEST_ACCESS_KEY"]
        secret_key = os.environ["MINIO_TEST_SECRET_KEY"]
        simulation_access_key = os.environ.get("MINIO_TEST_SIMULATION_ACCESS_KEY")
        simulation_secret_key = os.environ.get("MINIO_TEST_SIMULATION_SECRET_KEY")
        yield {
            "endpoint": endpoint,
            "access_key": access_key,
            "secret_key": secret_key,
            "simulation_access_key": simulation_access_key,
            "simulation_secret_key": simulation_secret_key,
            "use_ssl": os.environ.get("MINIO_TEST_USE_SSL", "").lower() == "true",
        }
        return

    container = (
        DockerContainer("minio/minio")
        .with_exposed_ports(9000, 9001)
        .with_env("MINIO_ROOT_USER", "minioadmin")
        .with_env("MINIO_ROOT_PASSWORD", "minioadmin123")
        .with_command('server /data --console-address ":9001"')
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(9000)
        endpoint = f"http://{host}:{port}"
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin123",
            region_name="us-east-1",
        )
        for _ in range(30):
            try:
                client.list_buckets()
                break
            except Exception:
                time.sleep(1)
        else:  # pragma: no cover - startup failure
            raise RuntimeError("MinIO test container did not become ready in time.")

        yield {
            "endpoint": endpoint,
            "access_key": "minioadmin",
            "secret_key": "minioadmin123",
            "simulation_access_key": None,
            "simulation_secret_key": None,
            "use_ssl": False,
        }


@pytest.fixture(scope="session")
def minio_admin_client(minio_server: dict[str, object]):
    client = boto3.client(
        "s3",
        endpoint_url=str(minio_server["endpoint"]),
        aws_access_key_id=str(minio_server["access_key"]),
        aws_secret_access_key=str(minio_server["secret_key"]),
        region_name="us-east-1",
    )
    for bucket in (
        "agent-packages",
        "execution-artifacts",
        "reasoning-traces",
        "sandbox-outputs",
        "evidence-bundles",
        "simulation-artifacts",
        "backups",
        "forensic-exports",
    ):
        existing = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
        if bucket not in existing:
            client.create_bucket(Bucket=bucket)
    client.put_bucket_versioning(
        Bucket="agent-packages",
        VersioningConfiguration={"Status": "Enabled"},
    )
    return client


@pytest.fixture
def object_storage_settings(
    minio_server: dict[str, object],
    minio_admin_client,
) -> Settings:
    return Settings(
        MINIO_ENDPOINT=str(minio_server["endpoint"]),
        MINIO_ACCESS_KEY=str(minio_server["access_key"]),
        MINIO_SECRET_KEY=str(minio_server["secret_key"]),
        MINIO_USE_SSL=bool(minio_server["use_ssl"]),
    )


@pytest_asyncio.fixture
async def object_storage_client(
    object_storage_settings: Settings,
) -> AsyncIterator[AsyncObjectStorageClient]:
    client = AsyncObjectStorageClient(object_storage_settings)
    yield client


@pytest.fixture(scope="session")
def auth_settings() -> PlatformSettings:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return PlatformSettings(
        AUTH_JWT_PRIVATE_KEY=private_pem,
        AUTH_JWT_PUBLIC_KEY=public_pem,
        AUTH_JWT_ALGORITHM="RS256",
        AUTH_MFA_ENCRYPTION_KEY=Fernet.generate_key().decode("utf-8"),
        AUTH_ACCESS_TOKEN_TTL=900,
        AUTH_REFRESH_TOKEN_TTL=604800,
        AUTH_LOCKOUT_THRESHOLD=5,
        AUTH_LOCKOUT_DURATION=900,
        AUTH_MFA_ENROLLMENT_TTL=600,
        AUTH_SESSION_TTL=604800,
        AUTH_PASSWORD_RESET_TTL=3600,
    )


@pytest.fixture(scope="session")
def qdrant_server() -> Iterator[dict[str, object]]:
    if os.environ.get("QDRANT_TEST_MODE") == "external":
        yield {
            "url": os.environ["QDRANT_TEST_URL"],
            "api_key": os.environ.get("QDRANT_TEST_API_KEY", ""),
            "grpc_port": int(os.environ.get("QDRANT_TEST_GRPC_PORT", "6334")),
        }
        return

    container = (
        DockerContainer("qdrant/qdrant:v1.16.3")
        .with_exposed_ports(6333, 6334)
        .with_env("QDRANT__SERVICE__API_KEY", "qdrant-test-key")
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6333)
        url = f"http://{host}:{port}"
        headers = {"Authorization": "api-key qdrant-test-key"}
        for _ in range(30):
            try:
                req = request.Request(f"{url}/healthz", headers=headers)
                with request.urlopen(req, timeout=5):
                    break
            except Exception:
                time.sleep(1)
        else:  # pragma: no cover - startup failure
            raise RuntimeError("Qdrant test container did not become ready in time.")

        yield {
            "url": url,
            "api_key": "qdrant-test-key",
            "grpc_port": int(container.get_exposed_port(6334)),
        }


@pytest.fixture
def qdrant_settings(qdrant_server: dict[str, object]) -> Settings:
    return Settings(
        QDRANT_URL=str(qdrant_server["url"]),
        QDRANT_API_KEY=str(qdrant_server["api_key"]),
        QDRANT_GRPC_PORT=int(qdrant_server["grpc_port"]),
        QDRANT_COLLECTION_DIMENSIONS=768,
    )


@pytest_asyncio.fixture
async def qdrant_client(qdrant_settings: Settings) -> AsyncIterator[AsyncQdrantClient]:
    client = AsyncQdrantClient(qdrant_settings)
    yield client
    await client.close()


@pytest_asyncio.fixture
async def qdrant_test_collection(
    qdrant_client: AsyncQdrantClient, qdrant_settings: Settings
) -> AsyncIterator[str]:
    qdrant_models = __import__("qdrant_client.models", fromlist=["models"])
    collection_name = f"test-{uuid4().hex}"
    await qdrant_client.create_collection_if_not_exists(
        collection=collection_name,
        vectors_config=qdrant_models.VectorParams(
            size=qdrant_settings.QDRANT_COLLECTION_DIMENSIONS,
            distance=qdrant_models.Distance.COSINE,
        ),
        hnsw_config=qdrant_models.HnswConfigDiff(m=16, ef_construct=128, full_scan_threshold=10000),
        replication_factor=1,
    )
    yield collection_name
    try:
        await qdrant_client._client.delete_collection(collection_name=collection_name)
    except Exception:
        return


def _neo4j_init_statements() -> list[str]:
    contents = NEO4J_INIT_CYPHER.read_text(encoding="utf-8")
    filtered = "\n".join(
        line for line in contents.splitlines() if not line.lstrip().startswith("//")
    )
    return [statement.strip() for statement in filtered.split(";") if statement.strip()]


async def _apply_neo4j_init(client: AsyncNeo4jClient) -> None:
    for statement in _neo4j_init_statements():
        await client.run_query(statement)


@pytest.fixture(scope="session")
def neo4j_server() -> Iterator[dict[str, object]]:
    if os.environ.get("NEO4J_TEST_MODE") == "external":
        yield {
            "url": os.environ["NEO4J_TEST_URL"],
            "password": os.environ["NEO4J_TEST_PASSWORD"],
            "http_url": os.environ.get("NEO4J_TEST_HTTP_URL", ""),
        }
        return

    container = (
        DockerContainer("neo4j:5.21.2-community")
        .with_exposed_ports(7474, 7687)
        .with_env("NEO4J_AUTH", "neo4j/test-password")
        .with_env("NEO4J_PLUGINS", '["apoc"]')
        .with_env("NEO4J_dbms_security_procedures_unrestricted", "apoc.*")
        .with_env("NEO4J_dbms_security_procedures_allowlist", "apoc.*")
    )
    with container:
        host = container.get_container_host_ip()
        bolt_port = int(container.get_exposed_port(7687))
        http_port = int(container.get_exposed_port(7474))
        for _ in range(60):
            try:
                with socket.create_connection((host, bolt_port), timeout=5):
                    break
            except OSError:
                time.sleep(2)
        else:  # pragma: no cover - startup failure
            raise RuntimeError("Neo4j test container did not become ready in time.")

        yield {
            "url": f"bolt://neo4j:test-password@{host}:{bolt_port}",
            "password": "test-password",
            "http_url": f"http://{host}:{http_port}",
        }


@pytest.fixture
def neo4j_settings(neo4j_server: dict[str, object]) -> Settings:
    return Settings(
        NEO4J_URL=str(neo4j_server["url"]),
        NEO4J_MAX_CONNECTION_POOL_SIZE=10,
        GRAPH_MODE="neo4j",
    )


@pytest_asyncio.fixture
async def neo4j_client(neo4j_settings: Settings) -> AsyncIterator[AsyncNeo4jClient]:
    pytest.importorskip("neo4j")
    client = AsyncNeo4jClient(neo4j_settings)
    await client.run_query("MATCH (n) DETACH DELETE n")
    await _apply_neo4j_init(client)
    yield client
    await client.run_query("MATCH (n) DETACH DELETE n")
    await client.close()


def _clickhouse_init_statements() -> list[str]:
    statements: list[str] = []
    for sql_file in sorted(CLICKHOUSE_INIT_DIR.glob("*.sql")):
        contents = sql_file.read_text(encoding="utf-8")
        for statement in contents.split(";"):
            stripped = statement.strip()
            if stripped:
                statements.append(stripped)
    return statements


async def _apply_clickhouse_init(client: AsyncClickHouseClient) -> None:
    for statement in _clickhouse_init_statements():
        await client.execute_command(statement)


@pytest.fixture(scope="session")
def clickhouse_server() -> Iterator[dict[str, object]]:
    if os.environ.get("CLICKHOUSE_TEST_MODE") == "external":
        yield {
            "url": os.environ["CLICKHOUSE_TEST_URL"],
            "user": os.environ.get("CLICKHOUSE_TEST_USER", "default"),
            "password": os.environ.get("CLICKHOUSE_TEST_PASSWORD", ""),
        }
        return

    container = (
        DockerContainer("clickhouse/clickhouse-server:24.3")
        .with_exposed_ports(8123, 9000)
        .with_env("CLICKHOUSE_DB", "default")
        .with_env("CLICKHOUSE_USER", "default")
        .with_env("CLICKHOUSE_PASSWORD", "test-password")
        .with_env("CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT", "1")
    )
    with container:
        host = container.get_container_host_ip()
        http_port = int(container.get_exposed_port(8123))
        url = f"http://{host}:{http_port}"
        for _ in range(60):
            try:
                with request.urlopen(f"{url}/ping", timeout=5) as response:
                    if response.read().decode().strip() == "Ok.":
                        break
            except Exception:
                time.sleep(2)
        else:  # pragma: no cover - startup failure
            raise RuntimeError("ClickHouse test container did not become ready in time.")

        yield {
            "url": url,
            "user": "default",
            "password": "test-password",
        }


@pytest.fixture
def clickhouse_settings(clickhouse_server: dict[str, object]) -> Settings:
    return Settings(
        CLICKHOUSE_URL=str(clickhouse_server["url"]),
        CLICKHOUSE_USER=str(clickhouse_server["user"]),
        CLICKHOUSE_PASSWORD=str(clickhouse_server["password"]),
        CLICKHOUSE_DATABASE="default",
        CLICKHOUSE_INSERT_BATCH_SIZE=1000,
        CLICKHOUSE_INSERT_FLUSH_INTERVAL=5.0,
    )


@pytest_asyncio.fixture
async def clickhouse_client(clickhouse_settings: Settings) -> AsyncIterator[AsyncClickHouseClient]:
    pytest.importorskip("clickhouse_connect")
    client = AsyncClickHouseClient(clickhouse_settings)
    await _apply_clickhouse_init(client)
    for table in (
        "analytics_usage_hourly_mv",
        "analytics_usage_hourly_v2",
        "analytics_usage_monthly",
        "analytics_usage_daily",
        "analytics_quality_events",
        "analytics_usage_events",
        "usage_hourly_mv",
        "usage_hourly_v2",
        "usage_hourly",
        "usage_events",
        "behavioral_drift",
        "fleet_performance",
        "self_correction_analytics",
    ):
        await client.execute_command(f"TRUNCATE TABLE IF EXISTS {table}")
    yield client
    for table in (
        "analytics_usage_hourly_mv",
        "analytics_usage_hourly_v2",
        "analytics_usage_monthly",
        "analytics_usage_daily",
        "analytics_quality_events",
        "analytics_usage_events",
        "usage_hourly_mv",
        "usage_hourly_v2",
        "usage_hourly",
        "usage_events",
        "behavioral_drift",
        "fleet_performance",
        "self_correction_analytics",
    ):
        await client.execute_command(f"TRUNCATE TABLE IF EXISTS {table}")
    await client.close()


def _load_opensearch_init_module():
    spec = importlib.util.spec_from_file_location(
        "musematic_opensearch_init", OPENSEARCH_INIT_SCRIPT
    )
    if spec is None or spec.loader is None:  # pragma: no cover - broken workspace
        raise RuntimeError(f"Unable to load OpenSearch init script from {OPENSEARCH_INIT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def opensearch_init_module():
    return _load_opensearch_init_module()


async def _reset_opensearch(async_client) -> None:
    for index_pattern in (
        "marketplace-agents-*",
        "audit-events-*",
        "connector-payloads-*",
        "audit-events-ism-test*",
        "snapshot-test-*",
    ):
        try:
            await async_client.indices.delete(index=index_pattern, ignore_unavailable=True)
        except Exception:
            pass
    for template_name in ("marketplace-agents", "audit-events", "connector-payloads"):
        try:
            await async_client.indices.delete_index_template(name=template_name)
        except Exception:
            pass
    for path in (
        "/_plugins/_ism/policies/audit-events-policy",
        "/_plugins/_ism/policies/connector-payloads-policy",
        "/_plugins/_ism/policies/test-short-retention",
        "/_plugins/_sm/policies/daily-snapshot",
    ):
        try:
            await async_client.transport.perform_request(method="DELETE", url=path)
        except Exception:
            pass
    try:
        await async_client.snapshot.delete_repository(repository="opensearch-backups")
    except Exception:
        pass


async def _apply_opensearch_init(
    client: AsyncOpenSearchClient,
    init_module,
    opensearch_server: dict[str, object],
) -> None:
    repository = init_module.SnapshotRepositorySettings(
        name="opensearch-backups",
        type=str(opensearch_server.get("snapshot_type", "fs")),
        bucket="backups",
        base_path="backups/opensearch",
        endpoint=str(opensearch_server.get("snapshot_endpoint", "http://musematic-minio:9000")),
        location=(
            str(opensearch_server["snapshot_location"])
            if opensearch_server.get("snapshot_location") is not None
            else None
        ),
    )
    await init_module.create_ism_policies(client._client)
    await init_module.create_index_templates(client._client)
    await init_module.setup_snapshot_management(client._client, repository_settings=repository)


@pytest.fixture(scope="session")
def opensearch_server() -> Iterator[dict[str, object]]:
    if os.environ.get("OPENSEARCH_TEST_MODE") == "external":
        yield {
            "url": os.environ["OPENSEARCH_TEST_URL"],
            "username": os.environ.get("OPENSEARCH_TEST_USERNAME", ""),
            "password": os.environ.get("OPENSEARCH_TEST_PASSWORD", ""),
            "snapshot_type": os.environ.get("OPENSEARCH_TEST_SNAPSHOT_TYPE", "fs"),
            "snapshot_location": os.environ.get("OPENSEARCH_TEST_SNAPSHOT_LOCATION"),
            "snapshot_endpoint": os.environ.get(
                "OPENSEARCH_TEST_SNAPSHOT_ENDPOINT", "http://musematic-minio:9000"
            ),
        }
        return

    with TemporaryDirectory() as snapshot_dir:
        container = (
            DockerContainer("opensearchproject/opensearch:2.18.0")
            .with_exposed_ports(9200)
            .with_env("discovery.type", "single-node")
            .with_env("plugins.security.disabled", "true")
            .with_env("DISABLE_SECURITY_PLUGIN", "true")
            .with_env("DISABLE_INSTALL_DEMO_CONFIG", "true")
            .with_env("OPENSEARCH_JAVA_OPTS", "-Xms512m -Xmx512m")
            .with_env("path.repo", "/var/backups/opensearch")
            .with_volume_mapping(snapshot_dir, "/var/backups/opensearch")
        )
        with container:
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(9200))
            url = f"http://{host}:{port}"
            for _ in range(60):
                try:
                    with request.urlopen(f"{url}/_cluster/health", timeout=5):
                        break
                except Exception:
                    time.sleep(2)
            else:  # pragma: no cover - startup failure
                raise RuntimeError("OpenSearch test container did not become ready in time.")

            yield {
                "url": url,
                "username": "",
                "password": "",
                "snapshot_type": "fs",
                "snapshot_location": "/var/backups/opensearch",
            }


@pytest.fixture
def opensearch_settings(opensearch_server: dict[str, object]) -> Settings:
    return Settings(
        OPENSEARCH_HOSTS=str(opensearch_server["url"]),
        OPENSEARCH_USERNAME=str(opensearch_server["username"]),
        OPENSEARCH_PASSWORD=str(opensearch_server["password"]),
        OPENSEARCH_USE_SSL=False,
        OPENSEARCH_VERIFY_CERTS=False,
        OPENSEARCH_TIMEOUT=30,
    )


@pytest_asyncio.fixture
async def opensearch_client(opensearch_settings: Settings) -> AsyncIterator[AsyncOpenSearchClient]:
    pytest.importorskip("opensearchpy")
    client = AsyncOpenSearchClient.from_settings(opensearch_settings)
    await client.connect()
    assert client._client is not None
    await _reset_opensearch(client._client)
    yield client
    await _reset_opensearch(client._client)
    await client.close()


@pytest_asyncio.fixture
async def initialized_opensearch_client(
    opensearch_client: AsyncOpenSearchClient,
    opensearch_init_module,
    opensearch_server: dict[str, object],
) -> AsyncIterator[AsyncOpenSearchClient]:
    await _apply_opensearch_init(opensearch_client, opensearch_init_module, opensearch_server)
    yield opensearch_client


@pytest.fixture
def mock_policy_governance_engine() -> AsyncMock:
    engine = AsyncMock()
    engine.evaluate_tool_access.return_value = True
    engine.evaluate_memory_write.return_value = True
    engine.check_privacy_compliance.return_value = {
        "compliant": True,
        "blocked": False,
        "violations": [],
    }
    return engine


@pytest.fixture
def mock_runtime_controller_client() -> AsyncMock:
    client = AsyncMock()
    client.stop_runtime.return_value = None
    client.pause_workflow.return_value = None
    return client


@pytest.fixture
def mock_simulation_controller_client() -> AsyncMock:
    client = AsyncMock()
    client.create_simulation.return_value = {"simulation_id": "sim-fixture"}
    return client


@pytest.fixture
def mock_minio_trust() -> FakeObjectStorage:
    return FakeObjectStorage()


@pytest.fixture
def trust_redis_test_client() -> FakeTrustRedisClient:
    return FakeTrustRedisClient()
