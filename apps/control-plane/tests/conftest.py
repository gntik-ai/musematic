from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
import os
import time

import boto3
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.core.container import DockerContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from helpers import make_async_database_url, run_alembic
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import Settings
from platform.common.clients.redis import AsyncRedisClient


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
async def session_factory(async_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


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
async def object_storage_client(object_storage_settings: Settings) -> AsyncIterator[AsyncObjectStorageClient]:
    client = AsyncObjectStorageClient(object_storage_settings)
    yield client
