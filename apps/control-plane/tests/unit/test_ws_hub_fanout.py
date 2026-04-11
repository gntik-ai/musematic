from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.ws_hub.connection import ConnectionRegistry
from platform.ws_hub.fanout import KafkaFanout
from platform.ws_hub.schemas import EventMessage
from platform.ws_hub.subscription import (
    ChannelType,
    Subscription,
    SubscriptionRegistry,
    subscription_key,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.ws_hub_support import FakeWebSocket, StaticWorkspacesService, build_connection


@pytest.mark.asyncio
async def test_fanout_routes_matching_events_to_all_subscribers() -> None:
    execution_id = uuid4()
    workspace_id = uuid4()
    conn_one = build_connection(
        user_id=uuid4(),
        workspace_ids={workspace_id},
        websocket=FakeWebSocket(SimpleNamespace()),
    )
    conn_two = build_connection(
        user_id=uuid4(),
        workspace_ids={workspace_id},
        websocket=FakeWebSocket(SimpleNamespace()),
    )
    subscription = Subscription(channel=ChannelType.EXECUTION, resource_id=str(execution_id))
    key = subscription_key(subscription.channel, subscription.resource_id)

    connections = ConnectionRegistry()
    subscriptions = SubscriptionRegistry()
    connections.add(conn_one)
    connections.add(conn_two)
    conn_one.subscriptions[key] = subscription
    conn_two.subscriptions[key] = subscription
    subscriptions.subscribe(conn_one.connection_id, subscription)
    subscriptions.subscribe(conn_two.connection_id, subscription)

    visibility = _visibility_filter()
    fanout = KafkaFanout(connections, subscriptions, PlatformSettings(), visibility)
    envelope = EventEnvelope(
        event_type="execution.updated",
        source="tests",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
            execution_id=execution_id,
        ),
        payload={"status": "running"},
    )

    await fanout._route_event("workflow.runtime", envelope.model_dump(mode="json"))

    first = await conn_one.send_queue.get()
    second = await conn_two.send_queue.get()
    assert isinstance(first, EventMessage)
    assert isinstance(second, EventMessage)
    assert first.resource_id == str(execution_id)
    assert second.channel == ChannelType.EXECUTION.value


@pytest.mark.asyncio
async def test_fanout_filters_non_visible_events_and_handles_control_events() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    conn = build_connection(
        user_id=user_id,
        workspace_ids={workspace_id},
        websocket=FakeWebSocket(SimpleNamespace()),
    )
    connections = ConnectionRegistry()
    subscriptions = SubscriptionRegistry()
    connections.add(conn)
    visibility = _visibility_filter(user_id=user_id, workspace_id=workspace_id)
    fanout = KafkaFanout(connections, subscriptions, PlatformSettings(), visibility)

    invisible = EventEnvelope(
        event_type="execution.updated",
        source="tests",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=uuid4(),
            execution_id=uuid4(),
        ),
        payload={},
    )
    await fanout._route_event("workflow.runtime", invisible.model_dump(mode="json"))
    assert conn.send_queue.empty()

    revoked = EventEnvelope(
        event_type="auth.session.invalidated",
        source="tests",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={"user_id": str(user_id)},
    )
    await fanout._route_event("auth.events", revoked.model_dump(mode="json"))
    assert conn.websocket.close_calls[-1][0] == 4401

    conn.closed.clear()
    membership_removed = EventEnvelope(
        event_type="workspaces.membership.removed",
        source="tests",
        correlation_context=CorrelationContext(correlation_id=uuid4(), workspace_id=workspace_id),
        payload={"user_id": str(user_id), "workspace_id": str(workspace_id)},
    )
    await fanout._route_event("workspaces.events", membership_removed.model_dump(mode="json"))
    assert conn.workspace_ids == {workspace_id}


@pytest.mark.asyncio
async def test_fanout_enqueue_drops_oldest_when_queue_is_full() -> None:
    conn = build_connection(queue_size=1, websocket=FakeWebSocket(SimpleNamespace()))
    conn.send_queue.put_nowait("old")
    fanout = KafkaFanout(
        ConnectionRegistry(),
        SubscriptionRegistry(),
        PlatformSettings(),
        _visibility_filter(),
    )
    message = EventMessage(
        channel="execution",
        resource_id="resource-1",
        payload={},
        gateway_received_at=datetime.now(UTC),
    )

    fanout._enqueue(conn, message)

    assert conn.dropped_count == 1
    assert conn.send_queue.qsize() == 1
    assert await conn.send_queue.get() == message


@pytest.mark.asyncio
async def test_fanout_ensure_consuming_starts_and_stops_consumers(monkeypatch) -> None:
    created: list[FakeConsumer] = []

    class FakeConsumer:
        def __init__(self, *topics, **kwargs) -> None:
            self.topics = topics
            self.kwargs = kwargs
            self.started = False
            self.stopped = False

        async def start(self) -> None:
            self.started = True
            created.append(self)

        async def stop(self) -> None:
            self.stopped = True

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    monkeypatch.setattr(
        "platform.ws_hub.fanout.import_module",
        lambda name: SimpleNamespace(AIOKafkaConsumer=FakeConsumer),
    )

    fanout = KafkaFanout(
        ConnectionRegistry(),
        SubscriptionRegistry(),
        PlatformSettings(KAFKA_BROKERS="kafka:9092"),
        _visibility_filter(),
    )
    await fanout.start()
    await fanout.ensure_consuming(["workflow.runtime"])
    await asyncio.sleep(0)
    await fanout.release_topics(["workflow.runtime"])

    assert created[0].started is True
    assert created[0].stopped is True


def _visibility_filter(
    *,
    user_id=None,
    workspace_id=None,
):
    from contextlib import asynccontextmanager

    service = StaticWorkspacesService(
        workspace_ids_by_user={user_id: [workspace_id]} if user_id and workspace_id else {}
    )

    @asynccontextmanager
    async def factory():
        yield service

    from platform.ws_hub.visibility import VisibilityFilter

    return VisibilityFilter(factory)
