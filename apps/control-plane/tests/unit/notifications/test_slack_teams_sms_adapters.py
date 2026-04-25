from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.notifications.channel_router import ChannelDelivererRegistry, ChannelRouter
from platform.notifications.deliverers.email_deliverer import EmailDeliverer
from platform.notifications.deliverers.slack_deliverer import SlackDeliverer
from platform.notifications.deliverers.sms_deliverer import (
    SmsDeliverer,
    SmsDeliveryResult,
    TwilioSmsProvider,
    _get_cost_counter,
    _increment_cost_counter,
    _int_value,
    _read_secret,
    _sender,
    _sms_cost_units,
    build_sms_body,
)
from platform.notifications.deliverers.teams_deliverer import TeamsDeliverer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.models import (
    AlertDeliveryOutcome,
    DeliveryMethod,
    DeliveryOutcome,
    UserAlert,
    UserAlertSettings,
)
from platform.notifications.schemas import ChannelConfigCreate, QuietHoursConfig
from platform.notifications.service import AlertService
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest


class _AsyncClientStub:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> _AsyncClientStub:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict[str, object]) -> httpx.Response:
        self.calls.append({"url": url, "json": json})
        return self.response


class _TwilioClientStub:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> _TwilioClientStub:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> httpx.Response:
        self.calls.append({"url": url, **kwargs})
        return self.response


class _TwilioExceptionClientStub:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def __aenter__(self) -> _TwilioExceptionClientStub:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> httpx.Response:
        del url, kwargs
        raise self.exc


class _SmsProviderStub:
    def __init__(self, result: SmsDeliveryResult | None = None) -> None:
        self.result = result or SmsDeliveryResult(DeliveryOutcome.success)
        self.sent: list[dict[str, object]] = []

    async def send_sms(self, *, to: str, body: str, sender: str | None) -> SmsDeliveryResult:
        self.sent.append({"to": to, "body": body, "sender": sender})
        return self.result


class _RedisStub:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values or {}

    async def get(self, key: str) -> bytes | None:
        value = self.values.get(key)
        return None if value is None else value.encode()

    async def set(self, key: str, value: bytes | str, ttl: int | None = None) -> None:
        del ttl
        self.values[key] = value.decode() if isinstance(value, bytes) else value


class _RawRedisClientStub:
    def __init__(self, value: object | None = None) -> None:
        self.value = value
        self.increments: list[tuple[str, int]] = []
        self.expired: list[tuple[str, int]] = []

    async def get(self, key: str) -> object | None:
        del key
        return self.value

    async def incrby(self, key: str, amount: int) -> None:
        self.increments.append((key, amount))

    async def expire(self, key: str, ttl: int) -> None:
        self.expired.append((key, ttl))


class _RedisWithRawClient:
    def __init__(self, client: _RawRedisClientStub | None) -> None:
        self.client = client


class _RedisSetTypeErrorStub:
    def __init__(self) -> None:
        self.value: bytes | None = None

    async def get(self, key: str) -> bytes | None:
        del key
        return self.value

    async def set(self, key: str, value: bytes | str, ttl: int | None = None) -> None:
        del key, ttl
        if isinstance(value, str):
            raise TypeError
        self.value = value


class _SecretStub:
    def __init__(self, value: object) -> None:
        self.value = value
        self.paths: list[str] = []

    async def read_secret(self, path: str) -> object:
        self.paths.append(path)
        return self.value


