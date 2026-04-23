from __future__ import annotations

import asyncio
import builtins
import types
from datetime import UTC, datetime
from pathlib import Path
from platform.common.config import PlatformSettings
from platform.common.exceptions import ValidationError
from platform.common.llm.mock_provider import MockLLMProvider
from platform.testing import service_e2e

import pytest


@pytest.mark.asyncio
async def test_service_e2e_helper_functions_cover_discovery_and_unknown_scopes(monkeypatch) -> None:
    fake_root = Path("/tmp/e2e-seeders")
    monkeypatch.setattr(service_e2e, "_seeders_root", lambda: fake_root)
    monkeypatch.setattr(service_e2e.sys, "path", [])

    service_e2e._ensure_seeders_on_path()
    service_e2e._ensure_seeders_on_path()
    assert service_e2e.sys.path == [str(fake_root)]

    def missing_module(name: str):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(service_e2e, "import_module", missing_module)
    assert service_e2e._discover_seeder_handlers() == {}

    monkeypatch.setattr(
        service_e2e, "import_module", lambda name: types.SimpleNamespace(_discover_seeders=None)
    )
    assert service_e2e._discover_seeder_handlers() == {}

    class LegacyReset:
        async def reset(self) -> dict[str, int]:
            return {"legacy": 2}

    monkeypatch.setattr(
        service_e2e.inspect,
        "signature",
        lambda fn: (_ for _ in ()).throw(TypeError("no signature")),
    )
    assert await service_e2e._invoke_reset(LegacyReset(), include_baseline=True) == {"legacy": 2}

    seed_response = await service_e2e.SeedService(handlers={}).seed("users")
    reset_response = await service_e2e.ResetService(handlers={}).reset(
        "workspaces", include_baseline=False
    )

    assert seed_response.seeded == {"users": 0}
    assert seed_response.skipped == {"users": 0}
    assert reset_response.deleted == {"workspaces": 0}
    assert reset_response.preserved_baseline is True

    service_e2e.ResetService.ensure_e2e_scope(
        workspace_names=["test-workspace"],
        user_emails=["user@e2e.test"],
    )


@pytest.mark.asyncio
async def test_mock_llm_service_wrapper_and_builder() -> None:
    captured: dict[str, object] = {}

    class FakeProvider:
        async def set_response(self, prompt_pattern: str, response: str, streaming_chunks):
            captured["args"] = (prompt_pattern, response, streaming_chunks)
            return {"agent_response": 3}

    service = service_e2e.MockLLMService(provider=FakeProvider())
    response = await service.set_response("agent_response", "ok", ["o", "k"])
    built = service_e2e.build_mock_llm_service(object())

    assert response == {"agent_response": 3}
    assert captured["args"] == ("agent_response", "ok", ["o", "k"])
    assert isinstance(built.provider, MockLLMProvider)


