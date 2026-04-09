from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from tests.helpers import make_async_database_url, run_alembic


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
