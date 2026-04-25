from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.notifications.channel_router import ChannelDelivererRegistry, ChannelRouter
from platform.notifications.models import (
    AlertDeliveryOutcome,
    DeliveryMethod,
    DeliveryOutcome,
    UserAlert,
    UserAlertSettings,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest


class RepoStub:
    def __init__(
        self,
        *,
        configs: list[SimpleNamespace] | None = None,
        legacy_method: DeliveryMethod = DeliveryMethod.in_app,
        legacy_webhook_url: str | None = None,
    ) -> None:
        self.configs = list(configs or [])
        self.legacy_method = legacy_method
        self.legacy_webhook_url = legacy_webhook_url
        self.list_called = False
        self.outcomes: list[dict[str, object]] = []

    async def list_enabled_channel_configs(self, user_id):
        del user_id
        self.list_called = True
        return self.configs

    async def get_settings(self, user_id):
        return UserAlertSettings(
            id=uuid4(),
            user_id=user_id,
            state_transitions=["any_to_failed"],
            delivery_method=self.legacy_method,
            webhook_url=self.legacy_webhook_url,
        )

    async def ensure_alert_delivery_outcome(self, alert_id, delivery_method):
        return AlertDeliveryOutcome(
            id=uuid4(),
            alert_id=alert_id,
            delivery_method=delivery_method,
            attempt_count=1,
        )

    async def update_delivery_outcome(self, outcome_id, **fields):
        self.outcomes.append({"outcome_id": outcome_id, **fields})


class WorkspaceEventRepoStub(RepoStub):
    def __init__(self, webhooks: list[SimpleNamespace]) -> None:
        super().__init__()
        self.webhooks = webhooks
        self.deliveries: list[dict[str, object]] = []

    async def list_active_outbound_webhooks(self, workspace_id, event_type):
        del workspace_id
        return [webhook for webhook in self.webhooks if event_type in webhook.event_types]

    async def insert_delivery(self, **fields):
        delivery = SimpleNamespace(id=uuid4(), **fields)
        self.deliveries.append(fields)
        return delivery

    async def update_delivery_status(self, delivery_id, **fields):
        self.outcomes.append({"delivery_id": delivery_id, **fields})


class DlpStub:
    def __init__(self, verdict: object | None = None) -> None:
        self.verdict = verdict or {"action": "allow"}

    async def scan_outbound(self, **kwargs):
        del kwargs
        return self.verdict


class ResidencyStub:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    async def resolve_region_for_url(self, url):
        del url
        return "eu"

    async def check_egress(self, workspace_id, region):
        del workspace_id, region
        return self.allowed


class EmailDelivererStub:
    def __init__(self) -> None:
        self.calls: list[tuple[UserAlert, str, object]] = []

    async def send(self, alert, recipient_email, smtp_settings):
        self.calls.append((alert, recipient_email, smtp_settings))
        return DeliveryOutcome.success


class WebhookDelivererStub:
    def __init__(self) -> None:
        self.calls: list[tuple[UserAlert, str]] = []

    async def send(self, alert, webhook_url):
        self.calls.append((alert, webhook_url))
        return DeliveryOutcome.success, None

    async def send_signed(self, **kwargs):
        self.calls.append((kwargs["payload"], kwargs["webhook_url"]))
        return DeliveryOutcome.success, None, kwargs["event_id"]


class SecretsStub:
    async def read_secret(self, path):
        del path
        return {"hmac_secret": "secret"}


class ProducerStub:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def publish(self, **kwargs) -> None:
        self.events.append(kwargs)


def _settings(enabled: bool = True) -> PlatformSettings:
    settings = PlatformSettings()
    settings.notifications.multi_channel_enabled = enabled
    return settings


def _alert() -> UserAlert:
    alert = UserAlert(
        id=uuid4(),
        user_id=uuid4(),
        interaction_id=None,
        source_reference=None,
        alert_type="attention_request",
        title="Attention requested",
        body="Review account 123",
        urgency="medium",
        read=False,
    )
    alert.created_at = datetime.now(UTC)
    alert.updated_at = alert.created_at
    return alert


def _recipient():
    return SimpleNamespace(id=uuid4(), email="user@example.com")


def _config(
    channel_type: DeliveryMethod,
    target: str,
    *,
    alert_type_filter: list[str] | None = None,
    severity_floor: str | None = None,
    quiet_hours: dict[str, object] | None = None,
):
    return SimpleNamespace(
        channel_type=channel_type,
        target=target,
        quiet_hours=quiet_hours,
        alert_type_filter=alert_type_filter,
        severity_floor=severity_floor,
        extra=None,
    )


def _router(
    repo: RepoStub,
    *,
    settings: PlatformSettings | None = None,
    dlp: DlpStub | None = None,
    residency: ResidencyStub | None = None,
    email: EmailDelivererStub | None = None,
    webhook: WebhookDelivererStub | None = None,
    producer: ProducerStub | None = None,
) -> ChannelRouter:
    return ChannelRouter(
        repo=repo,
        accounts_repo=SimpleNamespace(),
        workspaces_service=None,
        dlp_service=dlp or DlpStub(),
        residency_service=residency or ResidencyStub(),
        secrets=SecretsStub(),
        audit_chain=SimpleNamespace(),
        producer=producer,
        settings=settings or _settings(),
        deliverers=ChannelDelivererRegistry(
            email=email or EmailDelivererStub(),
            webhook=webhook or WebhookDelivererStub(),
        ),
    )


@pytest.mark.asyncio
async def test_route_fans_out_to_enabled_verified_channels_and_applies_filters() -> None:
    email = EmailDelivererStub()
    webhook = WebhookDelivererStub()
    repo = RepoStub(
        configs=[
            _config(DeliveryMethod.email, "user@example.com"),
            _config(DeliveryMethod.webhook, "https://hooks.example.com/alerts"),
            _config(DeliveryMethod.email, "filtered@example.com", alert_type_filter=["other"]),
            _config(DeliveryMethod.email, "floor@example.com", severity_floor="high"),
        ]
    )

    result = await _router(repo, email=email, webhook=webhook).route(
        _alert(),
        _recipient(),
        workspace_id=uuid4(),
        severity="medium",
    )

    assert [attempt.channel_type for attempt in result.attempts] == [
        DeliveryMethod.email,
        DeliveryMethod.webhook,
    ]
    assert [call[1] for call in email.calls] == ["user@example.com"]
    assert [call[1] for call in webhook.calls] == ["https://hooks.example.com/alerts"]


@pytest.mark.asyncio
async def test_route_honours_quiet_hours_and_critical_bypass() -> None:
    qh = {"start": "00:00", "end": "23:59", "timezone": "UTC"}
    repo = RepoStub(configs=[_config(DeliveryMethod.email, "user@example.com", quiet_hours=qh)])
    email = EmailDelivererStub()

    quiet_result = await _router(repo, email=email).route(_alert(), _recipient(), severity="medium")
    critical_result = await _router(repo, email=email).route(
        _alert(),
        _recipient(),
        severity="critical",
    )

    assert quiet_result.attempts == []
    assert [attempt.outcome for attempt in critical_result.attempts] == ["success"]


@pytest.mark.asyncio
async def test_route_records_dlp_block_and_redacts_payload_before_delivery() -> None:
    blocked_repo = RepoStub(configs=[_config(DeliveryMethod.email, "user@example.com")])
    blocked = await _router(blocked_repo, dlp=DlpStub({"action": "block"})).route(
        _alert(),
        _recipient(),
    )
    assert blocked.attempts[0].error_detail == "dlp_blocked"
    assert blocked_repo.outcomes[0]["error_detail"] == "dlp_blocked"

    email = EmailDelivererStub()
    redacted_repo = RepoStub(configs=[_config(DeliveryMethod.email, "user@example.com")])
    await _router(
        redacted_repo,
        dlp=DlpStub({"action": "redact", "redacted_payload": {"body": "[REDACTED]"}}),
        email=email,
    ).route(_alert(), _recipient())
    assert email.calls[0][0].body == "[REDACTED]"


@pytest.mark.asyncio
async def test_route_blocks_webhook_residency_violation() -> None:
    repo = RepoStub(configs=[_config(DeliveryMethod.webhook, "https://hooks.example.com")])
    webhook = WebhookDelivererStub()

    result = await _router(repo, residency=ResidencyStub(False), webhook=webhook).route(
        _alert(),
        _recipient(),
        workspace_id=uuid4(),
    )

    assert result.attempts[0].error_detail == "residency_violation"
    assert webhook.calls == []


@pytest.mark.asyncio
async def test_route_feature_flag_fallback_paths() -> None:
    recipient = _recipient()
    email = EmailDelivererStub()
    flag_off_repo = RepoStub(
        configs=[_config(DeliveryMethod.webhook, "https://ignored.example.com")],
        legacy_method=DeliveryMethod.email,
    )
    await _router(flag_off_repo, settings=_settings(False), email=email).route(_alert(), recipient)
    assert flag_off_repo.list_called is False
    assert email.calls[0][1] == recipient.email

    webhook = WebhookDelivererStub()
    no_rows_repo = RepoStub(
        configs=[],
        legacy_method=DeliveryMethod.webhook,
        legacy_webhook_url="https://legacy.example.com",
    )
    await _router(no_rows_repo, webhook=webhook).route(_alert(), recipient)
    assert webhook.calls[0][1] == "https://legacy.example.com"

    with_rows_repo = RepoStub(
        configs=[_config(DeliveryMethod.email, "row@example.com")],
        legacy_method=DeliveryMethod.webhook,
        legacy_webhook_url="https://ignored.example.com",
    )
    email = EmailDelivererStub()
    webhook = WebhookDelivererStub()
    await _router(with_rows_repo, email=email, webhook=webhook).route(_alert(), recipient)
    assert [call[1] for call in email.calls] == ["row@example.com"]
    assert webhook.calls == []


@pytest.mark.asyncio
async def test_route_workspace_event_creates_pending_and_policy_dead_letter_deliveries() -> None:
    workspace_id = uuid4()
    subscribed = SimpleNamespace(
        id=uuid4(),
        active=True,
        event_types=["execution.failed"],
        region_pinned_to=None,
        url="https://hooks.example.com/events",
        signing_secret_ref="secret/path",
        retry_policy={"backoff_seconds": [60]},
    )
    repo = WorkspaceEventRepoStub([subscribed])
    result = await _router(repo).route_workspace_event(
        {"event_id": uuid4(), "event_type": "execution.failed", "payload": {"ok": True}},
        workspace_id,
    )

    assert result[0].status == "delivered"
    assert repo.deliveries[0]["status"] == "delivering"
    assert repo.outcomes[0]["status"] == "delivered"

    blocked_repo = WorkspaceEventRepoStub([subscribed])
    blocked = await _router(blocked_repo, dlp=DlpStub({"action": "block"})).route_workspace_event(
        {"event_id": uuid4(), "event_type": "execution.failed"},
        workspace_id,
    )
    assert blocked[0].status == "dead_letter"
    assert blocked_repo.deliveries[0]["failure_reason"] == "dlp_blocked"
