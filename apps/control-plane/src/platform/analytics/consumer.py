from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from platform.analytics.models import CostModel
from platform.analytics.repository import AnalyticsRepository, CostModelRepository
from platform.common import database
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.common.events.retry import RetryHandler
from typing import Any
from uuid import UUID, uuid4

LOGGER = logging.getLogger(__name__)


class AnalyticsPipelineConsumer:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        clickhouse_client: AsyncClickHouseClient,
        producer: EventProducer | None = None,
    ) -> None:
        self.settings = settings
        self.repository = AnalyticsRepository(clickhouse_client)
        self.producer = producer
        self._consumer: Any | None = None
        self._consume_task: asyncio.Task[None] | None = None
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False
        self._usage_buffer: list[tuple[str, EventEnvelope, dict[str, Any]]] = []
        self._quality_buffer: list[tuple[str, EventEnvelope, dict[str, Any]]] = []
        self._buffer_lock = asyncio.Lock()
        self._pricing_cache: dict[str, CostModel] = {}
        self._pricing_cache_refreshed_at: datetime | None = None
        self._retry_handler = RetryHandler(producer) if producer is not None else None

    async def start(self) -> None:
        if self._running:
            return
        aiokafka = import_module("aiokafka")
        consumer_cls = aiokafka.AIOKafkaConsumer
        self._consumer = consumer_cls(
            "workflow.runtime",
            "runtime.lifecycle",
            "evaluation.events",
            bootstrap_servers=self.settings.KAFKA_BROKERS,
            group_id="analytics-pipeline",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        await self._refresh_cost_model_cache(force=True)
        self._running = True
        self._consume_task = asyncio.create_task(self._consume_loop())
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for task in (self._consume_task, self._flush_task):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._consume_task = None
        self._flush_task = None
        await self._flush_buffers()
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def _consume_loop(self) -> None:
        assert self._consumer is not None
        try:
            async for message in self._consumer:
                envelope = EventEnvelope.model_validate_json(message.value)
                await self._buffer_event(str(message.topic), envelope)
                commit = getattr(self._consumer, "commit", None)
                if callable(commit):
                    result = commit()
                    if hasattr(result, "__await__"):
                        await result
        except asyncio.CancelledError:
            raise

    async def _flush_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(5)
                await self._flush_buffers()
        except asyncio.CancelledError:
            raise

    async def _buffer_event(self, topic: str, envelope: EventEnvelope) -> None:
        if topic == "evaluation.events":
            usage_row = None
            quality_row = self._extract_quality_event(envelope)
        else:
            usage_row = self._extract_usage_event(envelope)
            quality_row = None
        usage_trigger = False
        quality_trigger = False
        async with self._buffer_lock:
            if usage_row is not None:
                self._usage_buffer.append((topic, envelope, usage_row))
                usage_trigger = len(self._usage_buffer) >= 100
            if quality_row is not None:
                self._quality_buffer.append((topic, envelope, quality_row))
                quality_trigger = len(self._quality_buffer) >= 100
        if usage_trigger or quality_trigger:
            await self._flush_buffers()

    async def _flush_buffers(self) -> None:
        async with self._buffer_lock:
            usage_batch = list(self._usage_buffer)
            quality_batch = list(self._quality_buffer)
            self._usage_buffer.clear()
            self._quality_buffer.clear()
        if usage_batch:
            await self._retry_batch_insert(
                topic_hint="workflow.runtime",
                envelopes=[item[1] for item in usage_batch],
                handler=lambda: self.repository.insert_usage_events_batch(
                    [item[2] for item in usage_batch]
                ),
            )
        if quality_batch:
            await self._retry_batch_insert(
                topic_hint="evaluation.events",
                envelopes=[item[1] for item in quality_batch],
                handler=lambda: self.repository.insert_quality_events_batch(
                    [item[2] for item in quality_batch]
                ),
            )

    async def _retry_batch_insert(
        self,
        *,
        topic_hint: str,
        envelopes: list[EventEnvelope],
        handler: Any,
    ) -> None:
        delay = 1
        for attempt in range(1, 4):
            try:
                await handler()
                return
            except Exception as exc:
                if attempt >= 3:
                    LOGGER.error(
                        "Analytics batch insert failed after %s attempts for %s: %s",
                        attempt,
                        topic_hint,
                        exc,
                    )
                    await self._route_failed_batch_to_dlq(topic_hint, envelopes)
                    return
                LOGGER.warning(
                    "Retrying analytics batch insert for %s (attempt %s): %s",
                    topic_hint,
                    attempt,
                    exc,
                )
                await asyncio.sleep(delay)
                delay *= 2

    async def _route_failed_batch_to_dlq(
        self,
        topic_hint: str,
        envelopes: list[EventEnvelope],
    ) -> None:
        if self._retry_handler is None:
            return

        async def _always_fail(_: EventEnvelope) -> None:
            raise RuntimeError("analytics-batch-failed")

        for envelope in envelopes:
            await self._retry_handler.handle(topic_hint, envelope, _always_fail)

    def _extract_usage_event(self, envelope: EventEnvelope) -> dict[str, Any] | None:
        workspace_id = envelope.correlation_context.workspace_id
        if workspace_id is None:
            return None
        agent_fqn = self._resolve_agent_fqn(envelope.payload)
        model_id = str(envelope.payload.get("model_id") or envelope.payload.get("model") or "")
        if not agent_fqn or not model_id:
            return None
        execution_id = envelope.correlation_context.execution_id or UUID(
            str(envelope.payload.get("execution_id") or uuid4())
        )
        input_tokens = int(envelope.payload.get("input_tokens") or 0)
        output_tokens = int(envelope.payload.get("output_tokens") or 0)
        execution_duration_ms = int(
            envelope.payload.get("execution_duration_ms")
            or envelope.payload.get("duration_ms")
            or 0
        )
        reasoning_tokens = int(envelope.payload.get("reasoning_tokens") or 0)
        self_correction_loops = int(envelope.payload.get("self_correction_loops") or 0)
        provider = str(
            envelope.payload.get("provider")
            or self._infer_provider(model_id)
        )
        return {
            "event_id": envelope.correlation_context.correlation_id,
            "execution_id": execution_id,
            "workspace_id": workspace_id,
            "goal_id": envelope.correlation_context.goal_id,
            "agent_fqn": agent_fqn,
            "model_id": model_id,
            "provider": provider,
            "timestamp": envelope.occurred_at,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "execution_duration_ms": execution_duration_ms,
            "self_correction_loops": self_correction_loops,
            "reasoning_tokens": reasoning_tokens,
            "cost_usd": self._compute_cost(
                input_tokens,
                output_tokens,
                execution_duration_ms,
                model_id,
            ),
            "pipeline_version": "1",
            "ingested_at": datetime.now(UTC),
        }

    def _extract_quality_event(self, envelope: EventEnvelope) -> dict[str, Any] | None:
        workspace_id = envelope.correlation_context.workspace_id
        execution_id = (
            envelope.correlation_context.execution_id
            or envelope.payload.get("execution_id")
        )
        quality_score = envelope.payload.get("quality_score")
        agent_fqn = self._resolve_agent_fqn(envelope.payload)
        model_id = str(envelope.payload.get("model_id") or envelope.payload.get("model") or "")
        if (
            workspace_id is None
            or execution_id is None
            or quality_score is None
            or not agent_fqn
            or not model_id
        ):
            return None
        return {
            "event_id": envelope.correlation_context.correlation_id,
            "execution_id": UUID(str(execution_id)),
            "workspace_id": workspace_id,
            "goal_id": envelope.correlation_context.goal_id,
            "agent_fqn": agent_fqn,
            "model_id": model_id,
            "timestamp": envelope.occurred_at,
            "quality_score": float(quality_score),
            "eval_suite_id": UUID(
                str(
                    envelope.payload.get("eval_suite_id")
                    or "00000000-0000-0000-0000-000000000000"
                )
            ),
            "ingested_at": datetime.now(UTC),
        }

    def _compute_cost(
        self,
        tokens_in: int,
        tokens_out: int,
        duration_ms: int,
        model_id: str,
    ) -> float:
        model = self._pricing_cache.get(model_id)
        if model is None:
            return 0.0
        input_cost = Decimal(tokens_in) * Decimal(model.input_token_cost_usd)
        output_cost = Decimal(tokens_out) * Decimal(model.output_token_cost_usd)
        duration_cost = Decimal("0")
        if model.per_second_cost_usd is not None:
            duration_cost = (
                Decimal(duration_ms) / Decimal(1000)
            ) * Decimal(model.per_second_cost_usd)
        return float(
            (input_cost + output_cost + duration_cost).quantize(Decimal("0.0000000001"))
        )

    async def _refresh_cost_model_cache(self, *, force: bool = False) -> None:
        now = datetime.now(UTC)
        if (
            not force
            and self._pricing_cache_refreshed_at is not None
            and now - self._pricing_cache_refreshed_at < timedelta(seconds=300)
        ):
            return
        async with database.AsyncSessionLocal() as session:
            repository = CostModelRepository(session)
            models = await repository.list_all()
        self._pricing_cache = {
            model.model_id: model
            for model in models
            if model.is_active and (model.valid_until is None or model.valid_until > now)
        }
        self._pricing_cache_refreshed_at = now

    def _resolve_agent_fqn(self, payload: dict[str, Any]) -> str | None:
        if payload.get("agent_fqn"):
            return str(payload["agent_fqn"])
        namespace = payload.get("agent_namespace")
        local_name = payload.get("agent_name")
        if namespace and local_name:
            return f"{namespace}:{local_name}"
        return None

    def _infer_provider(self, model_id: str) -> str:
        lowered = model_id.lower()
        if lowered.startswith("gpt"):
            return "openai"
        if lowered.startswith("claude"):
            return "anthropic"
        if lowered.startswith("gemini"):
            return "google"
        return "unknown"
