from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from platform.common.events.envelope import EventEnvelope, make_envelope
from platform.common.events.producer import AsyncKafkaProducer


class RetryHandler:
    def __init__(
        self,
        producer: AsyncKafkaProducer,
        max_attempts: int = 3,
        backoff_base_ms: int = 500,
    ) -> None:
        self.producer = producer
        self.max_attempts = max_attempts
        self.backoff_base_ms = backoff_base_ms

    async def handle(
        self,
        envelope: EventEnvelope,
        source_topic: str,
        source_partition: int,
        source_offset: int,
        processor: Callable[[EventEnvelope], Awaitable[None]],
        commit_fn: Callable[[], Awaitable[None]],
    ) -> None:
        retry_attempts: list[dict[str, object]] = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                await processor(envelope)
                await commit_fn()
                return
            except Exception as exc:
                retry_attempts.append(
                    {
                        "attempt": attempt,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "error": str(exc),
                    }
                )
                if attempt < self.max_attempts:
                    await asyncio.sleep((self.backoff_base_ms * (2 ** attempt)) / 1000)
                    continue

                dlq = make_envelope(
                    event_type="dlq.FailedMessage",
                    actor=f"consumer-group:{source_topic}",
                    payload={
                        "original_envelope": envelope.model_dump(mode="json"),
                        "source_topic": source_topic,
                        "source_partition": source_partition,
                        "source_offset": source_offset,
                        "error_class": exc.__class__.__name__,
                        "error_message": str(exc),
                        "retry_attempts": retry_attempts,
                    },
                    correlation=envelope.correlation,
                )
                await self.producer.produce(f"{source_topic}.dlq", dlq)
                await commit_fn()
                return

