from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime
from importlib import import_module
from platform.common import database
from platform.common.events.envelope import CorrelationContext, make_envelope
from platform.common.logging import get_logger
from platform.execution.repository import ExecutionRepository
from platform.ws_hub.connection import ConnectionRegistry, WebSocketConnection
from platform.ws_hub.dependencies import (
    get_connection_registry,
    get_fanout,
    get_subscription_registry,
    get_visibility_filter,
)
from platform.ws_hub.exceptions import ProtocolViolationError, SubscriptionAuthError
from platform.ws_hub.fanout import KafkaFanout
from platform.ws_hub.heartbeat import ConnectionHeartbeat
from platform.ws_hub.schemas import (
    ConnectionEstablishedMessage,
    ErrorMessage,
    EventMessage,
    ListSubscriptionsMessage,
    SubscribeMessage,
    SubscriptionConfirmedMessage,
    SubscriptionErrorMessage,
    SubscriptionInfo,
    SubscriptionListMessage,
    SubscriptionRemovedMessage,
    UnsubscribeMessage,
    parse_client_message,
)
from platform.ws_hub.subscription import (
    WORKSPACE_SCOPED_CHANNELS,
    ChannelType,
    Subscription,
    SubscriptionRegistry,
    subscription_key,
)
from platform.ws_hub.visibility import VisibilityFilter
from platform.ws_hub.writer import ConnectionWriter
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, WebSocket
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

router = APIRouter()
LOGGER = get_logger(__name__)


class _RouterMetrics:
    def __init__(self) -> None:
        self._active_connections = None
        try:
            metrics_module = import_module("opentelemetry.metrics")
            meter = metrics_module.get_meter(__name__)
            self._active_connections = meter.create_up_down_counter(
                "ws_hub.connections.active",
                description="Active WebSocket connections handled by ws-hub.",
                unit="{connection}",
            )
        except Exception:
            self._active_connections = None

    def connection_opened(self) -> None:
        if self._active_connections is not None:
            self._active_connections.add(1)

    def connection_closed(self) -> None:
        if self._active_connections is not None:
            self._active_connections.add(-1)


ROUTER_METRICS = _RouterMetrics()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    connection_registry: ConnectionRegistry = Depends(get_connection_registry),
    subscription_registry: SubscriptionRegistry = Depends(get_subscription_registry),
    fanout: KafkaFanout = Depends(get_fanout),
    visibility_filter: VisibilityFilter = Depends(get_visibility_filter),
) -> None:
    token = _extract_token(websocket)
    if token is None:
        await _deny(websocket, 401, "Missing authentication token")
        return

    try:
        auth_payload = await _validate_token(websocket, token)
    except _ConnectionDeniedError as exc:
        await _deny(websocket, exc.status_code, exc.message)
        return

    user_id = UUID(str(auth_payload["sub"]))
    workspace_ids = await _load_workspace_ids(websocket, user_id)

    await websocket.accept()
    connection = WebSocketConnection(
        connection_id=str(uuid4()),
        user_id=user_id,
        workspace_ids=set(workspace_ids),
        websocket=websocket,
        send_queue=asyncio.Queue(maxsize=websocket.app.state.settings.WS_CLIENT_BUFFER_SIZE),
    )
    connection_registry.add(connection)
    ROUTER_METRICS.connection_opened()

    writer = ConnectionWriter()
    heartbeat = ConnectionHeartbeat(
        websocket.app.state.settings.WS_HEARTBEAT_INTERVAL_SECONDS,
        websocket.app.state.settings.WS_HEARTBEAT_TIMEOUT_SECONDS,
    )
    connection.tasks = {
        asyncio.create_task(writer.run(connection)),
        asyncio.create_task(heartbeat.run(connection)),
    }

    try:
        await fanout.ensure_consuming(["auth.events"])
        auto_subscriptions = await _auto_subscribe_user_channels(
            connection,
            subscription_registry,
            fanout,
        )
        welcome = ConnectionEstablishedMessage(
            connection_id=connection.connection_id,
            user_id=str(connection.user_id),
            server_time=datetime.now(UTC),
            auto_subscriptions=auto_subscriptions,
        )
        await websocket.send_text(welcome.model_dump_json())
        await _receive_loop(
            websocket,
            connection,
            subscription_registry,
            fanout,
            visibility_filter,
        )
    finally:
        await _cleanup_connection(connection, connection_registry, subscription_registry, fanout)


