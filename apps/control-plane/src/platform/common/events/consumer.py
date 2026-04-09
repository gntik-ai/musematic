from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from importlib import import_module
from typing import Any

from platform.common.config import Settings
from platform.common.events.envelope import EventEnvelope
from platform.common.exceptions import KafkaConsumerError

CommitCallback = Callable[[], Awaitable[None]]


class AsyncKafkaConsumer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._consumer: Any | None = None
        self._topics: list[str] = []

    def subscribe(self, topics: list[str]) -> None:
        self._topics = topics

    async def start(self) -> None:
        if self._consumer is not None:
            return
        kafka_module = import_module("aiokafka")
        kafka_consumer_cls = getattr(kafka_module, "AIOKafkaConsumer")
        self._consumer = kafka_consumer_cls(
            *self._topics,
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.settings.KAFKA_CONSUMER_GROUP_ID,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()

    async def stop(self) -> None:
        if self._consumer is None:
            return
        await self._consumer.stop()
        self._consumer = None

    async def consume(self) -> AsyncIterator[tuple[EventEnvelope, CommitCallback]]:
        await self.start()
        assert self._consumer is not None
        try:
            async for message in self._consumer:
                envelope = EventEnvelope.model_validate_json(message.value)

                async def commit() -> None:
                    assert self._consumer is not None
                    await self._consumer.commit()

                yield envelope, commit
        except Exception as exc:  # pragma: no cover
            raise KafkaConsumerError(str(exc)) from exc

    async def reset_offset_to_timestamp(self, topic: str, timestamp_ms: int) -> None:
        await self.start()
        assert self._consumer is not None
        kafka_module = import_module("aiokafka")
        topic_partition_cls = getattr(kafka_module, "TopicPartition")
        partitions = self._consumer.partitions_for_topic(topic) or set()
        topic_partitions = [topic_partition_cls(topic, partition) for partition in partitions]
        timestamps = {partition: timestamp_ms for partition in topic_partitions}
        offsets = await self._consumer.offsets_for_times(timestamps)
        for partition in topic_partitions:
            # offsets_for_times returns the first offset at or after the timestamp.
            offset_and_timestamp = offsets.get(partition)
            if offset_and_timestamp is None:
                await self._consumer.seek_to_beginning(partition)
            else:
                self._consumer.seek(partition, offset_and_timestamp.offset)

    async def __aenter__(self) -> "AsyncKafkaConsumer":
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()
