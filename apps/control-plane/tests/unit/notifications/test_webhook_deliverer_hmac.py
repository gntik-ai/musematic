from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.notifications.channel_router import ChannelDelivererRegistry, ChannelRouter
from platform.notifications.deliverers.email_deliverer import EmailDeliverer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.models import DeliveryOutcome
from platform.notifications.workers.webhook_retry_worker import run_webhook_retry_scan
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest


class _AsyncClientStub:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> _AsyncClientStub:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> httpx.Response:
        self.calls.append({"url": url, "content": content, "headers": headers})
        return self.responses.pop(0)


class _MutableDeliveryRepo:
    def __init__(self, delivery: SimpleNamespace) -> None:
        self.delivery = delivery
        self.updates: list[dict[str, Any]] = []

    async def list_due_deliveries(self, now: datetime, limit: int) -> list[SimpleNamespace]:
        del now, limit
        if self.delivery.status in {"delivered", "dead_letter"}:
            return []
        return [self.delivery]

    async def update_delivery_status(self, delivery_id: UUID, **fields: Any) -> SimpleNamespace:
        assert delivery_id == self.delivery.id
        self.updates.append(fields)
        for key, value in fields.items():
            setattr(self.delivery, key, value)
        return self.delivery


class _RedisStub:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.deleted: list[str] = []

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        del key, value, ex, nx
        return self.acquired

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


class _SecretsStub:
    async def read_secret(self, path: str) -> dict[str, str]:
        del path
        return {"hmac_secret": "shared-secret"}


class _SequenceDeliverer:
    def __init__(self, outcomes: list[tuple[DeliveryOutcome, str | None]]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def send_signed(self, **kwargs: Any) -> tuple[DeliveryOutcome, str | None, UUID]:
        self.calls.append(kwargs)
        outcome, detail = self.outcomes.pop(0)
        return outcome, detail, kwargs["event_id"]


class _DlpStub:
    def __init__(self, action: str = "block") -> None:
        self.action = action

    async def scan_outbound(self, **kwargs: Any) -> dict[str, str]:
        del kwargs
        return {"action": self.action}


class _ResidencyStub:
    async def resolve_region_for_url(self, url: str) -> str | None:
        del url
        return None

    async def check_egress(self, workspace_id: UUID, region: str | None) -> bool:
        del workspace_id, region
        return True


class _WorkspaceEventRepo:
    def __init__(self, webhook: SimpleNamespace) -> None:
        self.webhook = webhook
        self.deliveries: list[SimpleNamespace] = []
        self.updates: list[dict[str, Any]] = []

    async def list_active_outbound_webhooks(
        self,
        workspace_id: UUID,
        event_type: str,
    ) -> list[SimpleNamespace]:
        del workspace_id
        return [self.webhook] if event_type in self.webhook.event_types else []

    async def insert_delivery(self, **fields: Any) -> SimpleNamespace:
        delivery = SimpleNamespace(id=uuid4(), **fields)
        self.deliveries.append(delivery)
        return delivery

    async def get_webhook_delivery_by_idempotency(
        self,
        webhook_id: UUID,
        idempotency_key: UUID,
    ) -> SimpleNamespace | None:
        for delivery in self.deliveries:
            if (
                delivery.webhook_id == webhook_id
                and delivery.idempotency_key == idempotency_key
                and getattr(delivery, "replayed_from", None) is None
            ):
                return delivery
        return None

    async def update_delivery_status(self, delivery_id: UUID, **fields: Any) -> SimpleNamespace:
        self.updates.append(fields)
        delivery = self.deliveries[-1]
        assert delivery.id == delivery_id
        for key, value in fields.items():
            setattr(delivery, key, value)
        return delivery


@pytest.mark.asyncio
async def test_signed_delivery_has_verifiable_hmac_and_stable_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _AsyncClientStub([httpx.Response(204), httpx.Response(204)])
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0, follow_redirects=False: client,
    )
    deliverer = WebhookDeliverer()
    webhook_id = uuid4()
    event_id = uuid4()

    first = await deliverer.send_signed(
        webhook_id=webhook_id,
        event_id=event_id,
        webhook_url="https://hooks.example.com/events",
        payload={"z": 1, "a": "same"},
        secret="shared-secret",
        platform_version="test",
    )
    second = await deliverer.send_signed(
        webhook_id=webhook_id,
        event_id=event_id,
        webhook_url="https://hooks.example.com/events",
        payload={"a": "same", "z": 1},
        secret="shared-secret",
        platform_version="test",
    )

    assert first[0] == DeliveryOutcome.success
    assert first[2] == second[2]
    headers = client.calls[0]["headers"]
    body = client.calls[0]["content"]
    signed = f"{headers['X-Musematic-Timestamp']}.".encode("ascii") + body
    expected = hmac.new(b"shared-secret", signed, hashlib.sha256).hexdigest()
    assert headers["X-Musematic-Signature"] == f"sha256={expected}"


@pytest.mark.asyncio
async def test_retry_worker_handles_503_503_200_sequence_with_stable_event_key() -> None:
    delivery = _delivery()
    repo = _MutableDeliveryRepo(delivery)
    deliverer = _SequenceDeliverer(
        [
            (DeliveryOutcome.timed_out, "server error"),
            (DeliveryOutcome.timed_out, "server error"),
            (DeliveryOutcome.success, None),
        ]
    )

    for _ in range(3):
        await run_webhook_retry_scan(
            repo=repo,
            redis=_RedisStub(),
            secrets=_SecretsStub(),
            deliverer=deliverer,
            settings=PlatformSettings(),
        )

    assert delivery.status == "delivered"
    assert delivery.attempts == 3
    assert {call["event_id"] for call in deliverer.calls} == {delivery.event_id}


