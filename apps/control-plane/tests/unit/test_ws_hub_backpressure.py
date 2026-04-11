from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.ws_hub.connection import ConnectionRegistry
from platform.ws_hub.fanout import KafkaFanout
from platform.ws_hub.schemas import EventMessage
from platform.ws_hub.subscription import SubscriptionRegistry
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.ws_hub_support import FakeWebSocket, StaticWorkspacesService, build_connection


@pytest.mark.asyncio
async def test_enqueue_drops_oldest_event_when_queue_is_full() -> None:
    connection = build_connection(queue_size=1, websocket=FakeWebSocket(SimpleNamespace()))
    connection.send_queue.put_nowait("stale")
    fanout = KafkaFanout(
        connection_registry=ConnectionRegistry(),
        subscription_registry=SubscriptionRegistry(),
        settings=PlatformSettings(),
        visibility_filter=_visibility_filter(),
    )
    fresh_event = EventMessage(
        channel="execution",
        resource_id=str(uuid4()),
        payload={"status": "fresh"},
        gateway_received_at=datetime.now(UTC),
    )

    dropped = fanout._enqueue(connection, fresh_event)

    assert dropped is True
    assert connection.dropped_count == 1
    assert connection.send_queue.qsize() == 1
    assert await connection.send_queue.get() == fresh_event


@pytest.mark.asyncio
async def test_writer_notifies_dropped_events_before_next_event() -> None:
    websocket = FakeWebSocket(SimpleNamespace())
    connection = build_connection(websocket=websocket)
    connection.dropped_count = 5
    connection.send_queue.put_nowait(
        EventMessage(
            channel="execution",
            resource_id=str(uuid4()),
            payload={"status": "running"},
            gateway_received_at=datetime.now(UTC),
        )
    )
    connection.closed.set()

    from platform.ws_hub.writer import ConnectionWriter

    await ConnectionWriter().run(connection)

    messages = websocket.decoded_messages()
    assert messages[0]["type"] == "events_dropped"
    assert messages[0]["count"] == 5
    assert messages[1]["type"] == "event"
    assert connection.dropped_count == 0


def _visibility_filter():
    from contextlib import asynccontextmanager

    service = StaticWorkspacesService()

    @asynccontextmanager
    async def factory():
        yield service

    from platform.ws_hub.visibility import VisibilityFilter

    return VisibilityFilter(factory)
