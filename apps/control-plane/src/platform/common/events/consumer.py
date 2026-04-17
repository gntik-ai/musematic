from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from platform.common.events.envelope import EventEnvelope
from platform.common.exceptions import KafkaConsumerError
from platform.common.kafka_tracing import extract_trace_context
from platform.common.tracing import trace
from typing import Any

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventConsumerManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self._subscriptions: list[tuple[str, str, EventHandler]] = []
        self._consumers: list[Any] = []
        self._tasks: list[asyncio.Task[None]] = []

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> EventConsumerManager:
        return cls(settings)

    def subscribe(self, topic: str, group_id: str, handler: EventHandler) -> None:
        self._subscriptions.append((topic, group_id, handler))

    async def start(self) -> None:
        if self._tasks:
            return
        aiokafka = import_module("aiokafka")
        consumer_cls = aiokafka.AIOKafkaConsumer
        for topic, group_id, handler in self._subscriptions:
            consumer = consumer_cls(
                topic,
                bootstrap_servers=self.settings.KAFKA_BROKERS,
                group_id=group_id,
                enable_auto_commit=False,
                auto_offset_reset="earliest",
            )
            await consumer.start()
            self._consumers.append(consumer)
            self._tasks.append(asyncio.create_task(self._consume(consumer, handler)))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        for consumer in self._consumers:
            await consumer.stop()
        self._consumers.clear()

    async def _consume(self, consumer: Any, handler: EventHandler) -> None:
        try:
            context_module = import_module("opentelemetry.context")
        except Exception:
            context_module = None
        tracer = trace.get_tracer(__name__)
        try:
            async for message in consumer:
                envelope = EventEnvelope.model_validate_json(message.value)
                message_headers = dict(message.headers or [])
                extracted_context = extract_trace_context(message_headers)
                topic = getattr(message, "topic", "events")
                with _attached_context(context_module, extracted_context):
                    with tracer.start_as_current_span(f"kafka.consume.{topic}"):
                        await handler(envelope)
                commit = getattr(consumer, "commit", None)
                if commit is not None:
                    result = commit()
                    if hasattr(result, "__await__"):
                        await result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise KafkaConsumerError(str(exc)) from exc


AsyncKafkaConsumer = EventConsumerManager


@contextmanager
def _attached_context(context_module: Any | None, extracted_context: Any) -> Iterator[None]:
    if context_module is None:
        yield
        return
    token = context_module.attach(extracted_context)
    try:
        yield
    finally:
        context_module.detach(token)
