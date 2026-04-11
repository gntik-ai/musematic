from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.ws_hub.heartbeat import ConnectionHeartbeat
from types import SimpleNamespace

import pytest

from tests.ws_hub_support import FakeWebSocket, build_connection


@pytest.mark.asyncio
async def test_connection_heartbeat_closes_timed_out_connection() -> None:
    websocket = FakeWebSocket(SimpleNamespace())
    conn = build_connection(websocket=websocket)
    conn.last_pong_at = datetime.now(UTC) - timedelta(seconds=5)

    await ConnectionHeartbeat(interval_seconds=0, timeout_seconds=1).run(conn)

    assert websocket.close_calls[-1][0] == 1001
    assert conn.closed.is_set() is True


@pytest.mark.asyncio
async def test_connection_heartbeat_sends_ping_for_live_connection() -> None:
    websocket = FakeWebSocket(SimpleNamespace())
    conn = build_connection(websocket=websocket)
    conn.last_pong_at = datetime.now(UTC)
    conn.closed.set()

    await ConnectionHeartbeat(interval_seconds=0, timeout_seconds=10).run(conn)

    assert websocket.sent_bytes == []
