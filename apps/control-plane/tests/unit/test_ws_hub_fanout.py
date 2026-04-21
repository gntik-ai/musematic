from __future__ import annotations

import asyncio
import json
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


class RaisingCloseWebSocket(FakeWebSocket):
    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        await super().close(code=code, reason=reason)
        raise RuntimeError("close failed")


@pytest.mark.asyncio
async def test_fanout_matches_topic_variants_and_loads_envelopes() -> None:
    fanout = KafkaFanout(
        ConnectionRegistry(),
        SubscriptionRegistry(),
        PlatformSettings(),
        _visibility_filter(),
    )
    execution_id = uuid4()
    fleet_id = uuid4()
    interaction_id = uuid4()
    conversation_id = uuid4()
    workspace_id = uuid4()
    workspace_payload_id = uuid4()
    simulation_id = uuid4()
    suite_id = uuid4()
    user_id = uuid4()
    target_id = uuid4()
    corr = {
        "execution_id": str(execution_id),
        "fleet_id": str(fleet_id),
        "interaction_id": str(interaction_id),
        "conversation_id": str(conversation_id),
        "workspace_id": str(workspace_id),
    }

    assert fanout._match_subscriptions(
        "workflow.runtime", {"correlation_context": corr, "payload": {}}
    ) == [(ChannelType.EXECUTION, str(execution_id))]
    assert fanout._match_subscriptions(
        "runtime.lifecycle", {"correlation_context": corr, "payload": {}}
    ) == [
        (ChannelType.EXECUTION, str(execution_id)),
        (ChannelType.FLEET, str(fleet_id)),
    ]
    assert fanout._match_subscriptions(
        "interaction.events", {"correlation_context": corr, "payload": {}}
    ) == [
        (ChannelType.INTERACTION, str(interaction_id)),
        (ChannelType.CONVERSATION, str(conversation_id)),
    ]
    assert fanout._match_subscriptions(
        "workspaces.events",
        {
            "correlation_context": {"workspace_id": str(workspace_id)},
            "payload": {"workspace_id": str(workspace_payload_id)},
        },
    ) == [
        (ChannelType.WORKSPACE, str(workspace_id)),
        (ChannelType.WORKSPACE, str(workspace_payload_id)),
    ]
    assert fanout._match_subscriptions(
        "runtime.reasoning", {"correlation_context": corr, "payload": {}}
    ) == [(ChannelType.REASONING, str(execution_id))]
    assert fanout._match_subscriptions(
        "runtime.selfcorrection", {"correlation_context": corr, "payload": {}}
    ) == [(ChannelType.CORRECTION, str(execution_id))]
    assert fanout._match_subscriptions(
        "simulation.events", {"payload": {"simulation_id": str(simulation_id)}}
    ) == [(ChannelType.SIMULATION, str(simulation_id))]
    assert fanout._match_subscriptions(
        "testing.results", {"payload": {"suite_id": str(suite_id)}}
    ) == [(ChannelType.TESTING, str(suite_id))]
    assert fanout._match_subscriptions(
        "monitor.alerts", {"payload": {"target_id": str(target_id)}}
    ) == [(ChannelType.ALERTS, str(target_id))]
    assert fanout._match_subscriptions(
        "notifications.alerts", {"payload": {"user_id": str(user_id)}}
    ) == [(ChannelType.ALERTS, str(user_id))]
    assert fanout._match_subscriptions(
        "interaction.attention", {"payload": {"target_id": str(target_id)}}
    ) == [(ChannelType.ATTENTION, str(target_id))]
    assert fanout._match_subscriptions(
        "interaction.attention", {"payload": {"target_identity": str(user_id)}}
    ) == [(ChannelType.ATTENTION, str(user_id))]

    envelope = EventEnvelope(
        event_type="execution.updated",
        source="tests",
        correlation_context=CorrelationContext(correlation_id=uuid4(), execution_id=execution_id),
        payload={"status": "running"},
    )
    assert KafkaFanout._load_envelope(envelope) is envelope
    assert (
        KafkaFanout._load_envelope(envelope.model_dump(mode="json")).event_type
        == envelope.event_type
    )
    assert (
        KafkaFanout._load_envelope(json.dumps(envelope.model_dump(mode="json"))).event_type
        == envelope.event_type
    )
    assert (
        KafkaFanout._load_envelope(
            json.dumps(
                {
                    "event_type": envelope.event_type,
                    "source": envelope.source,
                    "correlation": envelope.correlation_context.model_dump(mode="json"),
                    "payload": envelope.payload,
                }
            ).encode("utf-8")
        ).event_type
        == envelope.event_type
    )
    assert KafkaFanout._as_resource_id(None) is None
    with pytest.raises(TypeError):
        KafkaFanout._load_envelope(object())