async def _receive_loop(
    websocket: WebSocket,
    connection: WebSocketConnection,
    subscription_registry: SubscriptionRegistry,
    fanout: KafkaFanout,
    visibility_filter: VisibilityFilter,
) -> None:
    while not connection.closed.is_set():
        try:
            raw_message = await websocket.receive_text()
        except WebSocketDisconnect:
            connection.closed.set()
            return

        connection.last_pong_at = datetime.now(UTC)

        try:
            payload = json.loads(raw_message)
            if not isinstance(payload, dict):
                raise ProtocolViolationError(
                    "protocol_violation",
                    "Malformed message: expected JSON object",
                )
            message = parse_client_message(payload)
        except json.JSONDecodeError:
            await _handle_protocol_error(
                websocket,
                connection,
                ErrorMessage(error="Malformed JSON payload", code="protocol_violation"),
            )
            continue
        except ValidationError as exc:
            current_payload = payload if "payload" in locals() else {}
            await _handle_validation_error(
                websocket,
                connection,
                current_payload,
                exc,
            )
            continue
        except ProtocolViolationError as exc:
            await _handle_protocol_error(
                websocket,
                connection,
                ErrorMessage(error=exc.message, code=exc.code),
            )
            continue

        if isinstance(message, SubscribeMessage):
            await _handle_subscribe(
                websocket,
                connection,
                message,
                subscription_registry,
                fanout,
                visibility_filter,
            )
        elif isinstance(message, UnsubscribeMessage):
            await _handle_unsubscribe(
                websocket,
                connection,
                message,
                subscription_registry,
                fanout,
            )
        elif isinstance(message, ListSubscriptionsMessage):
            await _handle_list_subscriptions(websocket, connection)


async def _handle_subscribe(
    websocket: WebSocket,
    connection: WebSocketConnection,
    message: SubscribeMessage,
    subscription_registry: SubscriptionRegistry,
    fanout: KafkaFanout,
    visibility_filter: VisibilityFilter,
) -> None:
    key = subscription_key(message.channel, message.resource_id)
    if key in connection.subscriptions:
        error = SubscriptionErrorMessage(
            channel=message.channel.value,
            resource_id=message.resource_id,
            error="Subscription already exists",
            code="already_subscribed",
        )
        await websocket.send_text(error.model_dump_json())
        return

    try:
        await visibility_filter.authorize_subscription(
            connection,
            message.channel,
            message.resource_id,
        )
    except (SubscriptionAuthError, ProtocolViolationError) as exc:
        error = SubscriptionErrorMessage(
            channel=message.channel.value,
            resource_id=message.resource_id,
            error=exc.message,
            code=exc.code,
        )
        await websocket.send_text(error.model_dump_json())
        return

    subscription = Subscription(channel=message.channel, resource_id=message.resource_id)
    connection.pending_subscriptions.add(key)
    connection.subscriptions[key] = subscription
    try:
        topics = subscription_registry.subscribe(connection.connection_id, subscription)
        if message.channel in WORKSPACE_SCOPED_CHANNELS:
            topics = list({*topics, "workspaces.events"})
        await fanout.ensure_consuming(topics)

        confirmed = SubscriptionConfirmedMessage(
            channel=message.channel.value,
            resource_id=message.resource_id,
            subscribed_at=subscription.subscribed_at,
        )
        await websocket.send_text(confirmed.model_dump_json())
        await _send_subscription_snapshot(websocket, message)
    finally:
        connection.pending_subscriptions.discard(key)


