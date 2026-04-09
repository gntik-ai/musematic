from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
import os

import pytest
import pytest_asyncio
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
