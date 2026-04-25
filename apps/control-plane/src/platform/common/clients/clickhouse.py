from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from importlib import import_module
from platform.common.config import Settings
from platform.common.config import settings as default_settings
from platform.common.exceptions import (
    ClickHouseConnectionError,
    ClickHouseQueryError,
)
from typing import Any, cast
from urllib.parse import urlparse


class AsyncClickHouseClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or default_settings
        if self._settings.CLICKHOUSE_URL is None:
            raise ClickHouseConnectionError("CLICKHOUSE_URL not configured")
        self._client: Any | None = None
        self._client_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> AsyncClickHouseClient:
        return cls(settings)

    async def connect(self) -> None:
        await self._get_client()

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        sql = self._apply_tombstone_filter(sql)
        client = await self._get_client()
        try:
            result = await client.query(sql, parameters=params or {})
        except Exception as exc:
            raise self._translate_query_error(exc) from exc
        return [
            dict(zip(result.column_names, row, strict=False))
            for row in cast(list[tuple[Any, ...]], result.result_rows)
        ]

    def _apply_tombstone_filter(self, sql: str) -> str:
        tables = set(getattr(self._settings.privacy_compliance, "clickhouse_pii_tables", []))
        if not tables or "is_deleted" in sql.lower():
            return sql
        lowered = sql.lower()
        if not lowered.lstrip().startswith("select"):
            return sql
        table_matched = any(
            re.search(rf"\bfrom\s+{re.escape(table.lower())}\b", lowered)
            for table in tables
        )
        if not table_matched:
            return sql
        if " where " in lowered:
            return f"{sql} AND NOT is_deleted"
        return f"{sql} WHERE NOT is_deleted"

    async def execute_command(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        client = await self._get_client()
        try:
            await client.command(sql, parameters=params or {})
        except Exception as exc:
            raise self._translate_query_error(exc) from exc

    async def insert_batch(
        self,
        table: str,
        data: list[dict[str, Any]],
        column_names: list[str],
    ) -> None:
        if not data:
            return
        rows = [[row[column] for column in column_names] for row in data]
        client = await self._get_client()
        try:
            await client.insert(table, rows, column_names=column_names)
        except Exception as exc:
            raise self._translate_query_error(exc) from exc

    async def insert(self, table: str, rows: list[dict[str, Any]], column_names: list[str]) -> None:
        await self.insert_batch(table, rows, column_names)

    async def health_check(self) -> bool:
        try:
            rows = await self.execute_query("SELECT 1 AS ok")
            return bool(rows and rows[0]["ok"] == 1)
        except Exception:
            return False

    async def close(self) -> None:
        if self._client is None:
            return
        close = getattr(self._client, "close", None)
        if close is None:
            self._client = None
            return
        result = close()
        if asyncio.iscoroutine(result):
            await result
        self._client = None

    async def _get_client(self) -> Any:
        if self._current_client() is not None:
            return self._client

        async with self._client_lock:
            if self._current_client() is not None:
                return self._client

            parsed = urlparse(self._settings.CLICKHOUSE_URL or "")
            if not parsed.scheme or not parsed.hostname:
                raise ClickHouseConnectionError(
                    f"Invalid CLICKHOUSE_URL: {self._settings.CLICKHOUSE_URL!r}"
                )

            clickhouse_connect = import_module("clickhouse_connect")
            get_async_client = clickhouse_connect.get_async_client
            try:
                self._client = await get_async_client(
                    host=parsed.hostname,
                    port=parsed.port or 8123,
                    interface=parsed.scheme,
                    username=self._settings.CLICKHOUSE_USER,
                    password=self._settings.CLICKHOUSE_PASSWORD,
                    database=self._settings.CLICKHOUSE_DATABASE,
                )
            except Exception as exc:
                raise ClickHouseConnectionError(str(exc)) from exc
            return self._client

    def _translate_query_error(self, exc: Exception) -> ClickHouseQueryError:
        return ClickHouseQueryError(str(exc))

    def _current_client(self) -> Any | None:
        return self._client


@dataclass
class BatchBuffer:
    client: AsyncClickHouseClient
    table: str
    column_names: list[str]
    max_size: int = 1000
    flush_interval: float = 5.0

    def __post_init__(self) -> None:
        self._buffer: list[dict[str, Any]] = []
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def add(self, row: dict[str, Any]) -> None:
        async with self._lock:
            self._buffer.append(row)
            should_flush = len(self._buffer) >= self.max_size
        if should_flush:
            await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            rows = list(self._buffer)
            self._buffer.clear()
        await self.client.insert_batch(self.table, rows, self.column_names)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.flush()

    async def _flush_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
        except asyncio.CancelledError:
            raise
