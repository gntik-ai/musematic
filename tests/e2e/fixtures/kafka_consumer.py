from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest


class KafkaTestConsumer:
    def __init__(self, bootstrap_servers: str, http_client: Any | None = None) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.consumer: Any | None = None
        self._aiokafka: Any | None = None
        self.http_client = http_client
        self._seen: dict[str, int] = {}

    async def __aenter__(self) -> KafkaTestConsumer:
        if self.http_client is None:
            self._aiokafka = pytest.importorskip("aiokafka")
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self.consumer is not None:
            await self.consumer.stop()

    async def subscribe(self, topic: str) -> None:
        if self.http_client is not None:
            self._seen.setdefault(topic, 0)
            return
        assert self._aiokafka is not None
        if self.consumer is not None:
            await self.consumer.stop()
        self.consumer = self._aiokafka.AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=None,
            auto_offset_reset="latest",
            enable_auto_commit=False,
        )
        await self.consumer.start()

    async def expect_event(
        self,
        topic: str,
        predicate: Callable[[dict[str, Any]], bool],
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        if self.consumer is None:
            await self.subscribe(topic)
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            assert remaining > 0, f"Timed out waiting for Kafka event on {topic}"
            if self.http_client is not None:
                response = await self.http_client.get(
                    "/api/v1/_e2e/contract/events",
                    params={"topic": topic},
                )
                assert response.status_code == 200, response.text
                items = response.json().get("items", [])
                start = self._seen.get(topic, 0)
                for index, event in enumerate(items[start:], start=start + 1):
                    if predicate(event):
                        self._seen[topic] = index
                        return event
                await asyncio.sleep(min(remaining, 0.2))
                continue
            assert self.consumer is not None
            batches = await self.consumer.getmany(
                timeout_ms=int(min(remaining, 1.0) * 1000),
                max_records=25,
            )
            for records in batches.values():
                for record in records:
                    event = self._decode_record(record)
                    if predicate(event):
                        return event

    async def collect(self, topic: str, duration: float) -> list[dict[str, Any]]:
        if self.consumer is None:
            await self.subscribe(topic)
        if self.http_client is not None:
            response = await self.http_client.get(
                "/api/v1/_e2e/contract/events",
                params={"topic": topic},
            )
            assert response.status_code == 200, response.text
            await asyncio.sleep(duration)
            return list(response.json().get("items", []))
        deadline = asyncio.get_running_loop().time() + duration
        events: list[dict[str, Any]] = []
        while asyncio.get_running_loop().time() < deadline:
            assert self.consumer is not None
            batches = await self.consumer.getmany(timeout_ms=200, max_records=50)
            for records in batches.values():
                events.extend(self._decode_record(record) for record in records)
        return events

    async def expect_no_event(
        self,
        topic: str,
        predicate: Callable[[dict[str, Any]], bool],
        duration: float,
    ) -> None:
        events = await self.collect(topic, duration)
        assert not any(predicate(event) for event in events)

    @staticmethod
    def _decode_record(record: Any) -> dict[str, Any]:
        if isinstance(record.value, bytes):
            return json.loads(record.value.decode("utf-8"))
        return dict(record.value)


@pytest.fixture(scope="function")
async def kafka_consumer(
    kafka_bootstrap: str,
    http_client,
) -> AsyncIterator[KafkaTestConsumer]:
    async with KafkaTestConsumer(kafka_bootstrap, http_client=http_client) as consumer:
        yield consumer
