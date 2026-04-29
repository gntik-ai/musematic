from __future__ import annotations

import inspect
import json
from datetime import datetime
from platform.common.config import PlatformSettings
from platform.incident_response.schemas import TimelineEntry, TimelineSource
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from aiokafka import AIOKafkaConsumer

if TYPE_CHECKING:
    TopicPartition: Any
else:
    from aiokafka.structs import TopicPartition


class KafkaTimelineReplay:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        consumer_factory: type[AIOKafkaConsumer] = AIOKafkaConsumer,
    ) -> None:
        self.settings = settings
        self.consumer_factory = consumer_factory
        self.last_window_partial = False

    async def read_window(
        self,
        topics: list[str],
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[TimelineEntry]:
        window_hours = (end_ts - start_ts).total_seconds() / 3600
        if window_hours > self.settings.incident_response.timeline_max_window_hours:
            raise ValueError("timeline Kafka replay window exceeds configured cap")
        self.last_window_partial = False
        consumer = self.consumer_factory(
            *topics,
            bootstrap_servers=self.settings.kafka.brokers,
            enable_auto_commit=False,
        )
        try:
            await consumer.start()
            partitions: list[TopicPartition] = []
            for topic in topics:
                topic_partitions = consumer.partitions_for_topic(topic) or set()
                partitions.extend(
                    TopicPartition(topic, partition) for partition in topic_partitions
                )
            if not partitions:
                return []
            offsets = await consumer.offsets_for_times(
                {partition: int(start_ts.timestamp() * 1000) for partition in partitions}
            )
            end_offsets = await consumer.end_offsets(partitions)
            for partition in partitions:
                offset_and_timestamp = offsets.get(partition)
                if offset_and_timestamp is None:
                    await _maybe_await(consumer.seek(partition, end_offsets[partition]))
                    self.last_window_partial = True
                    continue
                if offset_and_timestamp.offset > 0:
                    beginning = (await consumer.beginning_offsets([partition]))[partition]
                    if offset_and_timestamp.offset <= beginning:
                        self.last_window_partial = True
                await _maybe_await(consumer.seek(partition, offset_and_timestamp.offset))

            entries: list[TimelineEntry] = []
            while True:
                batch = await consumer.getmany(timeout_ms=500, max_records=100)
                if not batch:
                    break
                stop = True
                for records in batch.values():
                    for record in records:
                        timestamp = datetime.fromtimestamp(
                            record.timestamp / 1000, tz=end_ts.tzinfo
                        )
                        if timestamp > end_ts:
                            continue
                        stop = False
                        entries.append(
                            TimelineEntry(
                                id=f"kafka:{record.topic}:{record.partition}:{record.offset}",
                                timestamp=timestamp,
                                source=TimelineSource.kafka,
                                topic=record.topic,
                                event_type=_event_type(record.value),
                                summary=_payload_summary(record.value),
                                payload_summary={"key": _decode(record.key)},
                            )
                        )
                if stop:
                    break
            return entries
        finally:
            await consumer.stop()


def _decode(value: bytes | None) -> str | None:
    if value is None:
        return None
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value


def _load_json(value: bytes | None) -> dict[str, Any]:
    decoded = _decode(value)
    if not decoded:
        return {}
    try:
        parsed = json.loads(decoded)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _event_type(value: bytes | None) -> str | None:
    payload = _load_json(value)
    event_type = payload.get("event_type") or payload.get("type")
    return str(event_type) if event_type is not None else None


def _payload_summary(value: bytes | None) -> str:
    payload = _load_json(value)
    if not payload:
        return f"Kafka event {uuid4()}"
    event_type = payload.get("event_type") or payload.get("type") or "event"
    subject = payload.get("subject") or payload.get("id") or payload.get("key") or ""
    return " ".join(part for part in (str(event_type), str(subject)) if part).strip()
