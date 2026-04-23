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

    assert websocket.sent_text == []


@pytest.mark.asyncio
async def test_connection_heartbeat_keeps_passive_subscription_alive_within_grace_window() -> None:
    websocket = FakeWebSocket(SimpleNamespace())
    conn = build_connection(websocket=websocket)
    conn.last_pong_at = datetime.now(UTC) - timedelta(seconds=5)

    async def send_and_stop(payload: str) -> None:
        websocket.sent_text.append(payload)
        conn.closed.set()

    websocket.send_text = send_and_stop

    await ConnectionHeartbeat(interval_seconds=0, timeout_seconds=10).run(conn)

    messages = websocket.decoded_messages()
    assert len(messages) == 1
    assert messages[0]["type"] == "heartbeat"
    assert "server_time" in messages[0]
    assert websocket.close_calls == []