@pytest.mark.asyncio
async def test_fanout_control_events_cover_invalid_and_exception_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    open_conn = build_connection(
        user_id=user_id,
        workspace_ids={workspace_id},
        websocket=RaisingCloseWebSocket(SimpleNamespace()),
    )
    closed_conn = build_connection(
        user_id=user_id,
        workspace_ids={workspace_id},
        websocket=FakeWebSocket(SimpleNamespace()),
    )
    closed_conn.closed.set()
    connections = ConnectionRegistry()
    connections.add(open_conn)
    connections.add(closed_conn)
    visibility = _visibility_filter(user_id=user_id, workspace_id=workspace_id)
    refreshed: list[str] = []

    async def _refresh(conn) -> None:
        refreshed.append(conn.connection_id)

    monkeypatch.setattr(visibility, "refresh_connection_memberships", _refresh)
    fanout = KafkaFanout(connections, SubscriptionRegistry(), PlatformSettings(), visibility)

    await fanout._handle_control_event(
        "auth.events", {"event_type": "auth.session.invalidated", "payload": {}}
    )
    await fanout._handle_control_event(
        "auth.events",
        {"event_type": "auth.session.invalidated", "payload": {"user_id": "not-a-uuid"}},
    )
    await fanout._handle_control_event(
        "auth.events",
        {"event_type": "auth.session.invalidated", "payload": {"user_id": str(user_id)}},
    )
    await fanout._handle_control_event(
        "workspaces.events",
        {"event_type": "workspaces.membership.removed", "payload": {"user_id": "not-a-uuid"}},
    )
    await fanout._handle_control_event(
        "workspaces.events",
        {"event_type": "workspaces.membership.role_changed", "payload": {"user_id": str(user_id)}},
    )

    assert open_conn.websocket.close_calls[-1] == (4401, "session-invalidated")
    assert refreshed == [open_conn.connection_id, closed_conn.connection_id]


@pytest.mark.asyncio
async def test_fanout_ensure_consuming_returns_when_not_started() -> None:
    fanout = KafkaFanout(
        ConnectionRegistry(),
        SubscriptionRegistry(),
        PlatformSettings(KAFKA_BROKERS="kafka:9092"),
        _visibility_filter(),
    )

    await fanout.ensure_consuming(["workflow.runtime"])

    assert fanout._consumers == {}


@pytest.mark.asyncio
async def test_fanout_route_event_and_consumer_loop_cover_remaining_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    execution_id = uuid4()
    visible_conn = build_connection(
        user_id=uuid4(),
        workspace_ids={workspace_id},
        websocket=FakeWebSocket(SimpleNamespace()),
    )
    closed_conn = build_connection(
        user_id=uuid4(),
        workspace_ids={workspace_id},
        websocket=FakeWebSocket(SimpleNamespace()),
    )
    closed_conn.closed.set()
    connections = ConnectionRegistry()
    connections.add(visible_conn)
    connections.add(closed_conn)
    subscriptions = SubscriptionRegistry()
    subscription = Subscription(channel=ChannelType.EXECUTION, resource_id=str(execution_id))
    subscriptions.subscribe("missing-conn", subscription)
    subscriptions.subscribe(closed_conn.connection_id, subscription)
    subscriptions.subscribe(visible_conn.connection_id, subscription)

    visibility = _visibility_filter()
    fanout = KafkaFanout(connections, subscriptions, PlatformSettings(), visibility)
    monkeypatch.setattr(visibility, "is_visible", lambda envelope, conn: conn is not visible_conn)

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
    assert visible_conn.send_queue.empty()

    monkeypatch.setattr(visibility, "is_visible", lambda envelope, conn: conn is visible_conn)
    await fanout._route_event("workflow.runtime", envelope.model_dump(mode="json"))
    delivered = await visible_conn.send_queue.get()
    assert delivered.resource_id == str(execution_id)

    class LoopConsumer:
        def __init__(self) -> None:
            self.committed = False
            self.stopped = False
            self._messages = [SimpleNamespace(value=envelope.model_dump(mode="json"))]

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._messages:
                raise StopAsyncIteration
            return self._messages.pop(0)

        async def commit(self) -> None:
            self.committed = True

        def stop(self) -> None:
            self.stopped = True

    loop_consumer = LoopConsumer()
    routed: list[str] = []

    async def _route(topic: str, raw_message) -> None:
        del raw_message
        routed.append(topic)

    monkeypatch.setattr(fanout, "_route_event", _route)
    await fanout._consumer_loop("workflow.runtime", loop_consumer)
    assert routed == ["workflow.runtime"]
    assert loop_consumer.committed is True

    fanout._consumers = {"workflow.runtime": loop_consumer, "other": object()}
    fanout._tasks = {"workflow.runtime": asyncio.create_task(asyncio.sleep(3600))}
    await fanout.stop()
    assert loop_consumer.stopped is True
    assert fanout._started is False