@pytest.mark.asyncio
async def test_retry_worker_dead_letters_4xx_inactive_and_exhausted_window() -> None:
    for delivery, deliverer, expected_reason in [
        (
            _delivery(),
            _SequenceDeliverer([(DeliveryOutcome.failed, "4xx_permanent")]),
            "4xx_permanent",
        ),
        (_delivery(active=False), _SequenceDeliverer([]), "webhook_inactive"),
        (
            _delivery(created_at=datetime.now(UTC) - timedelta(days=2)),
            _SequenceDeliverer([]),
            "retry_window_exhausted",
        ),
    ]:
        repo = _MutableDeliveryRepo(delivery)

        await run_webhook_retry_scan(
            repo=repo,
            redis=_RedisStub(),
            secrets=_SecretsStub(),
            deliverer=deliverer,
            settings=PlatformSettings(),
        )

        assert delivery.status == "dead_letter"
        assert delivery.failure_reason == expected_reason


@pytest.mark.asyncio
async def test_retry_worker_honours_retry_after_and_redis_lease() -> None:
    delivery = _delivery()
    repo = _MutableDeliveryRepo(delivery)
    await run_webhook_retry_scan(
        repo=repo,
        redis=_RedisStub(),
        secrets=_SecretsStub(),
        deliverer=_SequenceDeliverer(
            [(DeliveryOutcome.timed_out, "rate_limited; retry_after=30")]
        ),
        settings=PlatformSettings(),
    )

    assert delivery.status == "failed"
    assert delivery.next_attempt_at is not None
    assert delivery.last_attempt_at is not None
    assert (delivery.next_attempt_at - delivery.last_attempt_at).total_seconds() == 30

    locked_delivery = _delivery()
    locked_deliverer = _SequenceDeliverer([(DeliveryOutcome.success, None)])
    count = await run_webhook_retry_scan(
        repo=_MutableDeliveryRepo(locked_delivery),
        redis=_RedisStub(acquired=False),
        secrets=_SecretsStub(),
        deliverer=locked_deliverer,
        settings=PlatformSettings(),
    )

    assert count == 0
    assert locked_deliverer.calls == []


@pytest.mark.asyncio
async def test_workspace_event_dlp_block_dead_letters_without_http_dispatch() -> None:
    webhook = _webhook()
    repo = _WorkspaceEventRepo(webhook)
    deliverer = _SequenceDeliverer([(DeliveryOutcome.success, None)])
    router = ChannelRouter(
        repo=repo,
        accounts_repo=SimpleNamespace(),
        workspaces_service=None,
        dlp_service=_DlpStub(),
        residency_service=_ResidencyStub(),
        secrets=_SecretsStub(),
        audit_chain=SimpleNamespace(),
        producer=None,
        settings=PlatformSettings(),
        deliverers=ChannelDelivererRegistry(
            email=EmailDeliverer(),
            webhook=deliverer,
        ),
    )

    result = await router.route_workspace_event(
        {"event_id": uuid4(), "event_type": "execution.failed"},
        webhook.workspace_id,
    )

    assert result[0].status == "dead_letter"
    assert repo.deliveries[0].failure_reason == "dlp_blocked"
    assert deliverer.calls == []


@pytest.mark.asyncio
async def test_workspace_event_duplicate_returns_existing_delivery_without_reinsert() -> None:
    webhook = _webhook()
    repo = _WorkspaceEventRepo(webhook)
    deliverer = _SequenceDeliverer([(DeliveryOutcome.success, None)])
    router = ChannelRouter(
        repo=repo,
        accounts_repo=SimpleNamespace(),
        workspaces_service=None,
        dlp_service=_DlpStub("allow"),
        residency_service=_ResidencyStub(),
        secrets=_SecretsStub(),
        audit_chain=SimpleNamespace(),
        producer=None,
        settings=PlatformSettings(),
        deliverers=ChannelDelivererRegistry(
            email=EmailDeliverer(),
            webhook=deliverer,
        ),
    )
    envelope = {"event_id": uuid4(), "event_type": "execution.failed"}

    first = await router.route_workspace_event(envelope, webhook.workspace_id)
    duplicate = await router.route_workspace_event(envelope, webhook.workspace_id)

    assert first[0].delivery_id == duplicate[0].delivery_id
    assert first[0].status == "delivered"
    assert duplicate[0].status == "delivered"
    assert len(repo.deliveries) == 1
    assert len(deliverer.calls) == 1


def _webhook(*, active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        url="https://hooks.example.com/events",
        active=active,
        signing_secret_ref="secret/path",
        event_types=["execution.failed"],
        region_pinned_to=None,
        retry_policy={
            "max_retries": 3,
            "backoff_seconds": [60, 300, 900],
            "total_window_seconds": 86_400,
        },
    )


def _delivery(
    *,
    active: bool = True,
    created_at: datetime | None = None,
) -> SimpleNamespace:
    webhook = _webhook(active=active)
    return SimpleNamespace(
        id=uuid4(),
        webhook_id=webhook.id,
        event_id=uuid4(),
        event_type="execution.failed",
        payload={"event_type": "execution.failed"},
        status="pending",
        attempts=0,
        failure_reason=None,
        next_attempt_at=None,
        last_attempt_at=None,
        dead_lettered_at=None,
        created_at=created_at or datetime.now(UTC),
        webhook=webhook,
    )
