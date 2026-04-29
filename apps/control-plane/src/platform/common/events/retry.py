from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from typing import Any

LOGGER = get_logger(__name__)


class RetryHandler:
    def __init__(self, producer: EventProducer, max_attempts: int = 3) -> None:
        self.producer = producer
        self.max_attempts = max_attempts

    async def handle(
        self,
        topic: str,
        envelope: EventEnvelope,
        handler: Any,
    ) -> None:
        attempt = 0
        while attempt < self.max_attempts:
            attempt += 1
            try:
                await handler(envelope)
                return
            except Exception as exc:
                if attempt < self.max_attempts:
                    LOGGER.warning(
                        "Retrying event %s on %s (attempt %s)",
                        envelope.event_type,
                        topic,
                        attempt,
                    )
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                LOGGER.error("Routing event %s to DLQ for %s", envelope.event_type, topic)
                dlq_payload = {
                    "original_payload": envelope.payload,
                    "failure_reason": str(exc),
                    "attempt_count": attempt,
                    "failed_at": datetime.now(UTC).isoformat(),
                }
                await self.producer.publish(
                    topic=f"{topic}.dlq",
                    key=str(envelope.correlation_context.correlation_id),
                    event_type=envelope.event_type,
                    payload=dlq_payload,
                    correlation_ctx=envelope.correlation_context,
                    source=f"{topic}.consumer",
                )
                return
