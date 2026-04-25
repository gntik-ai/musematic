from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.notifications.models import DeliveryOutcome
from platform.notifications.workers.webhook_retry_worker import run_webhook_retry_scan
from types import SimpleNamespace
from uuid import uuid4

import pytest


class RepoStub:
    def __init__(self, delivery: SimpleNamespace) -> None:
        self.delivery = delivery
        self.updates: list[tuple[object, dict[str, object]]] = []

    async def list_due_deliveries(self, now, limit):
        del now, limit
        return [self.delivery]

    async def update_delivery_status(self, delivery_id, **fields):
        self.updates.append((delivery_id, fields))


class RedisStub:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def set(self, key, value, *, ex, nx):
        del value, ex, nx
        return key

    async def delete(self, key):
        self.deleted.append(key)


class SecretsStub:
    async def read_secret(self, path):
        del path
        return {"hmac_secret": "secret"}


class DelivererStub:
    def __init__(self, outcome: DeliveryOutcome, detail: str | None = None) -> None:
        self.outcome = outcome
        self.detail = detail

    async def send_signed(self, **kwargs):
        del kwargs
        return self.outcome, self.detail, uuid4()


class ProducerStub:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def publish(self, **kwargs) -> None:
        self.events.append(kwargs)


def _delivery() -> SimpleNamespace:
    webhook = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        url="https://hooks.example.com/events",
        active=True,
        signing_secret_ref="secret/path",
        retry_policy={
            "max_retries": 3,
            "backoff_seconds": [60, 300],
            "total_window_seconds": 86_400,
        },
    )
    return SimpleNamespace(
        id=uuid4(),
        webhook_id=webhook.id,
        event_id=uuid4(),
        event_type="execution.failed",
        payload={"event": "execution.failed"},
        attempts=0,
        created_at=datetime.now(UTC),
        webhook=webhook,
    )


@pytest.mark.asyncio
async def test_retry_worker_marks_successful_delivery_delivered() -> None:
    delivery = _delivery()
    repo = RepoStub(delivery)
    redis = RedisStub()

    count = await run_webhook_retry_scan(
        repo=repo,
        redis=redis,
        secrets=SecretsStub(),
        deliverer=DelivererStub(DeliveryOutcome.success),
        settings=PlatformSettings(),
    )

    assert count == 1
    assert repo.updates[0][1]["status"] == "delivered"
    assert repo.updates[0][1]["attempts"] == 1
    assert redis.deleted


@pytest.mark.asyncio
async def test_retry_worker_dead_letters_permanent_failure() -> None:
    delivery = _delivery()
    repo = RepoStub(delivery)
    producer = ProducerStub()

    await run_webhook_retry_scan(
        repo=repo,
        redis=RedisStub(),
        secrets=SecretsStub(),
        deliverer=DelivererStub(DeliveryOutcome.failed, "4xx_permanent"),
        settings=PlatformSettings(),
        producer=producer,
    )

    assert repo.updates[0][1]["status"] == "dead_letter"
    assert repo.updates[0][1]["failure_reason"] == "4xx_permanent"
    assert producer.events[0]["event_type"] == "notifications.delivery.dead_lettered"
