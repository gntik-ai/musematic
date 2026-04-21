from __future__ import annotations

import builtins
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.exceptions import ValidationError
from platform.testing.service_e2e import KafkaObserver, ResetService, SeedService
from typing import ClassVar

import pytest


@dataclass(slots=True)
class SeedRunSummary:
    seeded: dict[str, int]
    skipped: dict[str, int]


@dataclass(slots=True)
class FakeSeeder:
    name: str
    dependencies: tuple[str, ...] = ()

    async def seed(self) -> SeedRunSummary:
        return SeedRunSummary(seeded={self.name: 2}, skipped={self.name: 1})

    async def reset(self, *, include_baseline: bool = False) -> dict[str, int]:
        return {self.name: 3 if include_baseline else 1}


@pytest.mark.asyncio
async def test_seed_service_discovers_seeders(monkeypatch) -> None:
    fake_module = types.SimpleNamespace(
        _discover_seeders=lambda: [
            FakeSeeder("users"),
            FakeSeeder("agents", dependencies=("users",)),
        ]
    )
    monkeypatch.setattr(
        "platform.testing.service_e2e.import_module",
        lambda name: fake_module,
    )
    service = SeedService()

    response = await service.seed("all")

    assert response.seeded == {"users": 2, "agents": 2}
    assert response.skipped == {"users": 1, "agents": 1}


@pytest.mark.asyncio
async def test_reset_service_passes_include_baseline(monkeypatch) -> None:
    fake_module = types.SimpleNamespace(
        _discover_seeders=lambda: [FakeSeeder("workspaces")]
    )
    monkeypatch.setattr(
        "platform.testing.service_e2e.import_module",
        lambda name: fake_module,
    )
    service = ResetService()

    response = await service.reset("all", include_baseline=True)

    assert response.deleted == {"workspaces": 3}
    assert response.preserved_baseline is False


def test_reset_service_rejects_non_e2e_targets() -> None:
    with pytest.raises(ValidationError) as workspace_error:
        ResetService.ensure_e2e_scope(workspace_names=["prod-workspace"])
    with pytest.raises(ValidationError) as email_error:
        ResetService.ensure_e2e_scope(user_emails=["user@example.com"])

    assert workspace_error.value.code == "E2E_SCOPE_VIOLATION"
    assert email_error.value.code == "E2E_SCOPE_VIOLATION"


class FakeTopicPartition:
    def __init__(self, topic: str, partition: int) -> None:
        self.topic = topic
        self.partition = partition

    def __hash__(self) -> int:
        return hash((self.topic, self.partition))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FakeTopicPartition):
            return False
        return (self.topic, self.partition) == (other.topic, other.partition)


class FakeOffset:
    def __init__(self, offset: int) -> None:
        self.offset = offset


class FakeRecord:
    def __init__(
        self,
        *,
        timestamp: int,
        key: bytes | None,
        value: bytes,
        headers=None,
    ) -> None:
        self.topic = "execution.events"
        self.partition = 0
        self.offset = 12
        self.timestamp = timestamp
        self.key = key
        self.value = value
        self.headers = headers or []


class FakeConsumer:
    assigned: ClassVar[list[FakeTopicPartition] | None] = None
    seek_calls: ClassVar[list[tuple[int, int]]] = []
    requested_timestamps: ClassVar[dict[FakeTopicPartition, int] | None] = None
    started: ClassVar[bool] = False
    stopped: ClassVar[bool] = False

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def start(self) -> None:
        type(self).started = True

    async def stop(self) -> None:
        type(self).stopped = True

    async def partitions_for_topic(self, topic: str):
        assert topic == "execution.events"
        return {0}

    def assign(self, partitions) -> None:
        type(self).assigned = partitions

    async def offsets_for_times(self, timestamps):
        type(self).requested_timestamps = timestamps
        partition = next(iter(timestamps))
        return {partition: FakeOffset(7)}

    def seek(self, partition, offset: int) -> None:
        type(self).seek_calls.append((partition.partition, offset))

    async def getmany(self, timeout_ms: int, max_records: int):
        del timeout_ms, max_records
        if getattr(self, "_done", False):
            return {}
        self._done = True
        ts = int(datetime(2026, 4, 21, 10, 0, tzinfo=UTC).timestamp() * 1000)
        partition = type(self).assigned[0]
        return {
            partition: [
                FakeRecord(
                    timestamp=ts,
                    key=b"keep",
                    value=b'{"event_type":"checkpoint.created"}',
                    headers=[("trace_id", b"abc")],
                ),
                FakeRecord(timestamp=ts, key=b"drop", value=b"not-json"),
            ]
        }


@pytest.mark.asyncio
async def test_kafka_observer_seeks_from_timestamp_and_filters(monkeypatch) -> None:
    FakeConsumer.assigned = None
    FakeConsumer.seek_calls = []
    FakeConsumer.requested_timestamps = None
    FakeConsumer.started = False
    FakeConsumer.stopped = False
    fake_aiokafka = types.SimpleNamespace(
        AIOKafkaConsumer=FakeConsumer,
        TopicPartition=FakeTopicPartition,
    )
    original_import = builtins.__import__

    def fake_import(name, global_ns=None, local_ns=None, fromlist=(), level=0):
        if name == "aiokafka":
            return fake_aiokafka
        return original_import(name, global_ns, local_ns, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    observer = KafkaObserver(PlatformSettings(kafka={"brokers": "localhost:9092"}))
    since = datetime(2026, 4, 21, 9, 0, tzinfo=UTC)
    until = datetime(2026, 4, 21, 11, 0, tzinfo=UTC)

    response = await observer.get_events(
        topic="execution.events",
        since=since,
        until=until,
        limit=10,
        key="keep",
    )

    assert FakeConsumer.started is True
    assert FakeConsumer.stopped is True
    assert FakeConsumer.assigned is not None
    assert FakeConsumer.seek_calls == [(0, 7)]
    assert response.count == 1
    assert response.events[0].payload == {"event_type": "checkpoint.created"}
    assert response.events[0].headers == {"trace_id": "abc"}
    requested = next(iter(FakeConsumer.requested_timestamps.values()))
    assert requested == int(since.timestamp() * 1000)
