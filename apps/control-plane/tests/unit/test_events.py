from __future__ import annotations

import asyncio
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import CorrelationContext, EventEnvelope, make_envelope
from platform.common.events.producer import EventProducer
from platform.common.events.registry import EventTypeRegistry, event_registry
from platform.common.events.retry import RetryHandler
from platform.common.exceptions import ValidationError
from platform.common.kafka_tracing import extract_trace_context, inject_trace_context
from types import SimpleNamespace
from uuid import uuid4

import opentelemetry.context as otel_context
import opentelemetry.trace as trace
import pytest
from pydantic import BaseModel


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
    sent: list[tuple[str, bytes, bytes, list[tuple[str, bytes]]]] = []

    class FakeKafkaProducer:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def send_and_wait(
            self,
            topic: str,
            value: bytes,
            key: bytes,
            headers: list[tuple[str, bytes]],
        ) -> None:
            sent.append((topic, value, key, headers))

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
    assert isinstance(sent[0][3], list)


@pytest.mark.asyncio
async def test_event_producer_injects_trace_headers(monkeypatch) -> None:
    sent: list[list[tuple[str, bytes]]] = []

    class FakeKafkaProducer:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def send_and_wait(
            self,
            topic: str,
            value: bytes,
            key: bytes,
            headers: list[tuple[str, bytes]],
        ) -> None:
            sent.append(headers)

    monkeypatch.setattr(
        "platform.common.events.producer.import_module",
        lambda name: SimpleNamespace(AIOKafkaProducer=lambda **kwargs: FakeKafkaProducer()),
    )
    event_registry._schemas.clear()
    event_registry.register("test.event", PayloadModel)

    span_context = trace.SpanContext(
        trace_id=0x1234567890ABCDEF1234567890ABCDEF,
        span_id=0x1234567890ABCDEF,
        is_remote=False,
        trace_flags=trace.TraceFlags(0x01),
        trace_state=trace.TraceState(),
    )
    token = otel_context.attach(trace.set_span_in_context(trace.NonRecordingSpan(span_context)))
    try:
        producer = EventProducer(PlatformSettings(KAFKA_BROKERS="kafka:9092"))
        await producer.publish(
            topic="events",
            key="1",
            event_type="test.event",
            payload={"value": 7},
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
            source="tests",
        )
    finally:
        otel_context.detach(token)

    assert dict(sent[0])["traceparent"]


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
            self.headers = []
            self.topic = "events"

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
        lambda name: (
            SimpleNamespace(AIOKafkaConsumer=FakeConsumer) if name == "aiokafka" else otel_context
        ),
    )
    manager = EventConsumerManager(PlatformSettings(KAFKA_BROKERS="kafka:9092"))
    manager.subscribe("events", "group-1", lambda item: _append(received, item))
    await manager.start()
    await asyncio.sleep(0)
    await manager.stop()

    assert received[0].event_type == "test.event"


@pytest.mark.asyncio
async def test_event_consumer_manager_extracts_trace_context(monkeypatch) -> None:
    received: list[EventEnvelope] = []
    observed_trace_ids: list[int] = []

    envelope = EventEnvelope(
        event_type="test.event",
        source="tests",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={"value": 1},
    )
    span_context = trace.SpanContext(
        trace_id=0xABCDEF1234567890ABCDEF1234567890,
        span_id=0x1234567890ABCDEF,
        is_remote=False,
        trace_flags=trace.TraceFlags(0x01),
        trace_state=trace.TraceState(),
    )
    token = otel_context.attach(trace.set_span_in_context(trace.NonRecordingSpan(span_context)))
    try:
        headers = inject_trace_context({})
    finally:
        otel_context.detach(token)

    class FakeMessage:
        def __init__(self) -> None:
            self.value = envelope.model_dump_json().encode("utf-8")
            self.headers = list(headers.items())
            self.topic = "events"

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

    def fake_import(name: str):
        if name == "aiokafka":
            return SimpleNamespace(AIOKafkaConsumer=FakeConsumer)
        if name == "opentelemetry.context":
            return otel_context
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr("platform.common.events.consumer.import_module", fake_import)
    monkeypatch.setattr(
        "platform.common.events.consumer.trace",
        SimpleNamespace(get_tracer=lambda _name: _FakeTracer()),
    )

    manager = EventConsumerManager(PlatformSettings(KAFKA_BROKERS="kafka:9092"))
    manager.subscribe(
        "events",
        "group-1",
        lambda item: _append_with_trace(received, observed_trace_ids, item),
    )
    await manager.start()
    await asyncio.sleep(0)
    await manager.stop()

    assert received[0].event_type == "test.event"
    assert observed_trace_ids[0] == span_context.trace_id


def test_extract_trace_context_without_headers_returns_context() -> None:
    extracted = extract_trace_context({})

    assert extracted is not None


def test_inject_and_extract_trace_context_roundtrip() -> None:
    span_context = trace.SpanContext(
        trace_id=0x11111111111111111111111111111111,
        span_id=0x2222222222222222,
        is_remote=False,
        trace_flags=trace.TraceFlags(0x01),
        trace_state=trace.TraceState(),
    )
    token = otel_context.attach(trace.set_span_in_context(trace.NonRecordingSpan(span_context)))
    try:
        headers = inject_trace_context({})
    finally:
        otel_context.detach(token)

    extracted = extract_trace_context(headers)
    child_context = trace.get_current_span(extracted).get_span_context()

    assert headers["traceparent"]
    assert child_context.trace_id == span_context.trace_id


@pytest.mark.asyncio
async def test_retry_handler_routes_to_dlq_after_retries(monkeypatch) -> None:
    published: list[dict[str, str]] = []

    class FakeProducer:
        async def publish(self, topic, key, event_type, payload, correlation_ctx, source) -> None:
            published.append(
                {
                    "topic": topic,
                    "event_type": event_type,
                    "source": source,
                    "key": key,
                    "payload": payload,
                }
            )

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


async def _append_with_trace(
    received: list[EventEnvelope],
    observed_trace_ids: list[int],
    item: EventEnvelope,
) -> None:
    assert trace is not None
    received.append(item)
    current_span = trace.get_current_span()
    observed_trace_ids.append(current_span.get_span_context().trace_id)


async def _async_noop() -> None:
    return None


class _TestSpanContextManager:
    def __init__(self, trace_id: int) -> None:
        assert trace is not None
        assert otel_context is not None
        self._span = trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=trace_id,
                span_id=0x0FEDCBA987654321,
                is_remote=False,
                trace_flags=trace.TraceFlags(0x01),
                trace_state=trace.TraceState(),
            )
        )
        self._token = None

    def __enter__(self) -> object:
        assert trace is not None
        assert otel_context is not None
        self._token = otel_context.attach(trace.set_span_in_context(self._span))
        return self._span

    def __exit__(self, exc_type, exc, tb) -> None:
        assert otel_context is not None
        assert self._token is not None
        otel_context.detach(self._token)


class _FakeTracer:
    def start_as_current_span(self, _name: str) -> _TestSpanContextManager:
        assert trace is not None
        current_trace_id = trace.get_current_span().get_span_context().trace_id
        return _TestSpanContextManager(current_trace_id)
