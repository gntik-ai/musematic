from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.ws_hub import dependencies
from platform.ws_hub.exceptions import (
    ProtocolViolationError,
    SubscriptionAuthError,
    SubscriptionStateError,
    WebSocketGatewayError,
)
from platform.ws_hub.fanout import KafkaFanout
from platform.ws_hub.heartbeat import ConnectionHeartbeat
from platform.ws_hub.router import (
    _cleanup_connection,
    _deny,
    _extract_token,
    _handle_subscribe,
    _handle_unsubscribe,
    _handle_validation_error,
    _receive_loop,
    _validate_token,
)
from platform.ws_hub.schemas import (
    EventMessage,
    SubscribeMessage,
    UnsubscribeMessage,
    parse_client_message,
)
from platform.ws_hub.subscription import ChannelType, Subscription, SubscriptionRegistry
from platform.ws_hub.visibility import VisibilityFilter
from platform.ws_hub.writer import ConnectionWriter
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from tests.ws_hub_support import (
    FakeWebSocket,
    RecordingFanout,
    StaticAuthService,
    StaticWorkspacesService,
    build_connection,
    build_state,
)


def test_dependency_getters_and_exception_validation() -> None:
    state = build_state()
    websocket = FakeWebSocket(state)

    assert dependencies.get_connection_registry(websocket) is state.connection_registry
    assert dependencies.get_subscription_registry(websocket) is state.subscription_registry
    assert dependencies.get_fanout(websocket) is state.fanout
    assert dependencies.get_visibility_filter(websocket) is state.visibility_filter

    error = WebSocketGatewayError("protocol_violation", "boom")
    assert error.code == "protocol_violation"
    assert error.message == "boom"
    valid_state_error = SubscriptionStateError("already_subscribed", "duplicate")
    assert valid_state_error.code == "already_subscribed"

    with pytest.raises(ValueError, match="Unsupported subscription auth error code"):
        SubscriptionAuthError("boom", "bad")
    with pytest.raises(ValueError, match="Unsupported protocol violation code"):
        ProtocolViolationError("boom", "bad")
    with pytest.raises(ValueError, match="Unsupported subscription state error code"):
        SubscriptionStateError("boom", "bad")


@pytest.mark.asyncio
async def test_visibility_branches_for_user_scope_and_invalid_workspace_id() -> None:
    user_id = uuid4()
    conn = build_connection(user_id=user_id, workspace_ids={uuid4(), uuid4()})
    service = StaticWorkspacesService()
    visibility = _visibility_filter(service)

    with pytest.raises(SubscriptionAuthError) as exc_info:
        await visibility.authorize_subscription(conn, ChannelType.ALERTS, str(uuid4()))

    assert exc_info.value.code == "unauthorized"
    assert visibility.is_visible({"correlation_context": {"workspace_id": "bad"}}, conn) is False

    with pytest.raises(SubscriptionAuthError) as missing_exc:
        await visibility.authorize_subscription(conn, ChannelType.WORKSPACE, str(uuid4()))

    assert missing_exc.value.code == "resource_not_found"


