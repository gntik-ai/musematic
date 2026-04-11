from __future__ import annotations

from datetime import UTC, datetime
from platform.ws_hub.schemas import EventMessage
from platform.ws_hub.writer import ConnectionWriter
from types import SimpleNamespace

import pytest

from tests.ws_hub_support import FakeWebSocket, build_connection


@pytest.mark.asyncio
async def test_connection_writer_sends_events_dropped_before_event() -> None:
    websocket = FakeWebSocket(SimpleNamespace())
    conn = build_connection(websocket=websocket)
    conn.dropped_count = 3
    conn.send_queue.put_nowait(
        EventMessage(
            channel="execution",
            resource_id="resource-1",
            payload={"hello": "world"},
            gateway_received_at=datetime.now(UTC),
        )
    )
    conn.closed.set()

    await ConnectionWriter().run(conn)

    messages = websocket.decoded_messages()
    assert messages[0]["type"] == "events_dropped"
    assert messages[0]["count"] == 3
    assert messages[1]["type"] == "event"
    assert conn.dropped_count == 0


@pytest.mark.asyncio
async def test_connection_writer_stops_when_send_fails() -> None:
    websocket = FakeWebSocket(SimpleNamespace(), fail_send_text=True)
    conn = build_connection(websocket=websocket)
    conn.send_queue.put_nowait(
        EventMessage(
            channel="execution",
            resource_id="resource-1",
            payload={},
            gateway_received_at=datetime.now(UTC),
        )
    )
    conn.closed.set()

    await ConnectionWriter().run(conn)

    assert conn.closed.is_set() is True