@pytest.mark.asyncio
async def test_fanout_release_topics_drop_metrics_and_match_empty_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    execution_id = uuid4()
    conn = build_connection(
        user_id=uuid4(),
        workspace_ids={workspace_id},
        websocket=FakeWebSocket(SimpleNamespace()),
    )
    connections = ConnectionRegistry()
    connections.add(conn)
    subscriptions = SubscriptionRegistry()
    subscription = Subscription(channel=ChannelType.EXECUTION, resource_id=str(execution_id))
    subscriptions.subscribe(conn.connection_id, subscription)
    visibility = _visibility_filter()
    fanout = KafkaFanout(connections, subscriptions, PlatformSettings(), visibility)

    drops: list[str] = []
    monkeypatch.setattr(fanout, "_enqueue", lambda connection, message: True)
    monkeypatch.setattr(fanout._metrics, "dropped", lambda: drops.append("dropped"))

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
    assert drops == ["dropped"]

    class NonAwaitableConsumer:
        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    consumer = NonAwaitableConsumer()
    fanout._consumers = {"workflow.runtime": consumer}
    fanout._tasks = {"workflow.runtime": asyncio.create_task(asyncio.sleep(3600))}
    await fanout.release_topics(["workflow.runtime"])
    assert consumer.stopped is True

    empty_cases = [
        ("workflow.runtime", {"correlation_context": {}, "payload": {}}),
        ("runtime.lifecycle", {"correlation_context": {}, "payload": {}}),
        ("interaction.events", {"correlation_context": {}, "payload": {}}),
        ("workspaces.events", {"correlation_context": {}, "payload": {}}),
        ("runtime.reasoning", {"correlation_context": {}, "payload": {}}),
        ("runtime.selfcorrection", {"correlation_context": {}, "payload": {}}),
        ("simulation.events", {"payload": {}}),
        ("testing.results", {"payload": {}}),
        ("monitor.alerts", {"payload": {}}),
        ("notifications.alerts", {"payload": {}}),
        ("interaction.attention", {"payload": {}}),
    ]
    for topic, raw_envelope in empty_cases:
        assert fanout._match_subscriptions(topic, raw_envelope) == []


@pytest.mark.asyncio
async def test_fanout_consumer_loop_accepts_sync_commit() -> None:
    fanout = KafkaFanout(
        ConnectionRegistry(),
        SubscriptionRegistry(),
        PlatformSettings(),
        _visibility_filter(),
    )
    routed: list[str] = []

    async def _route(topic: str, raw_message) -> None:
        del raw_message
        routed.append(topic)

    fanout._route_event = _route  # type: ignore[method-assign]

    class SyncCommitConsumer:
        def __init__(self) -> None:
            self.committed = False
            self._messages = [SimpleNamespace(value={})]

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._messages:
                raise StopAsyncIteration
            return self._messages.pop(0)

        def commit(self) -> None:
            self.committed = True

    consumer = SyncCommitConsumer()
    await fanout._consumer_loop("workflow.runtime", consumer)

    assert routed == ["workflow.runtime"]
    assert consumer.committed is True
