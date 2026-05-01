from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest


class E2EDatabaseProbe:
    def __init__(self, http_client: Any, dsn: str) -> None:
        self.http_client = http_client
        self.dsn = dsn
        self.connection: asyncpg.Connection | None = None

    async def __aenter__(self) -> E2EDatabaseProbe:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self.connection is not None:
            await self.connection.close()

    async def fetchval(self, query: str, *args: object) -> Any:
        response = await self.http_client.post(
            "/api/v1/_e2e/contract/db/fetchval",
            json={"query": query, "args": [str(item) for item in args]},
        )
        if response.status_code == 200:
            return response.json().get("value")
        if self.connection is None:
            self.connection = await asyncpg.connect(self.dsn)
        return await self.connection.fetchval(query, *args)


@pytest.fixture
async def db(db_dsn: str, http_client) -> AsyncIterator[E2EDatabaseProbe]:
    async with E2EDatabaseProbe(http_client, db_dsn) as probe:
        yield probe