class _RepoStub:
    def __init__(self, config: SimpleNamespace) -> None:
        self.config = config
        self.outcomes: list[dict[str, object]] = []

    async def list_enabled_channel_configs(self, user_id):
        del user_id
        return [self.config]

    async def get_settings(self, user_id):
        return UserAlertSettings(
            id=uuid4(),
            user_id=user_id,
            state_transitions=["any_to_failed"],
            delivery_method=DeliveryMethod.in_app,
            webhook_url=None,
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


class _AllowDlp:
    async def scan_outbound(self, **kwargs):
        del kwargs
        return {"action": "allow"}


class _ResidencyStub:
    async def resolve_region_for_url(self, url):
        del url
        return None

    async def check_egress(self, workspace_id, region):
        del workspace_id, region
        return True


@pytest.mark.asyncio
async def test_slack_payload_and_failure_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _AsyncClientStub(httpx.Response(204))
    monkeypatch.setattr(
        "platform.notifications.deliverers.slack_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: client,
    )

    outcome, detail = await SlackDeliverer().send(
        _alert(),
        "https://hooks.slack.test",
        _config(DeliveryMethod.slack),
    )

    payload = client.calls[0]["json"]
    assert outcome == DeliveryOutcome.success
    assert detail is None
    assert payload["blocks"][0]["type"] == "header"
    assert payload["blocks"][1]["fields"][0]["text"] == "*Severity:* high"
    assert payload["blocks"][3]["elements"][0]["url"] == "https://app.test/deep-link"

    retry_client = _AsyncClientStub(httpx.Response(429, headers={"Retry-After": "30"}))
    monkeypatch.setattr(
        "platform.notifications.deliverers.slack_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: retry_client,
    )
    outcome, detail = await SlackDeliverer().send(_alert(), "https://hooks.slack.test")
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "rate_limited; retry_after=30"

    failed_client = _AsyncClientStub(httpx.Response(400, text="bad"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.slack_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: failed_client,
    )
    outcome, detail = await SlackDeliverer().send(_alert(), "https://hooks.slack.test")
    assert outcome == DeliveryOutcome.failed
    assert detail == "4xx_permanent"


@pytest.mark.asyncio
async def test_teams_payload_and_failure_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _AsyncClientStub(httpx.Response(204))
    monkeypatch.setattr(
        "platform.notifications.deliverers.teams_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: client,
    )

    outcome, detail = await TeamsDeliverer().send(
        _alert(),
        "https://hooks.teams.test",
        _config(DeliveryMethod.teams),
    )

    payload = client.calls[0]["json"]
    content = payload["attachments"][0]["content"]
    assert outcome == DeliveryOutcome.success
    assert detail is None
    assert content["type"] == "AdaptiveCard"
    assert content["body"][1]["facts"][0] == {"title": "Severity", "value": "high"}
    assert content["actions"][0]["url"] == "https://app.test/deep-link"

    retry_client = _AsyncClientStub(httpx.Response(503, text="down"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.teams_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: retry_client,
    )
    outcome, detail = await TeamsDeliverer().send(_alert(), "https://hooks.teams.test")
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "down"

    failed_client = _AsyncClientStub(httpx.Response(404, text="missing"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.teams_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: failed_client,
    )
    outcome, detail = await TeamsDeliverer().send(_alert(), "https://hooks.teams.test")
    assert outcome == DeliveryOutcome.failed
    assert detail == "4xx_permanent"


@pytest.mark.asyncio
async def test_channel_router_dispatches_slack_and_teams_via_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _AsyncClientStub(httpx.Response(204))
    monkeypatch.setattr(
        "platform.notifications.deliverers.slack_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: client,
    )
    monkeypatch.setattr(
        "platform.notifications.deliverers.teams_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: client,
    )

    slack_repo = _RepoStub(_config(DeliveryMethod.slack))
    teams_repo = _RepoStub(_config(DeliveryMethod.teams))
    await _router(slack_repo).route(_alert(), _recipient())
    await _router(teams_repo).route(_alert(), _recipient())

    assert slack_repo.outcomes[0]["outcome"] == DeliveryOutcome.success
    assert teams_repo.outcomes[0]["outcome"] == DeliveryOutcome.success
    assert [call["url"] for call in client.calls] == [
        "https://hooks.example.com/slack",
        "https://hooks.example.com/teams",
    ]


@pytest.mark.asyncio
async def test_slack_and_teams_verification_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, UserAlert]] = []

    class _VerificationDeliverer:
        async def send(self, alert, target, config):
            del config
            sent.append((target, alert))
            return DeliveryOutcome.success, None

    monkeypatch.setattr(
        "platform.notifications.service.SlackDeliverer",
        lambda: _VerificationDeliverer(),
    )
    monkeypatch.setattr(
        "platform.notifications.service.TeamsDeliverer",
        lambda: _VerificationDeliverer(),
    )
    service = AlertService(
        repo=SimpleNamespace(),
        accounts_repo=SimpleNamespace(),
        workspaces_service=None,
        redis=SimpleNamespace(),
        producer=None,
        settings=PlatformSettings(),
        email_deliverer=EmailDeliverer(),
        webhook_deliverer=WebhookDeliverer(),
    )

    await service._send_channel_verification(_config(DeliveryMethod.slack), "slack-code")
    await service._send_channel_verification(_config(DeliveryMethod.teams), "teams-code")

    assert [target for target, _alert_obj in sent] == [
        "https://hooks.example.com/slack",
        "https://hooks.example.com/teams",
    ]
    assert [alert.body for _target, alert in sent] == [
        "Use this verification token to activate your notification channel: slack-code",
        "Use this verification token to activate your notification channel: teams-code",
    ]


def test_sms_channel_create_schema_requires_e164_and_high_or_critical_floor() -> None:
    with pytest.raises(ValueError, match=r"E\.164"):
        ChannelConfigCreate(channel_type=DeliveryMethod.sms, target="666123456")

    with pytest.raises(ValueError, match="high or critical"):
        ChannelConfigCreate(
            channel_type=DeliveryMethod.sms,
            target="+34666123456",
            severity_floor="medium",
        )

    assert (
        ChannelConfigCreate(
            channel_type=DeliveryMethod.sms,
            target="+34666123456",
            severity_floor="critical",
        ).target
        == "+34666123456"
    )

    with pytest.raises(ValueError, match="timezone"):
        QuietHoursConfig(start="09:00", end="18:00", timezone="Not/AZone")

    with pytest.raises(ValueError, match="24-hour"):
        QuietHoursConfig(start="99:00", end="18:00", timezone="UTC")

    with pytest.raises(ValueError, match="targets must be URLs"):
        ChannelConfigCreate(channel_type=DeliveryMethod.slack, target="not-a-url")


@pytest.mark.asyncio
async def test_sms_cost_cap_exceeded_returns_fallback_without_incrementing_or_sending() -> None:
    settings = PlatformSettings()
    settings.notifications.sms_workspace_monthly_cost_cap_eur = 0.05
    provider = _SmsProviderStub()
    redis = _RedisStub()
    deliverer = SmsDeliverer(
        redis=redis,
        secrets=SimpleNamespace(),
        settings=settings,
        provider=provider,
    )

    outcome, detail = await deliverer.send(
        _alert(),
        "+34666123456",
        _config(DeliveryMethod.sms),
        workspace_id=uuid4(),
    )

    assert outcome == DeliveryOutcome.fallback
    assert detail == "cost_cap_exceeded"
    assert provider.sent == []
    assert redis.values == {}


@pytest.mark.asyncio
async def test_sms_body_truncates_to_single_message_with_deep_link_suffix() -> None:
    alert = _alert()
    alert.title = "Critical portfolio review required immediately"
    alert.body = " ".join(["customer identity verification evidence"] * 10)
    config = _config(DeliveryMethod.sms)
    config.extra["deep_link"] = "https://muse.test/a"
    provider = _SmsProviderStub()
    deliverer = SmsDeliverer(
        redis=_RedisStub(),
        secrets=SimpleNamespace(),
        settings=PlatformSettings(),
        provider=provider,
    )

    body = build_sms_body(alert, config)
    outcome, detail = await deliverer.send(alert, "+34666123456", config)

    assert len(body) <= 160
    assert "…" in body
    assert body.endswith("https://muse.test/a")
    assert outcome == DeliveryOutcome.success
    assert detail is None
    assert provider.sent[0]["body"] == body


@pytest.mark.asyncio
async def test_sms_twilio_errors_do_not_expose_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    sid = "ACsecretaccountsid"
    token = "auth-token-secret"
    client = _TwilioClientStub(httpx.Response(401, text=f"{sid}:{token} rejected"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.sms_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: client,
    )

    result = await TwilioSmsProvider(sid, token, "+15551230000").send_sms(
        to="+34666123456",
        body="Critical alert",
        sender=None,
    )

    assert result.outcome == DeliveryOutcome.failed
    assert result.error_detail == "sms_provider_rejected"
    assert sid not in str(result.error_detail)
    assert token not in str(result.error_detail)


@pytest.mark.asyncio
async def test_twilio_provider_classifies_success_retry_and_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    success_client = _TwilioClientStub(httpx.Response(201))
    monkeypatch.setattr(
        "platform.notifications.deliverers.sms_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: success_client,
    )
    success = await TwilioSmsProvider("ACsid", "token", "+15551230000").send_sms(
        to="+34666123456",
        body="Critical alert",
        sender="+15559990000",
    )
    assert success.outcome == DeliveryOutcome.success
    assert success.last_response_status == 201
    assert success_client.calls[0]["data"]["From"] == "+15559990000"

    rate_limited_client = _TwilioClientStub(httpx.Response(429))
    monkeypatch.setattr(
        "platform.notifications.deliverers.sms_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: rate_limited_client,
    )
    rate_limited = await TwilioSmsProvider("ACsid", "token", "+15551230000").send_sms(
        to="+34666123456",
        body="Critical alert",
        sender=None,
    )
    assert rate_limited.outcome == DeliveryOutcome.timed_out
    assert rate_limited.failure_reason == "rate_limited"

    unavailable_client = _TwilioClientStub(httpx.Response(503))
    monkeypatch.setattr(
        "platform.notifications.deliverers.sms_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: unavailable_client,
    )
    unavailable = await TwilioSmsProvider("ACsid", "token", "+15551230000").send_sms(
        to="+34666123456",
        body="Critical alert",
        sender=None,
    )
    assert unavailable.outcome == DeliveryOutcome.timed_out
    assert unavailable.error_detail == "sms_provider_unavailable"

    monkeypatch.setattr(
        "platform.notifications.deliverers.sms_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: _TwilioExceptionClientStub(httpx.TimeoutException("slow")),
    )
    timed_out = await TwilioSmsProvider("ACsid", "token", "+15551230000").send_sms(
        to="+34666123456",
        body="Critical alert",
        sender=None,
    )
    assert timed_out.failure_reason == "timeout"

    monkeypatch.setattr(
        "platform.notifications.deliverers.sms_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: _TwilioExceptionClientStub(httpx.TransportError("down")),
    )
    transport_error = await TwilioSmsProvider("ACsid", "token", "+15551230000").send_sms(
        to="+34666123456",
        body="Critical alert",
        sender=None,
    )
    assert transport_error.failure_reason == "provider_unavailable"


@pytest.mark.asyncio
async def test_sms_provider_secret_fallbacks_and_cost_counter_edges() -> None:
    settings = PlatformSettings()
    secrets = _SecretStub(
        {
            "account_sid": "ACsid",
            "auth_token": "token",
            "sender": "+15551230000",
        }
    )
    deliverer = SmsDeliverer(redis=None, secrets=secrets, settings=settings, deployment="prod")
    provider = await deliverer._provider()

    assert isinstance(provider, TwilioSmsProvider)
    assert secrets.paths == ["secret/data/notifications/sms-providers/prod"]
    assert await _read_secret(None, "secret/path") == {}
    assert await _read_secret(object(), "secret/path") == {}
    assert await _read_secret(_SecretStub(["not", "dict"]), "secret/path") == {}

    key = "notifications:sms_cost:test"
    raw_client = _RawRedisClientStub(b"17")
    assert await _get_cost_counter(_RedisWithRawClient(raw_client), key) == 17
    assert await _get_cost_counter(_RedisWithRawClient(None), key) == 0
    assert await _get_cost_counter(object(), key) == 0

    await _increment_cost_counter(_RedisWithRawClient(raw_client), key, 8)
    assert raw_client.increments == [(key, 8)]
    assert raw_client.expired == [(key, 35 * 24 * 60 * 60)]

    fallback = _RedisSetTypeErrorStub()
    await _increment_cost_counter(fallback, key, 9)
    assert fallback.value == b"9"
    assert _sms_cost_units(SimpleNamespace(extra={"sms_cost_eur": "bad"})) == 8
    assert _sms_cost_units(SimpleNamespace(extra={"sms_cost_eur": 0.12})) == 12
    assert _sender(SimpleNamespace(extra={"sender": "+15551230000"})) == "+15551230000"
    assert _int_value("not-an-int") == 0

    plain_redis = _RedisStub({"cost": "3"})
    await _increment_cost_counter(plain_redis, "cost", 4)
    assert plain_redis.values["cost"] == "7"

    zero_cap_settings = PlatformSettings()
    zero_cap_settings.notifications.sms_workspace_monthly_cost_cap_eur = 0
    assert await SmsDeliverer(
        redis=_RedisStub(),
        secrets=SimpleNamespace(),
        settings=zero_cap_settings,
        provider=_SmsProviderStub(),
    )._cost_cap_exceeded(uuid4(), 1)


@pytest.mark.asyncio
async def test_sms_verification_generates_six_digit_code_and_dispatches_sms() -> None:
    provider = _SmsProviderStub()
    service = AlertService(
        repo=SimpleNamespace(),
        accounts_repo=SimpleNamespace(),
        workspaces_service=None,
        redis=SimpleNamespace(),
        producer=None,
        settings=PlatformSettings(),
        email_deliverer=EmailDeliverer(),
        webhook_deliverer=WebhookDeliverer(),
        sms_deliverer=SmsDeliverer(
            redis=None,
            secrets=SimpleNamespace(),
            settings=PlatformSettings(),
            provider=provider,
        ),
    )

    token, token_hash, expires_at = service._verification_challenge(DeliveryMethod.sms)
    await service._send_channel_verification(_config(DeliveryMethod.sms), token)

    assert token.isdigit()
    assert len(token) == 6
    assert token_hash == service._hash_token(token)
    assert (expires_at - datetime.now(UTC)).total_seconds() <= 600
    assert provider.sent[0]["to"] == "+34666123456"
    assert token in str(provider.sent[0]["body"])


@pytest.mark.asyncio
async def test_sms_below_hard_severity_floor_is_not_dispatched() -> None:
    config = _config(DeliveryMethod.sms)
    config.severity_floor = "critical"
    provider = _SmsProviderStub()
    repo = _RepoStub(config)

    result = await _router(repo, sms_provider=provider).route(
        _alert(),
        _recipient(),
        workspace_id=uuid4(),
        severity="high",
    )

    assert result.attempts == []
    assert provider.sent == []


def _alert() -> UserAlert:
    alert = UserAlert(
        id=uuid4(),
        user_id=uuid4(),
        interaction_id=None,
        source_reference=None,
        alert_type="attention_request",
        title="Attention requested",
        body="Review this alert",
        urgency="high",
        read=False,
    )
    alert.created_at = datetime.now(UTC)
    alert.updated_at = alert.created_at
    return alert


def _config(channel_type: DeliveryMethod) -> SimpleNamespace:
    if channel_type == DeliveryMethod.sms:
        return SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            channel_type=channel_type,
            target="+34666123456",
            quiet_hours=None,
            alert_type_filter=None,
            severity_floor="critical",
            extra={"workspace_name": "Ops", "deep_link": "https://app.test/deep-link"},
        )
    suffix = "slack" if channel_type == DeliveryMethod.slack else "teams"
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        channel_type=channel_type,
        target=f"https://hooks.example.com/{suffix}",
        quiet_hours=None,
        alert_type_filter=None,
        severity_floor=None,
        extra={"workspace_name": "Ops", "deep_link": "https://app.test/deep-link"},
    )


def _recipient() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), email="user@example.com")


def _router(repo: _RepoStub, sms_provider: _SmsProviderStub | None = None) -> ChannelRouter:
    settings = PlatformSettings()
    settings.notifications.multi_channel_enabled = True
    return ChannelRouter(
        repo=repo,
        accounts_repo=SimpleNamespace(),
        workspaces_service=None,
        dlp_service=_AllowDlp(),
        residency_service=_ResidencyStub(),
        secrets=SimpleNamespace(),
        audit_chain=SimpleNamespace(),
        producer=None,
        settings=settings,
        deliverers=ChannelDelivererRegistry(
            email=EmailDeliverer(),
            webhook=WebhookDeliverer(),
            extras={
                DeliveryMethod.slack: SlackDeliverer(),
                DeliveryMethod.teams: TeamsDeliverer(),
                DeliveryMethod.sms: SmsDeliverer(
                    redis=_RedisStub(),
                    secrets=SimpleNamespace(),
                    settings=settings,
                    provider=sms_provider or _SmsProviderStub(),
                ),
            },
        ),
    )