@pytest.mark.asyncio
async def test_fanout_helpers_cover_parsing_and_stop_paths(monkeypatch) -> None:
    fanout = KafkaFanout(
        dependencies.get_connection_registry(FakeWebSocket(build_state())),
        SubscriptionRegistry(),
        PlatformSettings(),
        _visibility_filter(),
    )

    assert fanout._match_subscriptions(
        "runtime.lifecycle",
        {
            "correlation_context": {
                "execution_id": str(uuid4()),
                "fleet_id": str(uuid4()),
            },
            "payload": {},
        },
    )
    assert fanout._match_subscriptions(
        "interaction.events",
        {
            "correlation_context": {
                "interaction_id": str(uuid4()),
                "conversation_id": str(uuid4()),
            },
            "payload": {},
        },
    )
    simulation_id = str(uuid4())
    assert fanout._match_subscriptions(
        "simulation.events",
        {"payload": {"simulation_id": simulation_id}},
    ) == [(ChannelType.SIMULATION, simulation_id)]
    assert fanout._match_subscriptions(
        "testing.results",
        {"payload": {"suite_id": str(uuid4())}},
    )
    assert fanout._match_subscriptions(
        "monitor.alerts",
        {"payload": {"target_id": str(uuid4())}},
    )
    assert fanout._match_subscriptions(
        "interaction.attention",
        {"payload": {"target_id": str(uuid4())}},
    )
    assert fanout._match_subscriptions("unknown", {"payload": {}}) == []
    assert fanout._as_resource_id(None) is None
    assert fanout._load_envelope(
        EventEnvelope(
            event_type="x",
            source="tests",
            correlation_context=CorrelationContext(correlation_id=uuid4()),
            payload={},
        )
    ).event_type == "x"
    assert fanout._load_envelope(
        {
            "event_type": "x",
            "source": "tests",
            "correlation": {"correlation_id": str(uuid4())},
            "payload": {},
        }
    ).event_type == "x"
    assert fanout._load_envelope(
        
            EventEnvelope(
                event_type="x",
                source="tests",
                correlation_context=CorrelationContext(correlation_id=uuid4()),
                payload={},
            )
            .model_dump_json()
            .encode("utf-8")
        
    ).event_type == "x"
    assert fanout._load_envelope(
        EventEnvelope(
            event_type="x",
            source="tests",
            correlation_context=CorrelationContext(correlation_id=uuid4()),
            payload={},
        ).model_dump_json()
    ).event_type == "x"
    with pytest.raises(TypeError):
        fanout._load_envelope(123)

    class PassiveConsumer:
        def __init__(self, *args, **kwargs) -> None:
            self.started = False
            self.stopped = False

        async def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    monkeypatch.setattr(
        "platform.ws_hub.fanout.import_module",
        lambda name: SimpleNamespace(AIOKafkaConsumer=PassiveConsumer),
    )
    await fanout.ensure_consuming(["workflow.runtime"])
    await fanout.start()
    await fanout.ensure_consuming(["workflow.runtime"])
    await fanout.ensure_consuming(["workflow.runtime"])
    await fanout.stop()


@pytest.mark.asyncio
async def test_fanout_stop_and_control_event_edge_branches() -> None:
    fanout = KafkaFanout(
        dependencies.get_connection_registry(FakeWebSocket(build_state())),
        SubscriptionRegistry(),
        PlatformSettings(),
        _visibility_filter(),
    )

    async def pending() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise

    class ClosingConsumer:
        def __init__(self) -> None:
            self.stopped = False

        async def stop(self) -> None:
            self.stopped = True

    consumer = ClosingConsumer()
    task = asyncio.create_task(pending())
    fanout._tasks["topic"] = task
    fanout._consumers["topic"] = consumer
    await fanout.stop()
    assert consumer.stopped is True

    user_id = uuid4()
    conn = build_connection(user_id=user_id, websocket=FakeWebSocket(SimpleNamespace()))
    conn.closed.set()
    registry = dependencies.get_connection_registry(FakeWebSocket(build_state()))
    registry.add(conn)
    control_fanout = KafkaFanout(
        registry,
        SubscriptionRegistry(),
        PlatformSettings(),
        _visibility_filter(),
    )
    await control_fanout._handle_control_event(
        "auth.events",
        {"event_type": "auth.session.revoked", "payload": {}},
    )
    await control_fanout._handle_control_event(
        "auth.events",
        {"event_type": "auth.session.revoked", "payload": {"user_id": "bad"}},
    )
    await control_fanout._handle_control_event(
        "workspaces.events",
        {"event_type": "workspaces.membership.removed", "payload": {}},
    )
    await control_fanout._handle_control_event(
        "workspaces.events",
        {"event_type": "workspaces.membership.removed", "payload": {"user_id": "bad"}},
    )


