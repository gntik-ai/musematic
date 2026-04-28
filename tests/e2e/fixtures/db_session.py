from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest


@pytest.fixture(scope="session")
async def db(db_dsn: str) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(db_dsn)
    try:
        yield connection
    finally:
        await connection.close()