async def _send_subscription_snapshot(websocket: WebSocket, message: SubscribeMessage) -> None:
    if message.channel not in {ChannelType.EXECUTION, ChannelType.REASONING}:
        return
    try:
        execution_id = UUID(message.resource_id)
    except ValueError:
        return

    if await _send_e2e_contract_subscription_snapshot(websocket, message):
        return

    try:
        async with database.AsyncSessionLocal() as session:
            repository = ExecutionRepository(session)
            execution = await repository.get_execution_by_id(execution_id)
            if execution is None:
                return

            if message.channel == ChannelType.EXECUTION:
                event_type = "execution.status_changed"
                payload = {
                    "execution_id": str(execution.id),
                    "status": _enum_value(execution.status),
                    "snapshot": True,
                }
            else:
                trace = await repository.get_reasoning_trace_record(execution_id, None)
                if trace is None:
                    return
                event_type = "reasoning.trace_emitted"
                payload = {
                    "execution_id": str(execution.id),
                    "step_id": trace.step_id,
                    "technique": trace.technique,
                    "status": trace.status,
                    "storage_key": trace.storage_key,
                    "snapshot": True,
                }

            envelope = make_envelope(
                event_type=event_type,
                source="platform.ws_hub.snapshot",
                payload=payload,
                correlation_context=CorrelationContext(
                    workspace_id=execution.workspace_id,
                    conversation_id=execution.correlation_conversation_id,
                    interaction_id=execution.correlation_interaction_id,
                    execution_id=execution.id,
                    fleet_id=execution.correlation_fleet_id,
                    goal_id=execution.correlation_goal_id,
                    correlation_id=uuid4(),
                ),
            )
            snapshot = EventMessage(
                channel=message.channel.value,
                resource_id=message.resource_id,
                payload=envelope.model_dump(mode="json"),
                gateway_received_at=datetime.now(UTC),
            )
            await websocket.send_text(snapshot.model_dump_json())
    except Exception:
        LOGGER.warning(
            "ws-hub failed to send subscription snapshot",
            exc_info=True,
            extra={"channel": message.channel.value, "resource_id": message.resource_id},
        )


async def _send_e2e_contract_subscription_snapshot(
    websocket: WebSocket, message: SubscribeMessage
) -> bool:
    state = getattr(websocket.app.state, "e2e_contract_state", None)
    if not isinstance(state, dict):
        return False
    executions = state.get("executions")
    if not isinstance(executions, dict):
        return False
    execution = executions.get(message.resource_id)
    if not isinstance(execution, dict):
        return False

    if message.channel == ChannelType.EXECUTION:
        event_type = "execution.status_changed"
        payload = {
            "execution_id": str(execution["id"]),
            "status": execution.get("status", "completed"),
            "snapshot": True,
        }
    else:
        event_type = "reasoning.trace_emitted"
        payload = {
            "execution_id": str(execution["id"]),
            "step_id": "run_agent",
            "technique": "workflow",
            "status": "completed",
            "snapshot": True,
        }

    envelope = make_envelope(
        event_type=event_type,
        source="platform.ws_hub.e2e_contract_snapshot",
        payload=payload,
        correlation_context=CorrelationContext(
            workspace_id=_optional_uuid(execution.get("workspace_id")),
            conversation_id=_optional_uuid(execution.get("correlation_conversation_id")),
            interaction_id=_optional_uuid(execution.get("correlation_interaction_id")),
            execution_id=_optional_uuid(execution.get("id")),
            fleet_id=_optional_uuid(execution.get("correlation_fleet_id")),
            goal_id=_optional_uuid(execution.get("correlation_goal_id")),
            correlation_id=uuid4(),
        ),
    )
    snapshot = EventMessage(
        channel=message.channel.value,
        resource_id=message.resource_id,
        payload=envelope.model_dump(mode="json"),
        gateway_received_at=datetime.now(UTC),
    )
    await websocket.send_text(snapshot.model_dump_json())
    return True


def _optional_uuid(value: Any) -> UUID | None:
    if value in {None, ""}:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