@pytest.mark.asyncio
async def test_fanout_route_event_skips_missing_connections_and_invisible_subscribers() -> None:
    workspace_id = uuid4()
    visible_conn = build_connection(
        user_id=uuid4(),
        workspace_ids={workspace_id},
        websocket=FakeWebSocket(SimpleNamespace()),
    )
    registry = dependencies.get_connection_registry(FakeWebSocket(build_state()))
    subscriptions = SubscriptionRegistry()
    registry.add(visible_conn)
    subscription = Subscription(channel=ChannelType.REASONING, resource_id=str(uuid4()))
    subscriptions.subscribe("missing-conn", subscription)
    subscriptions.subscribe(visible_conn.connection_id, subscription)
    visible_conn.subscriptions[f"{subscription.channel}:{subscription.resource_id}"] = subscription

    class InvisibleFilter:
        def is_visible(self, envelope, conn):  # type: ignore[no-untyped-def]
            return False

        async def refresh_connection_memberships(self, conn):  # type: ignore[no-untyped-def]
            return None

    fanout = KafkaFanout(registry, subscriptions, PlatformSettings(), InvisibleFilter())  # type: ignore[arg-type]
    envelope = {
        "event_type": "reasoning.updated",
        "source": "tests",
        "correlation_context": {
            "correlation_id": str(uuid4()),
            "execution_id": subscription.resource_id,
            "workspace_id": str(workspace_id),
        },
        "payload": {},
    }

    await fanout._route_event("runtime.reasoning", envelope)
    assert visible_conn.send_queue.empty()


