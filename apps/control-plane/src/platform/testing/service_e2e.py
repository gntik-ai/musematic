from __future__ import annotations

import asyncio
import inspect
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.exceptions import ValidationError
from platform.common.llm.mock_provider import MockLLMProvider
from platform.testing.schemas_e2e import (
    ChaosKillPodItem,
    ChaosKillPodResponse,
    ChaosPartitionResponse,
    KafkaEventRecord,
    KafkaEventsResponse,
    ResetResponse,
    SeedResponse,
)
from typing import Any

ALLOWED_CHAOS_NAMESPACES = {"platform-execution", "platform-data"}


def _seeders_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "tests" / "e2e"
        if (candidate / "seeders" / "base.py").is_file():
            return candidate
    return Path("/app/tests/e2e")


def _ensure_seeders_on_path() -> None:
    seeders_root = str(_seeders_root())
    if seeders_root not in sys.path:
        sys.path.insert(0, seeders_root)


def _discover_seeder_handlers() -> dict[str, Any]:
    _ensure_seeders_on_path()
    try:
        module = import_module("seeders.base")
    except ModuleNotFoundError:
        return {}
    discover = getattr(module, "_discover_seeders", None)
    if not callable(discover):
        return {}
    return {str(seeder.name): seeder for seeder in discover()}


async def _invoke_reset(handler: Any, include_baseline: bool) -> dict[str, int]:
    reset = handler.reset
    try:
        signature = inspect.signature(reset)
    except (TypeError, ValueError):
        signature = None
    if signature and "include_baseline" in signature.parameters:
        result = await reset(include_baseline=include_baseline)
    else:
        result = await reset()
    return {str(key): int(value) for key, value in dict(result).items()}


@dataclass(slots=True)
class SeedService:
    handlers: dict[str, Any] | None = None

    def _handlers(self) -> dict[str, Any]:
        return self.handlers or _discover_seeder_handlers()

    async def seed(self, scope: str) -> SeedResponse:
        start = time.perf_counter()
        handlers = self._handlers()
        seeded: dict[str, int] = {}
        skipped: dict[str, int] = {}
        names = list(handlers) if scope == "all" else [scope]
        for name in names:
            handler = handlers.get(name)
            if handler is None:
                seeded[name] = 0
                skipped[name] = 0
                continue
            result = await handler.seed()
            seeded[name] = int(sum(result.seeded.values()))
            skipped[name] = int(sum(result.skipped.values()))
        return SeedResponse(
            seeded=seeded,
            skipped=skipped,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )


@dataclass(slots=True)
class ResetService:
    handlers: dict[str, Any] | None = None

    def _handlers(self) -> dict[str, Any]:
        return self.handlers or _discover_seeder_handlers()

    async def reset(self, scope: str, *, include_baseline: bool) -> ResetResponse:
        start = time.perf_counter()
        handlers = self._handlers()
        deleted: dict[str, int] = {}
        names = list(handlers) if scope == "all" else [scope]
        for name in names:
            handler = handlers.get(name)
            if handler is None:
                deleted[name] = 0
                continue
            result = await _invoke_reset(handler, include_baseline)
            deleted[name] = int(sum(result.values()))
        return ResetResponse(
            deleted=deleted,
            preserved_baseline=not include_baseline,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )

    @staticmethod
    def ensure_e2e_scope(
        *,
        workspace_names: list[str] | None = None,
        user_emails: list[str] | None = None,
    ) -> None:
        for workspace_name in workspace_names or []:
            if not workspace_name.startswith("test-"):
                raise ValidationError(
                    "E2E_SCOPE_VIOLATION",
                    "Reset refused to delete a non-E2E workspace",
                    {"workspace_name": workspace_name},
                )
        for email in user_emails or []:
            if not email.endswith("@e2e.test"):
                raise ValidationError(
                    "E2E_SCOPE_VIOLATION",
                    "Reset refused to delete a non-E2E user",
                    {"email": email},
                )


class ChaosService:
    async def kill_pod(
        self,
        namespace: str,
        label_selector: str,
        count: int,
    ) -> ChaosKillPodResponse:
        self._validate_namespace(namespace)
        client_module = __import__("kubernetes.client", fromlist=["client"])
        config_module = __import__("kubernetes.config", fromlist=["config"])
        try:
            config_module.load_incluster_config()
        except Exception:
            config_module.load_kube_config()
        api = client_module.CoreV1Api()
        pods = api.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector,
        ).items
        killed: list[ChaosKillPodItem] = []
        for pod in pods[:count]:
            api.delete_namespaced_pod(name=pod.metadata.name, namespace=namespace)
            killed.append(
                ChaosKillPodItem(
                    pod=str(pod.metadata.name),
                    namespace=namespace,
                    at=datetime.now(UTC),
                )
            )
        return ChaosKillPodResponse(
            killed=killed,
            not_found=max(0, count - len(killed)),
        )

    async def partition_network(
        self,
        from_namespace: str,
        to_namespace: str,
        ttl_seconds: int,
    ) -> ChaosPartitionResponse:
        self._validate_namespace(from_namespace)
        self._validate_namespace(to_namespace)
        client_module = __import__("kubernetes.client", fromlist=["client"])
        config_module = __import__("kubernetes.config", fromlist=["config"])
        try:
            config_module.load_incluster_config()
        except Exception:
            config_module.load_kube_config()
        api = client_module.NetworkingV1Api()
        applied_at = datetime.now(UTC)
        expires_at = applied_at + timedelta(seconds=ttl_seconds)
        policy_name = f"e2e-partition-{int(applied_at.timestamp())}"
        body = client_module.V1NetworkPolicy(
            metadata=client_module.V1ObjectMeta(
                name=policy_name,
                labels={"e2e-chaos": "partition"},
                annotations={"expires_at": expires_at.isoformat()},
            ),
            spec=client_module.V1NetworkPolicySpec(
                pod_selector=client_module.V1LabelSelector(match_labels={}),
                policy_types=["Egress"],
                egress=[],
            ),
        )
        api.create_namespaced_network_policy(namespace=from_namespace, body=body)
        return ChaosPartitionResponse(
            network_policy_name=policy_name,
            applied_at=applied_at,
            expires_at=expires_at,
        )

    @staticmethod
    def _validate_namespace(namespace: str) -> None:
        if namespace not in ALLOWED_CHAOS_NAMESPACES:
            raise ValidationError(
                "NAMESPACE_NOT_ALLOWED",
                "Chaos endpoints are limited to E2E namespaces",
                {"namespace": namespace},
            )


