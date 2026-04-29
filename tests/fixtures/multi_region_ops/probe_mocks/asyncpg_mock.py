from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from types import ModuleType
from typing import Any


@dataclass
class AsyncpgReplicationMock:
    lag_seconds: int = 0
    connected: bool = True

    async def connect(self, dsn: str) -> "AsyncpgReplicationConnection":
        return AsyncpgReplicationConnection(dsn=dsn, state=self)


@dataclass
class AsyncpgReplicationConnection:
    dsn: str
    state: AsyncpgReplicationMock

    async def fetch(self, query: str) -> list[dict[str, Any]]:
        assert "pg_stat_replication" in query
        if not self.state.connected:
            return []
        return [{"state": "streaming", "replay_lag": timedelta(seconds=self.state.lag_seconds)}]

    async def close(self) -> None:
        return None


def install_asyncpg_replication_mock(monkeypatch: Any, state: AsyncpgReplicationMock) -> None:
    module = ModuleType("asyncpg")
    module.connect = state.connect  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "asyncpg", module)
