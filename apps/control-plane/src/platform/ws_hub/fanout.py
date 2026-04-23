from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
from datetime import UTC, datetime
from importlib import import_module
from platform.common.events.envelope import EventEnvelope, parse_event_envelope
from platform.ws_hub.schemas import EventMessage
from platform.ws_hub.subscription import ChannelType, SubscriptionRegistry, subscription_key
from platform.ws_hub.visibility import VisibilityFilter
from typing import Any, Protocol
from uuid import UUID

LOGGER = logging.getLogger(__name__)


class _ConnectionRegistry(Protocol):
    def get(self, connection_id: str) -> Any | None: ...

    def get_by_user_id(self, user_id: UUID) -> list[Any]: ...


class _FanoutMetrics:
    def __init__(self) -> None:
        self._events_delivered = None
        self._events_dropped = None
        self._delivery_latency = None
        try:
            metrics_module = import_module("opentelemetry.metrics")
            meter = metrics_module.get_meter(__name__)
            self._events_delivered = meter.create_counter(
                "ws_hub.events.delivered",
                description="Events delivered from Kafka into client queues.",
                unit="{event}",
            )
            self._events_dropped = meter.create_counter(
                "ws_hub.events.dropped",
                description="Events dropped because a client queue was full.",
                unit="{event}",
            )
            self._delivery_latency = meter.create_histogram(
                "ws_hub.event_delivery_latency",
                description="Latency from Kafka event production to ws-hub queue delivery.",
                unit="ms",
            )
        except Exception:
            self._events_delivered = None
            self._events_dropped = None
            self._delivery_latency = None

    def delivered(self) -> None:
        if self._events_delivered is not None:
            self._events_delivered.add(1)

    def dropped(self) -> None:
        if self._events_dropped is not None:
            self._events_dropped.add(1)

    def observe_latency(self, envelope: dict[str, Any]) -> None:
        if self._delivery_latency is None:
            return

        raw_occurred_at = envelope.get("occurred_at")
        produced_at: datetime | None = None
        if isinstance(raw_occurred_at, datetime):
            produced_at = raw_occurred_at
        elif isinstance(raw_occurred_at, str):
            with contextlib.suppress(ValueError):
                produced_at = datetime.fromisoformat(raw_occurred_at.replace("Z", "+00:00"))
        if produced_at is None:
            return
        latency_ms = max((datetime.now(UTC) - produced_at).total_seconds() * 1000, 0.0)
        self._delivery_latency.record(latency_ms)


