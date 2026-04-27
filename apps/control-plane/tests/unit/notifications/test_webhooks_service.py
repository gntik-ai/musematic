from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.notifications.exceptions import (
    DeadLetterNotReplayableError,
    InvalidWebhookUrlError,
    QuotaExceededError,
    ResidencyViolationError,
    WebhookInactiveError,
    WebhookNotFoundError,
)
from platform.notifications.models import DeliveryOutcome
from platform.notifications.schemas import OutboundWebhookCreate, OutboundWebhookUpdate
from platform.notifications.webhooks_service import (
    OutboundWebhookService,
    _retry_delay_seconds,
    _write_secret_values,
)
from platform.notifications.webhooks_service import (
    _read_hmac_secret as _read_webhook_hmac_secret,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest


class RepoStub:
    def __init__(self) -> None:
        self.created: SimpleNamespace | None = None
        self.updated: list[tuple[object, dict[str, object]]] = []
        self.deliveries: list[SimpleNamespace] = []

    async def count_active_webhooks(self, workspace_id):
        del workspace_id
        return 0

    async def create_outbound_webhook(self, **fields):
        now = datetime.now(UTC)
        self.created = SimpleNamespace(
            id=uuid4(),
            last_rotated_at=None,
            created_at=now,
            updated_at=now,
            **fields,
        )
        return self.created

    async def update_outbound_webhook(self, webhook_id, **fields):
        if self.created is None:
            return None
        self.updated.append((webhook_id, fields))
        for key, value in fields.items():
            setattr(self.created, key, value)
        return self.created

    async def get_outbound_webhook(self, webhook_id):
        del webhook_id
        return self.created

    async def list_outbound_webhooks(self, workspace_id):
        del workspace_id
        return [] if self.created is None else [self.created]

    async def insert_delivery(self, **fields):
        now = datetime.now(UTC)
        delivery = SimpleNamespace(
            id=uuid4(),
            last_attempt_at=None,
            last_response_status=None,
            replayed_from=None,
            replayed_by=None,
            created_at=now,
            updated_at=now,
            **fields,
        )
        self.deliveries.append(delivery)
        return delivery

    async def update_delivery_status(self, delivery_id, **fields):
        for delivery in self.deliveries:
            if delivery.id == delivery_id:
                for key, value in fields.items():
                    setattr(delivery, key, value)
                delivery.updated_at = datetime.now(UTC)
                return delivery
        return None

    async def get_delivery(self, delivery_id, include_webhook=False):
        del include_webhook
        for delivery in self.deliveries:
            if delivery.id == delivery_id:
                return delivery
        return None


class SecretProviderStub:
    def __init__(self) -> None:
        self.writes: list[tuple[str, dict[str, object]]] = []

    async def write_secret(self, path, payload):
        self.writes.append((path, payload))

    async def read_secret(self, path):
        del path
        return {"hmac_secret": "secret"}


class LegacySecretProviderStub:
    def __init__(self) -> None:
        self.writes: list[tuple[str, dict[str, str]]] = []

    async def put(self, path, payload):
        self.writes.append((path, payload))

    async def get(self, path, *, key):
        assert path == "secret/path"
        assert key == "hmac_secret"
        return "legacy-secret"


class NonStringGetSecretProviderStub:
    async def get(self, path, *, key):
        del path, key
        return None

    async def read_secret(self, path):
        del path
        return {"hmac_secret": "fallback-secret"}


class MissingHmacSecretProviderStub:
    async def get(self, path, *, key):
        del path, key
        return None

    async def read_secret(self, path):
        del path
        return {}


class ResidencyStub:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    async def resolve_region_for_url(self, url):
        del url
        return "eu"

    async def check_egress(self, workspace_id, region):
        del workspace_id, region
        return self.allowed


class DlpStub:
    def __init__(self, action: str = "allow") -> None:
        self.action = action

    async def scan_outbound(self, **kwargs):
        del kwargs
        return {"action": self.action}


class DlpObjectStub:
    def __init__(self, action: str = "allow") -> None:
        self.action = action

    async def scan_outbound(self, **kwargs):
        del kwargs
        return SimpleNamespace(action=self.action)


class WebhookDelivererStub:
    def __init__(
        self,
        outcome: DeliveryOutcome = DeliveryOutcome.success,
        error_detail: str | None = None,
    ) -> None:
        self.outcome = outcome
        self.error_detail = error_detail
        self.calls: list[dict[str, object]] = []

    async def send_signed(self, **kwargs):
        self.calls.append(kwargs)
        return self.outcome, self.error_detail, kwargs["event_id"]


def _service(
    *,
    repo: RepoStub | None = None,
    secrets: SecretProviderStub | None = None,
    residency: ResidencyStub | None = None,
    settings: PlatformSettings | None = None,
    dlp: DlpStub | None = None,
    deliverer: WebhookDelivererStub | None = None,
):
    return OutboundWebhookService(
        repo=repo or RepoStub(),
        settings=settings or PlatformSettings(),
        secrets=secrets or SecretProviderStub(),
        residency_service=residency or ResidencyStub(),
        dlp_service=dlp or DlpStub(),
        deliverer=deliverer or WebhookDelivererStub(),
    )


@pytest.mark.asyncio
async def test_create_webhook_stores_secret_and_returns_it_once() -> None:
    repo = RepoStub()
    secrets = SecretProviderStub()
    workspace_id = uuid4()

    response = await _service(repo=repo, secrets=secrets).create(
        OutboundWebhookCreate(
            workspace_id=workspace_id,
            name="CRM",
            url="https://hooks.example.com/events",
            event_types=["execution.failed"],
        ),
        actor_id=uuid4(),
    )

    assert response.workspace_id == workspace_id
    assert response.signing_secret
    assert response.signing_secret_ref.endswith(str(response.id))
    assert secrets.writes == [
        (response.signing_secret_ref, {"hmac_secret": response.signing_secret})
    ]


@pytest.mark.asyncio
async def test_create_webhook_rejects_http_and_residency_violation() -> None:
    with pytest.raises(InvalidWebhookUrlError):
        await _service().create(
            OutboundWebhookCreate(
                workspace_id=uuid4(),
                name="Local",
                url="http://hooks.example.com/events",
                event_types=["execution.failed"],
            ),
            actor_id=uuid4(),
        )

    with pytest.raises(ResidencyViolationError):
        await _service(residency=ResidencyStub(False)).create(
            OutboundWebhookCreate(
                workspace_id=uuid4(),
                name="Blocked",
                url="https://hooks.example.com/events",
                event_types=["execution.failed"],
            ),
            actor_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_rotate_secret_does_not_return_secret_material() -> None:
    repo = RepoStub()
    secrets = SecretProviderStub()
    created = await _service(repo=repo, secrets=secrets).create(
        OutboundWebhookCreate(
            workspace_id=uuid4(),
            name="CRM",
            url="https://hooks.example.com/events",
            event_types=["execution.failed"],
        ),
        actor_id=uuid4(),
    )

    rotated = await _service(repo=repo, secrets=secrets).rotate_secret(created.id)

    assert not hasattr(rotated, "signing_secret")
    assert rotated.last_rotated_at is not None
    assert len(secrets.writes) == 2


@pytest.mark.asyncio
async def test_send_test_event_dispatches_signed_delivery_and_returns_delivery_row() -> None:
    repo = RepoStub()
    deliverer = WebhookDelivererStub()
    created = await _service(repo=repo, deliverer=deliverer).create(
        OutboundWebhookCreate(
            workspace_id=uuid4(),
            name="CRM",
            url="https://hooks.example.com/events",
            event_types=["execution.failed"],
        ),
        actor_id=uuid4(),
    )

    delivery = await _service(repo=repo, deliverer=deliverer).send_test_event(
        created.id,
        actor_id=uuid4(),
    )

    assert delivery.status == "delivered"
    assert delivery.attempts == 1
    assert delivery.event_type == "notifications.webhook.test"
    assert deliverer.calls[0]["webhook_url"] == "https://hooks.example.com/events"
    assert deliverer.calls[0]["secret"] == "secret"


@pytest.mark.asyncio
async def test_send_test_event_dead_letters_policy_or_inactive_webhook() -> None:
    repo = RepoStub()
    created = await _service(repo=repo).create(
        OutboundWebhookCreate(
            workspace_id=uuid4(),
            name="CRM",
            url="https://hooks.example.com/events",
            event_types=["execution.failed"],
        ),
        actor_id=uuid4(),
    )

    blocked = await _service(repo=repo, dlp=DlpStub("block")).send_test_event(
        created.id,
        actor_id=uuid4(),
    )
    assert blocked.status == "dead_letter"
    assert blocked.failure_reason == "dlp_blocked"

    await _service(repo=repo).deactivate(created.id)
    with pytest.raises(WebhookInactiveError):
        await _service(repo=repo).send_test_event(created.id, actor_id=uuid4())


@pytest.mark.asyncio
async def test_send_test_event_honours_retry_after_on_transient_failure() -> None:
    repo = RepoStub()
    deliverer = WebhookDelivererStub(
        DeliveryOutcome.timed_out,
        "rate_limited; retry_after=30",
    )
    created = await _service(repo=repo, deliverer=deliverer).create(
        OutboundWebhookCreate(
            workspace_id=uuid4(),
            name="CRM",
            url="https://hooks.example.com/events",
            event_types=["execution.failed"],
        ),
        actor_id=uuid4(),
    )

    delivery = await _service(repo=repo, deliverer=deliverer).send_test_event(
        created.id,
        actor_id=uuid4(),
    )

    assert delivery.status == "failed"
    assert delivery.next_attempt_at is not None
    assert 0 <= (delivery.next_attempt_at - delivery.last_attempt_at).total_seconds() <= 31


@pytest.mark.asyncio
async def test_service_list_get_update_deactivate_and_not_found_edges() -> None:
    repo = RepoStub()
    service = _service(repo=repo)
    webhook_id = uuid4()

    with pytest.raises(WebhookNotFoundError):
        await service.get(webhook_id)
    with pytest.raises(WebhookNotFoundError):
        await service.update(webhook_id, OutboundWebhookUpdate(active=False))
    with pytest.raises(WebhookNotFoundError):
        await service.rotate_secret(webhook_id)
    with pytest.raises(WebhookNotFoundError):
        await service.deactivate(webhook_id)
    with pytest.raises(WebhookNotFoundError):
        await service.send_test_event(webhook_id, actor_id=uuid4())

    settings = PlatformSettings()
    settings.notifications.webhooks_per_workspace_max = 0
    with pytest.raises(QuotaExceededError):
        await _service(repo=repo, settings=settings).create(
            OutboundWebhookCreate(
                workspace_id=uuid4(),
                name="Too many",
                url="https://hooks.example.com/events",
                event_types=["execution.failed"],
            ),
            actor_id=uuid4(),
        )

    created = await service.create(
        OutboundWebhookCreate(
            workspace_id=uuid4(),
            name="CRM",
            url="https://hooks.example.com/events",
            event_types=["execution.failed"],
        ),
        actor_id=uuid4(),
    )
    listed = await service.list(created.workspace_id)
    resolved = await service.get(created.id)
    updated = await service.update(
        created.id,
        OutboundWebhookUpdate(
            url="https://hooks.example.com/updated",
            event_types=["execution.completed"],
        ),
    )
    deactivated = await service.deactivate(created.id)

    assert listed[0].id == created.id
    assert resolved.id == created.id
    assert updated.url == "https://hooks.example.com/updated"
    assert updated.event_types == ["execution.completed"]
    assert deactivated.active is False


@pytest.mark.asyncio
async def test_send_test_event_dead_letters_deliverer_failure_and_region_policy() -> None:
    repo = RepoStub()
    created = await _service(repo=repo).create(
        OutboundWebhookCreate(
            workspace_id=uuid4(),
            name="CRM",
            url="https://hooks.example.com/events",
            event_types=["execution.failed"],
            region_pinned_to="eu",
        ),
        actor_id=uuid4(),
    )

    failed = await _service(
        repo=repo,
        deliverer=WebhookDelivererStub(DeliveryOutcome.failed, "4xx_permanent"),
    ).send_test_event(created.id, actor_id=uuid4())
    assert failed.status == "dead_letter"
    assert failed.failure_reason == "4xx_permanent"
    dead_letter = await _service(repo=repo).get_dead_letter(failed.id)
    assert dead_letter.id == failed.id

    region_blocked = await _service(
        repo=repo,
        dlp=DlpObjectStub("allow"),
        residency=ResidencyStub(False),
    ).send_test_event(created.id, actor_id=uuid4())
    assert region_blocked.status == "dead_letter"
    assert region_blocked.failure_reason == "residency_violation"


@pytest.mark.asyncio
async def test_send_test_event_allows_missing_dlp_service() -> None:
    repo = RepoStub()
    deliverer = WebhookDelivererStub()
    service = OutboundWebhookService(
        repo=repo,
        settings=PlatformSettings(),
        secrets=SecretProviderStub(),
        residency_service=ResidencyStub(),
        dlp_service=None,
        deliverer=deliverer,
    )
    created = await service.create(
        OutboundWebhookCreate(
            workspace_id=uuid4(),
            name="CRM",
            url="https://hooks.example.com/events",
            event_types=["execution.failed"],
        ),
        actor_id=uuid4(),
    )

    delivery = await service.send_test_event(created.id, actor_id=uuid4())

    assert delivery.status == "delivered"


@pytest.mark.asyncio
async def test_dead_letter_methods_report_not_found_and_non_replayable_edges() -> None:
    repo = RepoStub()
    service = _service(repo=repo)
    delivery_id = uuid4()

    with pytest.raises(WebhookNotFoundError):
        await service.get_dead_letter(delivery_id)
    with pytest.raises(WebhookNotFoundError):
        await service.replay_dead_letter(delivery_id, actor_id=uuid4())
    with pytest.raises(WebhookNotFoundError):
        await service.resolve_dead_letter(delivery_id, actor_id=uuid4(), resolution="resolved")

    repo.deliveries.append(SimpleNamespace(id=delivery_id, status="delivered"))

    with pytest.raises(DeadLetterNotReplayableError):
        await service.resolve_dead_letter(delivery_id, actor_id=uuid4(), resolution="resolved")


def test_webhook_retry_delay_helper_handles_bad_retry_after_and_empty_policy() -> None:
    settings = PlatformSettings()

    assert _retry_delay_seconds("retry_after=bad", {"backoff_seconds": [7]}, settings) == 7
    assert _retry_delay_seconds(None, {"backoff_seconds": []}, settings) == 60
    assert _retry_delay_seconds("retry_after=-5", {"backoff_seconds": [7]}, settings) == 0


@pytest.mark.asyncio
async def test_webhook_secret_helpers_support_legacy_get_put_and_errors() -> None:
    provider = LegacySecretProviderStub()

    await _write_secret_values(provider, "secret/path", {"hmac_secret": "secret"})

    assert provider.writes == [("secret/path", {"hmac_secret": "secret"})]
    assert await _read_webhook_hmac_secret(provider, "secret/path") == "legacy-secret"
    assert (
        await _read_webhook_hmac_secret(NonStringGetSecretProviderStub(), "secret/path")
        == "fallback-secret"
    )

    with pytest.raises(AttributeError):
        await _write_secret_values(object(), "secret/path", {"hmac_secret": "secret"})
    with pytest.raises(AttributeError):
        await _read_webhook_hmac_secret(object(), "secret/path")
    with pytest.raises(AttributeError):
        await _read_webhook_hmac_secret(MissingHmacSecretProviderStub(), "secret/path")