async def _handle_unsubscribe(
    websocket: WebSocket,
    connection: WebSocketConnection,
    message: UnsubscribeMessage,
    subscription_registry: SubscriptionRegistry,
    fanout: KafkaFanout,
) -> None:
    key = subscription_key(message.channel, message.resource_id)
    subscription = connection.subscriptions.get(key)
    if subscription is None:
        removed = SubscriptionRemovedMessage(
            channel=message.channel.value,
            resource_id=message.resource_id,
        )
        await websocket.send_text(removed.model_dump_json())
        return
    if subscription.auto:
        error = SubscriptionErrorMessage(
            channel=message.channel.value,
            resource_id=message.resource_id,
            error="Auto-managed subscriptions cannot be removed explicitly",
            code="cannot_unsubscribe_auto",
        )
        await websocket.send_text(error.model_dump_json())
        return

    del connection.subscriptions[key]
    connection.pending_subscriptions.discard(key)
    topics = subscription_registry.unsubscribe(connection.connection_id, key)
    if (
        message.channel in WORKSPACE_SCOPED_CHANNELS
        and not subscription_registry.has_workspace_scoped_subscriptions()
    ):
        topics = list({*topics, "workspaces.events"})
    await fanout.release_topics(topics)

    removed = SubscriptionRemovedMessage(
        channel=message.channel.value,
        resource_id=message.resource_id,
    )
    await websocket.send_text(removed.model_dump_json())


async def _handle_list_subscriptions(websocket: WebSocket, connection: WebSocketConnection) -> None:
    subscriptions = [
        SubscriptionInfo(
            channel=item.channel.value,
            resource_id=item.resource_id,
            subscribed_at=item.subscribed_at,
            auto=item.auto,
        )
        for item in sorted(
            connection.subscriptions.values(),
            key=lambda subscription: (
                subscription.subscribed_at,
                subscription.channel.value,
                subscription.resource_id,
            ),
        )
    ]
    message = SubscriptionListMessage(subscriptions=subscriptions)
    await websocket.send_text(message.model_dump_json())


async def _auto_subscribe_attention(
    connection: WebSocketConnection,
    subscription_registry: SubscriptionRegistry,
    fanout: KafkaFanout,
) -> list[SubscriptionInfo]:
    subscription = Subscription(
        channel=ChannelType.ATTENTION,
        resource_id=str(connection.user_id),
        auto=True,
    )
    key = subscription_key(subscription.channel, subscription.resource_id)
    connection.subscriptions[key] = subscription
    topics = subscription_registry.subscribe(connection.connection_id, subscription)
    await fanout.ensure_consuming(topics)
    return [
        SubscriptionInfo(
            channel=subscription.channel.value,
            resource_id=subscription.resource_id,
            subscribed_at=subscription.subscribed_at,
            auto=subscription.auto,
        )
    ]


async def _auto_subscribe_alerts(
    connection: WebSocketConnection,
    subscription_registry: SubscriptionRegistry,
    fanout: KafkaFanout,
) -> list[SubscriptionInfo]:
    subscription = Subscription(
        channel=ChannelType.ALERTS,
        resource_id=str(connection.user_id),
        auto=True,
    )
    key = subscription_key(subscription.channel, subscription.resource_id)
    connection.subscriptions[key] = subscription
    topics = subscription_registry.subscribe(connection.connection_id, subscription)
    await fanout.ensure_consuming(topics)
    return [
        SubscriptionInfo(
            channel=subscription.channel.value,
            resource_id=subscription.resource_id,
            subscribed_at=subscription.subscribed_at,
            auto=subscription.auto,
        )
    ]


async def _auto_subscribe_user_channels(
    connection: WebSocketConnection,
    subscription_registry: SubscriptionRegistry,
    fanout: KafkaFanout,
) -> list[SubscriptionInfo]:
    attention = await _auto_subscribe_attention(connection, subscription_registry, fanout)
    alerts = await _auto_subscribe_alerts(connection, subscription_registry, fanout)
    return [*attention, *alerts]


