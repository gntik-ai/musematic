from __future__ import annotations

from importlib import import_module
from typing import Any

from platform.common.config import Settings
from platform.common.events.envelope import EventEnvelope
from platform.common.exceptions import KafkaProducerError


class AsyncKafkaProducer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._producer: Any | None = None

    async def start(self) -> None:
        if self._producer is not None:
            return
        kafka_module = import_module("aiokafka")
        kafka_producer_cls = getattr(kafka_module, "AIOKafkaProducer")
        self._producer = kafka_producer_cls(
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
            acks="all",
            enable_idempotence=True,
            compression_type="lz4",
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is None:
            return
        await self._producer.stop()
        self._producer = None

    async def produce(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        partition_key: str | None = None,
    ) -> None:
        await self.start()
        assert self._producer is not None
        try:
            await self._producer.send_and_wait(
                topic,
                envelope.model_dump_json().encode(),
                key=partition_key.encode() if partition_key is not None else None,
            )
        except Exception as exc:  # pragma: no cover - network/container dependent
            raise KafkaProducerError(str(exc)) from exc

    async def __aenter__(self) -> "AsyncKafkaProducer":
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()

    @staticmethod
    async def health_check(settings: Settings) -> dict[str, object]:
        producer = AsyncKafkaProducer(settings)
        try:
            await producer.start()
            assert producer._producer is not None
            topics = await producer._producer.client.fetch_all_metadata()
            return {"status": "ok", "topic_count": len(topics.topics)}
        except Exception as exc:  # pragma: no cover - network/container dependent
            return {"status": "error", "error": str(exc)}
        finally:
            await producer.stop()
