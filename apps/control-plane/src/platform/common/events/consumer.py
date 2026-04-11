from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from platform.common.events.envelope import EventEnvelope
from platform.common.exceptions import KafkaConsumerError
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
            async for message in consumer:
                envelope = EventEnvelope.model_validate_json(message.value)
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