async def _handle_validation_error(
    websocket: WebSocket,
    connection: WebSocketConnection,
    payload: dict[str, object],
    exc: ValidationError,
) -> None:
    message_type = payload.get("type")
    if message_type in {"subscribe", "unsubscribe"}:
        channel = str(payload.get("channel", ""))
        resource_id = str(payload.get("resource_id", ""))
        code = "protocol_violation"
        error = "Malformed subscription message"
        for issue in exc.errors():
            field_path = issue.get("loc", ())
            if "channel" in field_path:
                code = "invalid_channel"
                error = "Invalid channel"
                break
            if "resource_id" in field_path:
                code = "invalid_resource_id"
                error = "Invalid resource_id"
                break
        response = SubscriptionErrorMessage(
            channel=channel,
            resource_id=resource_id,
            error=error,
            code=code,
        )
        await websocket.send_text(response.model_dump_json())
        if code == "protocol_violation":
            connection.malformed_message_count += 1
    else:
        await _handle_protocol_error(
            websocket,
            connection,
            ErrorMessage(error="Malformed message", code="protocol_violation"),
        )

    if connection.malformed_message_count >= websocket.app.state.settings.WS_MAX_MALFORMED_MESSAGES:
        connection.closed.set()
        await websocket.close(code=4400, reason="protocol-violation-threshold")


async def _handle_protocol_error(
    websocket: WebSocket,
    connection: WebSocketConnection,
    response: ErrorMessage,
) -> None:
    connection.malformed_message_count += 1
    await websocket.send_text(response.model_dump_json())
    if connection.malformed_message_count >= websocket.app.state.settings.WS_MAX_MALFORMED_MESSAGES:
        connection.closed.set()
        await websocket.close(code=4400, reason="protocol-violation-threshold")


async def _cleanup_connection(
    connection: WebSocketConnection,
    connection_registry: ConnectionRegistry,
    subscription_registry: SubscriptionRegistry,
    fanout: KafkaFanout,
) -> None:
    had_workspace_scoped_subscriptions = any(
        subscription.channel in WORKSPACE_SCOPED_CHANNELS
        for subscription in connection.subscriptions.values()
    )

    if connection.closed.is_set():
        pass
    else:
        connection.closed.set()

    removed = connection_registry.remove(connection.connection_id)
    released_topics = subscription_registry.unsubscribe_all(connection.connection_id)
    if (
        removed is not None
        and had_workspace_scoped_subscriptions
        and not subscription_registry.has_workspace_scoped_subscriptions()
    ):
        released_topics = list({*released_topics, "workspaces.events"})
    if connection_registry.count() == 0:
        released_topics = list({*released_topics, "auth.events"})
    await fanout.release_topics(released_topics)
    ROUTER_METRICS.connection_closed()

    for task in list(connection.tasks):
        task.cancel()
    for task in list(connection.tasks):
        with suppress(asyncio.CancelledError):
            await task


def _extract_token(websocket: WebSocket) -> str | None:
    header = websocket.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header.removeprefix("Bearer ").strip()
        return token or None
    query_token = websocket.query_params.get("token")
    return query_token.strip() if query_token else None


async def _validate_token(websocket: WebSocket, token: str) -> dict[str, object]:
    async with websocket.app.state.auth_service_factory() as auth_service:
        try:
            return dict(await auth_service.validate_token(token))
        except Exception as exc:
            status_code = getattr(exc, "status_code", 401)
            message = getattr(exc, "message", "Invalid authentication token")
            raise _ConnectionDeniedError(status_code, message) from exc


async def _load_workspace_ids(websocket: WebSocket, user_id: UUID) -> list[UUID]:
    async with websocket.app.state.workspaces_service_factory() as workspaces_service:
        return list(await workspaces_service.get_user_workspace_ids(user_id))


async def _deny(websocket: WebSocket, status_code: int, message: str) -> None:
    await websocket.send_denial_response(
        JSONResponse(
            status_code=status_code,
            content={"error": {"code": "websocket_denied", "message": message}},
        )
    )


class _ConnectionDeniedError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