def test_fanout_enqueue_handles_queuefull_then_queueempty() -> None:
    fanout = KafkaFanout(
        dependencies.get_connection_registry(FakeWebSocket(build_state())),
        SubscriptionRegistry(),
        PlatformSettings(),
        _visibility_filter(),
    )

    class FakeQueue:
        def __init__(self) -> None:
            self.calls = 0
            self.items: list[object] = []

        def put_nowait(self, item):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                raise asyncio.QueueFull
            self.items.append(item)

        def get_nowait(self):  # type: ignore[no-untyped-def]
            raise asyncio.QueueEmpty

    conn = build_connection(websocket=FakeWebSocket(SimpleNamespace()))
    conn.send_queue = FakeQueue()  # type: ignore[assignment]
    message = EventMessage(
        channel="alerts",
        resource_id=str(uuid4()),
        payload={},
        gateway_received_at=datetime.now(UTC),
    )

    fanout._enqueue(conn, message)

    assert conn.dropped_count == 1
    assert conn.send_queue.items == [message]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_fanout_consumer_loop_commits_and_handles_edge_cases(monkeypatch) -> None:
    workspace_id = uuid4()
    connection = build_connection(workspace_ids={workspace_id})
    connections = dependencies.get_connection_registry(FakeWebSocket(build_state()))
    subscriptions = SubscriptionRegistry()
    visibility = _visibility_filter()
    fanout = KafkaFanout(connections, subscriptions, PlatformSettings(), visibility)

    subscription = Subscription(channel=ChannelType.WORKSPACE, resource_id=str(workspace_id))
    key = f"{subscription.channel}:{subscription.resource_id}"
    connection.subscriptions[key] = subscription
    connections.add(connection)
    subscriptions.subscribe(connection.connection_id, subscription)

    envelope = EventEnvelope(
        event_type="workspaces.workspace.updated",
        source="tests",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=UUID(subscription.resource_id),
        ),
        payload={},
    )

    class Message:
        value = envelope.model_dump(mode="json")

    class Consumer:
        def __init__(self) -> None:
            self.messages = [Message()]
            self.committed = False

        async def commit(self) -> None:
            self.committed = True

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.messages:
                raise StopAsyncIteration
            return self.messages.pop(0)

    consumer = Consumer()
    await fanout._consumer_loop("workspaces.events", consumer)

    assert consumer.committed is True
    assert connection.send_queue.qsize() == 1

    connection.closed.set()
    closed_envelope = EventEnvelope(
        event_type="auth.session.revoked",
        source="tests",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={"user_id": "not-a-uuid"},
    )
    await fanout._route_event("auth.events", closed_envelope.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_router_helpers_cover_duplicate_unsubscribe_and_validation_paths() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    state = build_state(
        auth_service=StaticAuthService({"good": {"sub": str(user_id), "type": "access"}}),
        workspaces_service=StaticWorkspacesService(
            workspace_ids_by_user={user_id: [workspace_id]},
            resource_workspace_map={},
        ),
    )
    empty_bearer = FakeWebSocket(
        state,
        headers={"Authorization": "Bearer "},
    )
    websocket = FakeWebSocket(
        state,
        query_params={"token": "good"},
    )
    connection = build_connection(
        user_id=user_id,
        workspace_ids={workspace_id},
        websocket=websocket,
    )

    assert _extract_token(empty_bearer) is None
    assert _extract_token(websocket) == "good"
    assert (await _validate_token(websocket, "good"))["sub"] == str(user_id)
    await _deny(websocket, 403, "forbidden")
    assert websocket.denial_status_code == 403

    subscription_registry = SubscriptionRegistry()
    fanout = RecordingFanout()
    subscription = Subscription(channel=ChannelType.WORKSPACE, resource_id=str(uuid4()))
    key = f"{subscription.channel}:{subscription.resource_id}"
    connection.subscriptions[key] = subscription
    subscription_registry.subscribe(connection.connection_id, subscription)

    await _handle_subscribe(
        websocket,
        connection,
        SubscribeMessage(
            type="subscribe",
            channel=ChannelType.WORKSPACE,
            resource_id=subscription.resource_id,
        ),
        subscription_registry,
        fanout,
        state.visibility_filter,
    )
    await _handle_unsubscribe(
        websocket,
        connection,
        UnsubscribeMessage(
            type="unsubscribe",
            channel=ChannelType.EXECUTION,
            resource_id=str(uuid4()),
        ),
        subscription_registry,
        fanout,
    )
    await _handle_validation_error(
        websocket,
        connection,
        {"type": "subscribe", "channel": "workspace"},
        _subscribe_validation_error(),
    )
    await _handle_validation_error(
        websocket,
        connection,
        {"type": "other"},
        _unknown_message_validation_error(),
    )
    assert connection.malformed_message_count == 1
    assert websocket.decoded_messages()[-1]["type"] == "error"

    other_workspace = uuid4()
    unauthorized_state = build_state(
        workspaces_service=StaticWorkspacesService(
            resource_workspace_map={
                (ChannelType.WORKSPACE.value, UUID(subscription.resource_id)): other_workspace,
            }
        )
    )
    unauthorized_socket = FakeWebSocket(unauthorized_state)
    unauthorized_conn = build_connection(
        user_id=user_id,
        workspace_ids={workspace_id},
        websocket=unauthorized_socket,
    )
    await _handle_subscribe(
        unauthorized_socket,
        unauthorized_conn,
        SubscribeMessage(
            type="subscribe",
            channel=ChannelType.WORKSPACE,
            resource_id=subscription.resource_id,
        ),
        SubscriptionRegistry(),
        fanout,
        unauthorized_state.visibility_filter,
    )
    assert unauthorized_socket.decoded_messages()[-1]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_receive_loop_and_cleanup_cover_remaining_router_branches(monkeypatch) -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    state = build_state(
        auth_service=StaticAuthService({"good": {"sub": str(user_id), "type": "access"}}),
        workspaces_service=StaticWorkspacesService(
            workspace_ids_by_user={user_id: [workspace_id]},
        ),
    )
    websocket = FakeWebSocket(
        state,
        incoming=[
            "[]",
            '{"type":"unsubscribe","channel":"execution","resource_id":"bad"}',
        ],
    )
    connection = build_connection(
        user_id=user_id,
        workspace_ids={workspace_id},
        websocket=websocket,
    )
    connection.tasks = {asyncio.create_task(asyncio.sleep(0))}

    await _receive_loop(
        websocket,
        connection,
        SubscriptionRegistry(),
        RecordingFanout(),
        state.visibility_filter,
    )
    assert websocket.decoded_messages()[0]["type"] == "error"

    fanout = RecordingFanout()
    registry = dependencies.get_connection_registry(FakeWebSocket(state))
    registry.add(connection)
    await _cleanup_connection(connection, registry, SubscriptionRegistry(), fanout)
    assert fanout.released[-1] == ["auth.events"]

    workspace_subscription = Subscription(
        channel=ChannelType.WORKSPACE,
        resource_id=str(workspace_id),
    )
    key = f"{workspace_subscription.channel}:{workspace_subscription.resource_id}"
    open_conn = build_connection(
        user_id=user_id,
        workspace_ids={workspace_id},
        websocket=FakeWebSocket(state),
    )
    open_conn.subscriptions[key] = workspace_subscription
    open_registry = dependencies.get_connection_registry(FakeWebSocket(state))
    open_subscriptions = SubscriptionRegistry()
    open_registry.add(open_conn)
    open_subscriptions.subscribe(open_conn.connection_id, workspace_subscription)
    fanout = RecordingFanout()
    await _cleanup_connection(open_conn, open_registry, open_subscriptions, fanout)
    assert open_conn.closed.is_set() is True
    assert fanout.released[-1] == ["auth.events", "workspaces.events"]


@pytest.mark.asyncio
async def test_heartbeat_and_writer_cover_timeout_and_error_paths(monkeypatch) -> None:
    websocket = FakeWebSocket(SimpleNamespace())
    connection = build_connection(websocket=websocket)

    async def send_and_stop(_: bytes) -> None:
        connection.closed.set()
        websocket.sent_bytes.append(b"")

    websocket.send_bytes = send_and_stop
    await ConnectionHeartbeat(interval_seconds=0, timeout_seconds=10).run(connection)
    assert websocket.sent_bytes == [b""]

    failing_socket = FakeWebSocket(SimpleNamespace(), fail_send_bytes=True)
    failing_conn = build_connection(websocket=failing_socket)
    await ConnectionHeartbeat(interval_seconds=0, timeout_seconds=10).run(failing_conn)
    assert failing_conn.closed.is_set() is True

    timeout_socket = FakeWebSocket(SimpleNamespace())
    timeout_conn = build_connection(websocket=timeout_socket)
    calls = {"count": 0}
    real_wait_for = asyncio.wait_for

    async def fake_wait_for(awaitable, delay=None, **kwargs):  # type: ignore[no-untyped-def]
        if calls["count"] == 0:
            calls["count"] += 1
            timeout_conn.closed.set()
            awaitable.close()
            raise TimeoutError
        return await real_wait_for(awaitable, delay or kwargs["timeout"])

    monkeypatch.setattr("platform.ws_hub.writer.asyncio.wait_for", fake_wait_for)
    await ConnectionWriter().run(timeout_conn)

    text_socket = FakeWebSocket(SimpleNamespace())
    text_conn = build_connection(websocket=text_socket)
    text_conn.send_queue.put_nowait("plain-text")
    text_conn.closed.set()
    await ConnectionWriter().run(text_conn)
    assert text_socket.sent_text == ["plain-text"]

    closing_socket = FakeWebSocket(SimpleNamespace())
    closing_conn = build_connection(websocket=closing_socket)

    async def close_before_return(_: float) -> None:
        closing_conn.closed.set()

    monkeypatch.setattr("platform.ws_hub.heartbeat.asyncio.sleep", close_before_return)
    await ConnectionHeartbeat(interval_seconds=0, timeout_seconds=10).run(closing_conn)
    assert closing_socket.sent_bytes == []

    broken_close_socket = FakeWebSocket(SimpleNamespace())
    broken_conn = build_connection(websocket=broken_close_socket)
    broken_conn.last_pong_at = datetime.now(UTC).replace(year=2000)

    async def broken_close(*, code: int = 1000, reason: str | None = None) -> None:
        raise RuntimeError("close failed")

    broken_close_socket.close = broken_close  # type: ignore[assignment]
    monkeypatch.setattr("platform.ws_hub.heartbeat.asyncio.sleep", asyncio.sleep)
    await ConnectionHeartbeat(interval_seconds=0, timeout_seconds=1).run(broken_conn)
    assert broken_conn.closed.is_set() is True


def _visibility_filter(service: StaticWorkspacesService | None = None) -> VisibilityFilter:
    from contextlib import asynccontextmanager

    resolved = service or StaticWorkspacesService()

    @asynccontextmanager
    async def factory():
        yield resolved

    return VisibilityFilter(factory)


def _subscribe_validation_error():
    from pydantic import ValidationError

    try:
        SubscribeMessage.model_validate({"type": "subscribe", "channel": "workspace"})
    except ValidationError as exc:
        return exc
    raise AssertionError("unreachable")


def _unknown_message_validation_error():
    from pydantic import ValidationError

    try:
        parse_client_message({"type": "other"})
    except ValidationError as exc:
        return exc
    raise AssertionError("unreachable")
