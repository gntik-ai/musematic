from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from platform.analytics.consumer import AnalyticsPipelineConsumer
from platform.common.config import PlatformSettings
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.analytics_support import (
    AsyncSessionFactoryStub,
    ClickHouseClientStub,
    RetryHandlerStub,
    build_cost_model,
    build_envelope,
)
from tests.auth_support import RecordingProducer


def _consumer(*, producer: RecordingProducer | None = None) -> AnalyticsPipelineConsumer:
    return AnalyticsPipelineConsumer(
        settings=PlatformSettings(),
        clickhouse_client=ClickHouseClientStub(),  # type: ignore[arg-type]
        producer=producer,
    )


@pytest.mark.asyncio
async def test_buffer_event_routes_usage_and_quality(monkeypatch) -> None:
    consumer = _consumer()
    flushed: list[str] = []

    async def _fake_flush() -> None:
        flushed.append("flush")

    monkeypatch.setattr(consumer, "_flush_buffers", _fake_flush)
    for _ in range(100):
        await consumer._buffer_event(
            "workflow.runtime",
            build_envelope(
                workspace_id=uuid4(),
                payload={"agent_fqn": "planner:daily", "model_id": "gpt-4o"},
            ),
        )
    await consumer._buffer_event(
        "evaluation.events",
        build_envelope(
            workspace_id=uuid4(),
            execution_id=uuid4(),
            payload={
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "quality_score": 0.9,
            },
        ),
    )

    assert flushed == ["flush"]
    assert len(consumer._usage_buffer) == 100
    assert len(consumer._quality_buffer) == 1


@pytest.mark.asyncio
async def test_retry_batch_insert_retries_then_succeeds(monkeypatch) -> None:
    consumer = _consumer()
    attempts = {"count": 0}
    sleeps: list[int] = []

    async def _handler() -> None:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("retry")

    async def _fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("platform.analytics.consumer.asyncio.sleep", _fake_sleep)

    await consumer._retry_batch_insert(
        topic_hint="workflow.runtime",
        envelopes=[],
        handler=_handler,
    )

    assert attempts["count"] == 3
    assert sleeps == [1, 2]