@dataclass(slots=True)
class MockLLMService:
    provider: MockLLMProvider

    async def set_response(
        self,
        prompt_pattern: str,
        response: str,
        streaming_chunks: list[str] | None = None,
    ) -> dict[str, int]:
        return await self.provider.set_response(
            prompt_pattern,
            response,
            streaming_chunks,
        )

    async def clear_queue(self, prompt_pattern: str | None = None) -> None:
        await self.provider.clear_queue(prompt_pattern)

    async def set_rate_limit_error(self, prompt_pattern: str, count: int = 1) -> None:
        await self.provider.set_rate_limit_error(prompt_pattern, count)

    async def get_calls(
        self,
        *,
        pattern: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        records = await self.provider.get_calls(pattern=pattern, since=since)
        return [record.model_dump(mode="json") for record in records]


class KafkaObserver:
    def __init__(self, settings: PlatformSettings) -> None:
        self.settings = settings

    async def get_events(
        self,
        *,
        topic: str,
        since: datetime,
        until: datetime | None = None,
        limit: int = 100,
        key: str | None = None,
    ) -> KafkaEventsResponse:
        aiokafka = __import__(
            "aiokafka",
            fromlist=["AIOKafkaConsumer", "TopicPartition"],
        )
        consumer = aiokafka.AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.settings.KAFKA_BROKERS,
            enable_auto_commit=False,
            group_id=None,
            auto_offset_reset="latest",
        )
        await consumer.start()
        events: list[KafkaEventRecord] = []
        try:
            topic_partitions = sorted(
                consumer.assignment(),
                key=lambda partition: partition.partition,
            )
            if not topic_partitions:
                return KafkaEventsResponse(events=[], count=0)
            offsets = await consumer.offsets_for_times(
                {
                    partition: int(since.timestamp() * 1000)
                    for partition in topic_partitions
                }
            )
            active_partitions = []
            for partition in topic_partitions:
                offset_data = offsets.get(partition)
                if offset_data is None or getattr(offset_data, "offset", None) is None:
                    continue
                consumer.seek(partition, int(offset_data.offset))
                active_partitions.append(partition)
            if not active_partitions:
                return KafkaEventsResponse(events=[], count=0)

            resolved_until = until or datetime.now(UTC)
            while len(events) < limit:
                batch = await consumer.getmany(
                    timeout_ms=1000,
                    max_records=limit - len(events),
                )
                if not batch:
                    break
                for records in batch.values():
                    for record in records:
                        ts = datetime.fromtimestamp(record.timestamp / 1000, tz=UTC)
                        if ts < since or ts > resolved_until:
                            continue
                        record_key = record.key
                        if isinstance(record_key, bytes):
                            record_key = record_key.decode("utf-8")
                        if key is not None and record_key != key:
                            continue
                        payload_bytes = record.value
                        if isinstance(payload_bytes, bytes):
                            payload_bytes = payload_bytes.decode("utf-8")
                        try:
                            payload = json.loads(payload_bytes)
                        except Exception:
                            payload = {"raw": payload_bytes}
                        headers = {
                            header_key: (
                                header_value.decode("utf-8")
                                if isinstance(header_value, bytes)
                                else str(header_value)
                            )
                            for header_key, header_value in (record.headers or [])
                        }
                        normalized_payload = (
                            payload
                            if isinstance(payload, dict)
                            else {"value": payload}
                        )
                        events.append(
                            KafkaEventRecord(
                                topic=record.topic,
                                partition=record.partition,
                                offset=record.offset,
                                key=record_key,
                                timestamp=ts,
                                headers=headers,
                                payload=normalized_payload,
                            )
                        )
                        if len(events) >= limit:
                            break
                    if len(events) >= limit:
                        break
            return KafkaEventsResponse(events=events, count=len(events))
        finally:
            try:
                await consumer.stop()
            except asyncio.CancelledError:
                pass


def build_mock_llm_service(redis_client: AsyncRedisClient) -> MockLLMService:
    return MockLLMService(provider=MockLLMProvider(redis_client))
