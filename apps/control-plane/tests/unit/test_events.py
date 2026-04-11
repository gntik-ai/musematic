from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import BaseModel

from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.common.events.envelope import make_envelope
from platform.common.events.producer import EventProducer
from platform.common.events.registry import EventTypeRegistry, event_registry
from platform.common.events.retry import RetryHandler
from platform.common.exceptions import ValidationError


class PayloadModel(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_event_envelope_roundtrip_and_registry_validation() -> None:
    registry = EventTypeRegistry()
    registry.register("test.event", PayloadModel)
    payload = registry.validate("test.event", {"value": 3})
    envelope = EventEnvelope(
        event_type="test.event",
        source="tests",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload=payload.model_dump(),
    )

    hydrated = EventEnvelope.model_validate_json(envelope.model_dump_json())

    assert hydrated.event_type == "test.event"
    assert hydrated.payload["value"] == 3
    assert registry.is_registered("test.event") is True


def test_make_envelope_supplies_default_correlation_context() -> None:
    envelope = make_envelope("test.event", "tests", {"value": 1})

    assert envelope.source == "tests"
    assert envelope.correlation_context.correlation_id is not None


def test_registry_rejects_unknown_event_type() -> None:
    registry = EventTypeRegistry()

    with pytest.raises(ValidationError):
        registry.validate("missing.event", {"value": 1})


@pytest.mark.asyncio
async def test_event_producer_validates_and_publishes(monkeypatch) -> None:
    sent: list[tuple[str, bytes, bytes]] = []

    class FakeKafkaProducer:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def send_and_wait(self, topic: str, value: bytes, key: bytes) -> None:
            sent.append((topic, value, key))

    monkeypatch.setattr(
        "platform.common.events.producer.import_module",
        lambda name: SimpleNamespace(AIOKafkaProducer=FakeKafkaProducer),
    )
    event_registry._schemas.clear()
    event_registry.register("test.event", PayloadModel)

    producer = EventProducer(PlatformSettings(KAFKA_BROKERS="kafka:9092"))
    await producer.publish(
        topic="events",
        key="1",
        event_type="test.event",
        payload={"value": 7},
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        source="tests",
    )

    assert sent[0][0] == "events"
    assert sent[0][2] == b"1"


@pytest.mark.asyncio
async def test_event_consumer_manager_dispatches_messages(monkeypatch) -> None:
    received: list[EventEnvelope] = []

    envelope = EventEnvelope(
        event_type="test.event",
        source="tests",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={"value": 1},
    )

    class FakeMessage:
        def __init__(self) -> None:
            self.value = envelope.model_dump_json().encode("utf-8")

    class FakeConsumer:
        def __init__(self, *topics, **kwargs) -> None:
            self.messages = [FakeMessage()]

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def commit(self) -> None:
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.messages:
                raise StopAsyncIteration
            return self.messages.pop(0)

    monkeypatch.setattr(
        "platform.common.events.consumer.import_module",
        lambda name: SimpleNamespace(AIOKafkaConsumer=FakeConsumer),
    )
    manager = EventConsumerManager(PlatformSettings(KAFKA_BROKERS="kafka:9092"))
    manager.subscribe("events", "group-1", lambda item: _append(received, item))
    await manager.start()
    await asyncio.sleep(0)
    await manager.stop()

    assert received[0].event_type == "test.event"


@pytest.mark.asyncio
async def test_retry_handler_routes_to_dlq_after_retries(monkeypatch) -> None:
    published: list[dict[str, str]] = []

    class FakeProducer:
        async def publish(self, topic, key, event_type, payload, correlation_ctx, source) -> None:
            published.append({"topic": topic, "event_type": event_type, "source": source, "key": key, "payload": payload})

    async def failing_handler(envelope: EventEnvelope) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("platform.common.events.retry.asyncio.sleep", lambda seconds: _async_noop())

    handler = RetryHandler(FakeProducer())  # type: ignore[arg-type]
    await handler.handle(
        "events",
        EventEnvelope(
            event_type="test.event",
            source="tests",
            correlation_context=CorrelationContext(correlation_id=uuid4()),
            payload={"value": 1},
        ),
        failing_handler,
    )

    assert published[0]["topic"] == "events.dlq"
    assert published[0]["payload"]["attempt_count"] == 3


async def _append(received: list[EventEnvelope], item: EventEnvelope) -> None:
    received.append(item)


async def _async_noop() -> None:
    return None