@pytest.mark.asyncio
async def test_chaos_service_uses_kubernetes_clients_and_validates_namespaces(monkeypatch) -> None:
    deleted_pods: list[tuple[str, str]] = []
    created_policies: list[tuple[str, object]] = []

    class FakeConfigModule:
        kube_loaded = False

        @staticmethod
        def load_incluster_config() -> None:
            raise RuntimeError("missing incluster config")

        @staticmethod
        def load_kube_config() -> None:
            FakeConfigModule.kube_loaded = True

    class FakeCoreV1Api:
        def list_namespaced_pod(self, *, namespace: str, label_selector: str):
            assert namespace == "platform-execution"
            assert label_selector == "app=worker"
            pods = [
                types.SimpleNamespace(metadata=types.SimpleNamespace(name="worker-a")),
                types.SimpleNamespace(metadata=types.SimpleNamespace(name="worker-b")),
            ]
            return types.SimpleNamespace(items=pods)

        def delete_namespaced_pod(self, *, name: str, namespace: str) -> None:
            deleted_pods.append((name, namespace))

    class FakeNetworkingV1Api:
        def create_namespaced_network_policy(self, *, namespace: str, body: object) -> None:
            created_policies.append((namespace, body))

    fake_client_module = types.SimpleNamespace(
        CoreV1Api=FakeCoreV1Api,
        NetworkingV1Api=FakeNetworkingV1Api,
        V1NetworkPolicy=lambda **kwargs: types.SimpleNamespace(**kwargs),
        V1ObjectMeta=lambda **kwargs: types.SimpleNamespace(**kwargs),
        V1NetworkPolicySpec=lambda **kwargs: types.SimpleNamespace(**kwargs),
        V1LabelSelector=lambda **kwargs: types.SimpleNamespace(**kwargs),
    )
    original_import = builtins.__import__

    def fake_import(name, global_ns=None, local_ns=None, fromlist=(), level=0):
        if name == "kubernetes.client":
            return fake_client_module
        if name == "kubernetes.config":
            return FakeConfigModule
        return original_import(name, global_ns, local_ns, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    service = service_e2e.ChaosService()

    kill_response = await service.kill_pod("platform-execution", "app=worker", 3)
    partition_response = await service.partition_network(
        "platform-execution",
        "platform-data",
        30,
    )

    assert FakeConfigModule.kube_loaded is True
    assert deleted_pods == [
        ("worker-a", "platform-execution"),
        ("worker-b", "platform-execution"),
    ]
    assert kill_response.not_found == 1
    assert partition_response.network_policy_name.startswith("e2e-partition-")
    assert created_policies[0][0] == "platform-execution"
    assert created_policies[0][1].metadata.labels == {"e2e-chaos": "partition"}

    with pytest.raises(ValidationError) as excinfo:
        await service.kill_pod("default", "app=worker", 1)

    assert excinfo.value.code == "NAMESPACE_NOT_ALLOWED"


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


class EmptyTopicConsumer:
    started = False
    stopped = False

    def __init__(self, *topics, **kwargs) -> None:
        self.topics = topics
        self.kwargs = kwargs

    async def start(self) -> None:
        type(self).started = True

    async def stop(self) -> None:
        type(self).stopped = True

    def assignment(self):
        return []


class RawRecordConsumer:
    started = False
    stopped = False
    assigned = None

    def __init__(self, *topics, **kwargs) -> None:
        self.topics = topics
        self.kwargs = kwargs
        self._done = False

    async def start(self) -> None:
        type(self).started = True

    async def stop(self) -> None:
        type(self).stopped = True

    def assignment(self):
        type(self).assigned = [FakeTopicPartition("execution.events", 0)]
        return type(self).assigned

    async def offsets_for_times(self, timestamps):
        partition = next(iter(timestamps))
        return {partition: types.SimpleNamespace(offset=5)}

    def seek(self, partition, offset: int) -> None:
        return None

    async def getmany(self, timeout_ms: int, max_records: int):
        del timeout_ms, max_records
        if self._done:
            return {}
        self._done = True
        timestamp = int(datetime(2026, 4, 21, 10, 0, tzinfo=UTC).timestamp() * 1000)
        partition = type(self).assigned[0]
        return {
            partition: [
                types.SimpleNamespace(
                    topic="execution.events",
                    partition=0,
                    offset=5,
                    timestamp=timestamp,
                    key="keep",
                    value=b"not-json",
                    headers=[("attempt", 2)],
                ),
                types.SimpleNamespace(
                    topic="execution.events",
                    partition=0,
                    offset=6,
                    timestamp=timestamp,
                    key=b"keep-2",
                    value=b'"scalar"',
                    headers=[],
                ),
            ]
        }


class StopCancellingConsumer(RawRecordConsumer):
    stopped = False

    async def stop(self) -> None:
        type(self).stopped = True
        raise asyncio.CancelledError()


@pytest.mark.asyncio
async def test_kafka_observer_handles_empty_topics_and_non_json_payloads(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import_empty(name, global_ns=None, local_ns=None, fromlist=(), level=0):
        if name == "aiokafka":
            return types.SimpleNamespace(
                AIOKafkaConsumer=EmptyTopicConsumer,
                TopicPartition=lambda topic, partition: (topic, partition),
            )
        return original_import(name, global_ns, local_ns, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import_empty)
    observer = service_e2e.KafkaObserver(PlatformSettings(kafka={"brokers": "localhost:9092"}))
    empty_response = await observer.get_events(
        topic="execution.events",
        since=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
    )

    assert empty_response.count == 0
    assert EmptyTopicConsumer.started is True
    assert EmptyTopicConsumer.stopped is True

    def fake_import_raw(name, global_ns=None, local_ns=None, fromlist=(), level=0):
        if name == "aiokafka":
            return types.SimpleNamespace(
                AIOKafkaConsumer=RawRecordConsumer,
                TopicPartition=lambda topic, partition: (topic, partition),
            )
        return original_import(name, global_ns, local_ns, fromlist, level)

    class FixedKafkaDateTime:
        @staticmethod
        def now(tz):
            return datetime(2026, 4, 21, 11, 0, tzinfo=tz)

        @staticmethod
        def fromtimestamp(timestamp: float, tz):
            return datetime.fromtimestamp(timestamp, tz=tz)

    monkeypatch.setattr(builtins, "__import__", fake_import_raw)
    monkeypatch.setattr(service_e2e, "datetime", FixedKafkaDateTime)
    raw_response = await observer.get_events(
        topic="execution.events",
        since=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        until=None,
        limit=2,
        key=None,
    )

    assert raw_response.count == 2
    assert raw_response.events[0].payload == {"raw": "not-json"}
    assert raw_response.events[0].headers == {"attempt": "2"}
    assert raw_response.events[1].payload == {"value": "scalar"}
    assert raw_response.events[1].key == "keep-2"

    def fake_import_stop_cancel(name, global_ns=None, local_ns=None, fromlist=(), level=0):
        if name == "aiokafka":
            return types.SimpleNamespace(
                AIOKafkaConsumer=StopCancellingConsumer,
                TopicPartition=lambda topic, partition: (topic, partition),
            )
        return original_import(name, global_ns, local_ns, fromlist, level)

    StopCancellingConsumer.started = False
    StopCancellingConsumer.stopped = False
    StopCancellingConsumer.assigned = None
    monkeypatch.setattr(builtins, "__import__", fake_import_stop_cancel)
    stop_cancel_response = await observer.get_events(
        topic="execution.events",
        since=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        until=None,
        limit=1,
        key=None,
    )

    assert stop_cancel_response.count == 1
    assert StopCancellingConsumer.stopped is True
