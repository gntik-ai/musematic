from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from helpers import make_async_database_url, run_alembic
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


@pytest.fixture
async def redis_client(redis_container: RedisContainer) -> AsyncIterator[AsyncRedisClient]:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = AsyncRedisClient(nodes=[f"{host}:{port}"])
    os.environ["REDIS_TEST_MODE"] = "standalone"
    os.environ["REDIS_URL"] = f"redis://{host}:{port}"
    await client.initialize()
    assert client.client is not None
    await client.client.flushdb()
    yield client
    await client.close()
    os.environ.pop("REDIS_TEST_MODE", None)
    os.environ.pop("REDIS_URL", None)