@pytest.mark.asyncio
async def test_retry_batch_insert_routes_to_dlq_after_three_failures(monkeypatch) -> None:
    consumer = _consumer()
    routed: list[tuple[str, list[object]]] = []
    original_sleep = asyncio.sleep

    async def _fake_route(topic_hint: str, envelopes: list[object]) -> None:
        routed.append((topic_hint, envelopes))

    async def _always_fail() -> None:
        raise RuntimeError("boom")

    async def _fake_sleep(_: int) -> None:
        await original_sleep(0)

    monkeypatch.setattr("platform.analytics.consumer.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr(consumer, "_route_failed_batch_to_dlq", _fake_route)
    envelopes = [build_envelope(workspace_id=uuid4(), payload={"agent_fqn": "planner:daily"})]

    await consumer._retry_batch_insert(
        topic_hint="evaluation.events",
        envelopes=envelopes,
        handler=_always_fail,
    )

    assert routed == [("evaluation.events", envelopes)]


@pytest.mark.asyncio
async def test_route_failed_batch_to_dlq_uses_retry_handler() -> None:
    consumer = _consumer()
    retry_handler = RetryHandlerStub()
    consumer._retry_handler = retry_handler  # type: ignore[assignment]
    envelopes = [build_envelope(workspace_id=uuid4(), payload={"agent_fqn": "planner:daily"})]

    await consumer._route_failed_batch_to_dlq("workflow.runtime", envelopes)

    assert retry_handler.calls[0][0] == "workflow.runtime"
    assert retry_handler.calls[0][1] == envelopes[0]


@pytest.mark.asyncio
async def test_route_failed_batch_to_dlq_noop_without_retry_handler() -> None:
    consumer = _consumer()

    await consumer._route_failed_batch_to_dlq(
        "workflow.runtime",
        [build_envelope(workspace_id=uuid4(), payload={"agent_fqn": "planner:daily"})],
    )


@pytest.mark.asyncio
async def test_route_failed_batch_to_dlq_executes_failure_handler() -> None:
    consumer = _consumer()
    failures: list[str] = []

    class CallingRetryHandler:
        async def handle(self, topic: str, envelope, handler) -> None:  # type: ignore[no-untyped-def]
            del topic
            try:
                await handler(envelope)
            except RuntimeError as exc:
                failures.append(str(exc))

    consumer._retry_handler = CallingRetryHandler()  # type: ignore[assignment]

    await consumer._route_failed_batch_to_dlq(
        "workflow.runtime",
        [build_envelope(workspace_id=uuid4(), payload={"agent_fqn": "planner:daily"})],
    )

    assert failures == ["analytics-batch-failed"]


@pytest.mark.asyncio
async def test_refresh_cost_model_cache_filters_inactive_and_recent_entries(monkeypatch) -> None:
    consumer = _consumer()
    valid_model = build_cost_model(model_id="gpt-4o")
    expired_model = build_cost_model(
        model_id="expired",
        valid_until=datetime.now(UTC) - timedelta(days=1),
    )
    inactive_model = build_cost_model(model_id="inactive", is_active=False)

    class CostModelRepositoryStub:
        def __init__(self, session: object) -> None:
            self.session = session

        async def list_all(self) -> list[object]:
            return [valid_model, expired_model, inactive_model]

    monkeypatch.setattr(
        "platform.analytics.consumer.database.AsyncSessionLocal",
        AsyncSessionFactoryStub(object()),
    )
    monkeypatch.setattr(
        "platform.analytics.consumer.CostModelRepository",
        CostModelRepositoryStub,
    )

    await consumer._refresh_cost_model_cache(force=True)
    cached_at = consumer._pricing_cache_refreshed_at
    await consumer._refresh_cost_model_cache(force=False)

    assert consumer._pricing_cache == {"gpt-4o": valid_model}
    assert consumer._pricing_cache_refreshed_at == cached_at


@pytest.mark.asyncio
async def test_flush_buffers_writes_usage_and_quality_batches() -> None:
    consumer = _consumer()
    usage_envelope = build_envelope(
        workspace_id=uuid4(),
        payload={"agent_fqn": "planner:daily", "model_id": "gpt-4o"},
    )
    quality_envelope = build_envelope(
        workspace_id=uuid4(),
        execution_id=uuid4(),
        payload={
            "agent_fqn": "planner:daily",
            "model_id": "gpt-4o",
            "quality_score": 0.8,
        },
    )
    usage_row = {
        "event_id": uuid4(),
        "workspace_id": uuid4(),
    }
    quality_row = {
        "event_id": uuid4(),
        "workspace_id": uuid4(),
    }
    calls: list[tuple[str, list[object]]] = []

    async def _fake_retry_batch_insert(
        *,
        topic_hint: str,
        envelopes,
        handler,  # type: ignore[no-untyped-def]
    ) -> None:
        await handler()
        calls.append((topic_hint, list(envelopes)))

    consumer._usage_buffer = [("workflow.runtime", usage_envelope, usage_row)]
    consumer._quality_buffer = [("evaluation.events", quality_envelope, quality_row)]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(consumer, "_retry_batch_insert", _fake_retry_batch_insert)
    try:
        await consumer._flush_buffers()
    finally:
        monkeypatch.undo()

    assert calls[0][0] == "workflow.runtime"
    assert calls[1][0] == "evaluation.events"
    assert consumer._usage_buffer == []
    assert consumer._quality_buffer == []


@pytest.mark.asyncio
async def test_consume_and_flush_loops_process_messages(monkeypatch) -> None:
    consumer = _consumer()
    buffered: list[str] = []
    flushed: list[str] = []
    envelope = build_envelope(workspace_id=uuid4(), payload={"agent_fqn": "planner:daily"})

    class FakeKafkaConsumer:
        def __init__(self) -> None:
            self._messages = [
                SimpleNamespace(
                    topic="workflow.runtime",
                    value=envelope.model_dump_json().encode(),
                )
            ]
            self.committed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._messages:
                return self._messages.pop(0)
            raise StopAsyncIteration

        async def commit(self) -> None:
            self.committed = True

    async def _fake_buffer(topic: str, received_envelope) -> None:  # type: ignore[no-untyped-def]
        buffered.append(topic)
        assert received_envelope.event_type == envelope.event_type

    async def _fake_flush() -> None:
        flushed.append("flush")
        consumer._running = False

    async def _fake_sleep(_: int) -> None:
        return None

    consumer._consumer = FakeKafkaConsumer()
    consumer._running = True
    monkeypatch.setattr(consumer, "_buffer_event", _fake_buffer)
    monkeypatch.setattr(consumer, "_flush_buffers", _fake_flush)
    monkeypatch.setattr("platform.analytics.consumer.asyncio.sleep", _fake_sleep)

    await consumer._consume_loop()
    await consumer._flush_loop()

    assert buffered == ["workflow.runtime"]
    assert consumer._consumer.committed is True
    assert flushed == ["flush"]


@pytest.mark.asyncio
async def test_stop_returns_early_when_not_running() -> None:
    consumer = _consumer()

    await consumer.stop()


@pytest.mark.asyncio
async def test_start_and_stop_manage_consumer_lifecycle(monkeypatch) -> None:
    producer = RecordingProducer()
    consumer = _consumer(producer=producer)
    started: list[str] = []
    stopped: list[str] = []

    class FakeKafkaConsumer:
        def __init__(self, *topics: str, **kwargs: object) -> None:
            self.topics = topics
            self.kwargs = kwargs

        async def start(self) -> None:
            started.append("start")

        async def stop(self) -> None:
            stopped.append("stop")

    async def _consume_loop() -> None:
        return None

    async def _flush_loop() -> None:
        return None

    async def _refresh(*, force: bool = False) -> None:
        assert force is True

    monkeypatch.setattr(
        "platform.analytics.consumer.import_module",
        lambda name: SimpleNamespace(AIOKafkaConsumer=FakeKafkaConsumer),
    )
    monkeypatch.setattr(consumer, "_consume_loop", _consume_loop)
    monkeypatch.setattr(consumer, "_flush_loop", _flush_loop)
    monkeypatch.setattr(consumer, "_refresh_cost_model_cache", _refresh)

    await consumer.start()
    await consumer.stop()

    assert started == ["start"]
    assert stopped == ["stop"]
    assert consumer._consumer is None


def test_agent_resolution_and_provider_inference() -> None:
    consumer = _consumer()

    assert consumer._resolve_agent_fqn({"agent_fqn": "planner:daily"}) == "planner:daily"
    assert consumer._resolve_agent_fqn({"agent_namespace": "planner", "agent_name": "daily"}) == (
        "planner:daily"
    )
    assert consumer._resolve_agent_fqn({}) is None
    assert consumer._infer_provider("claude-3-5-sonnet") == "anthropic"
    assert consumer._infer_provider("gemini-2.0-flash") == "google"
    assert consumer._infer_provider("custom") == "unknown"
    consumer._pricing_cache["gpt-4o"] = build_cost_model()
    assert consumer._compute_cost(10, 10, 100, "gpt-4o") > 0