class KafkaFanout:
    def __init__(
        self,
        connection_registry: _ConnectionRegistry,
        subscription_registry: SubscriptionRegistry,
        settings: Any,
        visibility_filter: VisibilityFilter,
    ) -> None:
        self.connection_registry = connection_registry
        self.subscription_registry = subscription_registry
        self.settings = settings
        self.visibility_filter = visibility_filter
        self._consumers: dict[str, Any] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._started = False
        self._lock = asyncio.Lock()
        self._consumer_group_id = f"ws-hub-{socket.gethostname()}-{os.getpid()}"
        self._metrics = _FanoutMetrics()

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._tasks.clear()

            consumers = list(self._consumers.values())
            for consumer in consumers:
                stop = getattr(consumer, "stop", None)
                if callable(stop):
                    result = stop()
                    if hasattr(result, "__await__"):
                        await result
            self._consumers.clear()
            self._started = False

    async def ensure_consuming(self, topics: list[str]) -> None:
        if not self._started:
            return

        async with self._lock:
            aiokafka = import_module("aiokafka")
            consumer_cls = aiokafka.AIOKafkaConsumer
            for topic in topics:
                if topic in self._consumers:
                    continue
                consumer = consumer_cls(
                    topic,
                    bootstrap_servers=self.settings.KAFKA_BROKERS,
                    group_id=self._group_id_for_topic(topic),
                    enable_auto_commit=False,
                    auto_offset_reset="latest",
                )
                await consumer.start()
                self._consumers[topic] = consumer
                self._tasks[topic] = asyncio.create_task(self._consumer_loop(topic, consumer))

    async def release_topics(self, topics: list[str]) -> None:
        async with self._lock:
            for topic in topics:
                task = self._tasks.pop(topic, None)
                if task is not None:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                consumer = self._consumers.pop(topic, None)
                if consumer is None:
                    continue
                stop = getattr(consumer, "stop", None)
                if callable(stop):
                    result = stop()
                    if hasattr(result, "__await__"):
                        await result

    async def _consumer_loop(self, topic: str, consumer: Any) -> None:
        try:
            async for message in consumer:
                try:
                    await self._route_event(topic, message.value)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    LOGGER.exception("ws-hub failed to route Kafka event", extra={"topic": topic})
                commit = getattr(consumer, "commit", None)
                if callable(commit):
                    result = commit()
                    if hasattr(result, "__await__"):
                        await result
        except asyncio.CancelledError:
            raise

    async def _route_event(self, topic: str, raw_message: Any) -> None:
        envelope = self._load_envelope(raw_message)
        envelope_dict = envelope.model_dump(mode="json")
        await self._handle_control_event(topic, envelope_dict)

        for channel, resource_id in self._match_subscriptions(topic, envelope_dict):
            subscriber_ids = self.subscription_registry.get_subscribers(channel, resource_id)
            if not subscriber_ids:
                continue
            event_message = EventMessage(
                channel=channel.value,
                resource_id=resource_id,
                payload=envelope_dict,
                gateway_received_at=datetime.now(UTC),
            )
            for subscriber_id in subscriber_ids:
                conn = self.connection_registry.get(subscriber_id)
                if conn is None or conn.closed.is_set():
                    continue
                if not await self._wait_for_subscription_confirmation(conn, channel, resource_id):
                    continue
                if not self.visibility_filter.is_visible(envelope_dict, conn):
                    continue
                dropped = self._enqueue(conn, event_message)
                self._metrics.delivered()
                self._metrics.observe_latency(envelope_dict)
                if dropped:
                    self._metrics.dropped()

    async def _handle_control_event(self, topic: str, envelope: dict[str, Any]) -> None:
        if topic == "auth.events" and envelope.get("event_type") in {
            "auth.session.invalidated",
            "auth.session.revoked",
        }:
            raw_user_id = envelope.get("payload", {}).get("user_id")
            if raw_user_id is None:
                return
            try:
                user_id = UUID(str(raw_user_id))
            except ValueError:
                return
            for conn in self.connection_registry.get_by_user_id(user_id):
                if conn.closed.is_set():
                    continue
                conn.closed.set()
                try:
                    await conn.websocket.close(code=4401, reason="session-invalidated")
                except Exception:
                    continue

        if topic == "workspaces.events" and envelope.get("event_type") in {
            "workspaces.membership.added",
            "workspaces.membership.removed",
            "workspaces.membership.role_changed",
        }:
            raw_user_id = envelope.get("payload", {}).get("user_id")
            if raw_user_id is None:
                return
            try:
                user_id = UUID(str(raw_user_id))
            except ValueError:
                return
            for conn in self.connection_registry.get_by_user_id(user_id):
                await self.visibility_filter.refresh_connection_memberships(conn)

    def _match_subscriptions(
        self,
        topic: str,
        envelope: dict[str, Any],
    ) -> list[tuple[ChannelType, str]]:
        correlation = envelope.get("correlation_context") or envelope.get("correlation") or {}
        payload = envelope.get("payload", {})
        matches: list[tuple[ChannelType, str]] = []

        if topic == "execution.events":
            if execution_id := self._as_resource_id(correlation.get("execution_id")):
                matches.append((ChannelType.EXECUTION, execution_id))
        elif topic == "workflow.runtime":
            if execution_id := self._as_resource_id(correlation.get("execution_id")):
                matches.append((ChannelType.EXECUTION, execution_id))
        elif topic == "runtime.lifecycle":
            if execution_id := self._as_resource_id(correlation.get("execution_id")):
                matches.append((ChannelType.EXECUTION, execution_id))
            if fleet_id := self._as_resource_id(correlation.get("fleet_id")):
                matches.append((ChannelType.FLEET, fleet_id))
        elif topic == "interaction.events":
            if interaction_id := self._as_resource_id(correlation.get("interaction_id")):
                matches.append((ChannelType.INTERACTION, interaction_id))
            if conversation_id := self._as_resource_id(correlation.get("conversation_id")):
                matches.append((ChannelType.CONVERSATION, conversation_id))
        elif topic == "workspaces.events":
            if workspace_id := self._as_resource_id(correlation.get("workspace_id")):
                matches.append((ChannelType.WORKSPACE, workspace_id))
            if workspace_id := self._as_resource_id(payload.get("workspace_id")):
                matches.append((ChannelType.WORKSPACE, workspace_id))
        elif topic == "runtime.reasoning":
            if execution_id := self._as_resource_id(correlation.get("execution_id")):
                matches.append((ChannelType.REASONING, execution_id))
        elif topic == "runtime.selfcorrection":
            if execution_id := self._as_resource_id(correlation.get("execution_id")):
                matches.append((ChannelType.CORRECTION, execution_id))
        elif topic == "simulation.events":
            if simulation_id := self._as_resource_id(payload.get("simulation_id")):
                matches.append((ChannelType.SIMULATION, simulation_id))
        elif topic == "testing.results":
            if suite_id := self._as_resource_id(payload.get("suite_id")):
                matches.append((ChannelType.TESTING, suite_id))
        elif topic == "monitor.alerts":
            if target_id := self._as_resource_id(payload.get("target_id")):
                matches.append((ChannelType.ALERTS, target_id))
        elif topic == "notifications.alerts":
            if user_id := self._as_resource_id(payload.get("user_id")):
                matches.append((ChannelType.ALERTS, user_id))
        elif topic == "interaction.attention":
            target_resource = payload.get("target_id") or payload.get("target_identity")
            if target_id := self._as_resource_id(target_resource):
                matches.append((ChannelType.ATTENTION, target_id))

        return matches

    async def _wait_for_subscription_confirmation(
        self,
        conn: Any,
        channel: ChannelType,
        resource_id: str,
    ) -> bool:
        key = subscription_key(channel, resource_id)
        if key not in getattr(conn, "pending_subscriptions", set()):
            return True

        for _ in range(100):
            if conn.closed.is_set():
                return False
            if key not in conn.pending_subscriptions:
                return True
            await asyncio.sleep(0.01)

        LOGGER.warning(
            "ws-hub timed out waiting for subscription confirmation before delivery",
            extra={
                "connection_id": getattr(conn, "connection_id", None),
                "channel": channel.value,
                "resource_id": resource_id,
            },
        )
        return key not in conn.pending_subscriptions

    def _enqueue(self, conn: Any, event_message: EventMessage) -> bool:
        try:
            conn.send_queue.put_nowait(event_message)
            return False
        except asyncio.QueueFull:
            pass

        try:
            conn.send_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        conn.dropped_count += 1
        conn.send_queue.put_nowait(event_message)
        return True

    def _group_id_for_topic(self, topic: str) -> str:
        safe_topic = topic.replace(".", "-").replace("_", "-")
        return f"{self._consumer_group_id}-{safe_topic}"

    @staticmethod
    def _load_envelope(raw_message: Any) -> EventEnvelope:
        return parse_event_envelope(raw_message)

    @staticmethod
    def _as_resource_id(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)
