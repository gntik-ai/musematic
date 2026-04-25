from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.notifications.canonical import canonicalise_payload
from platform.notifications.deliverers.email_deliverer import EmailDeliverer
from platform.notifications.deliverers.slack_deliverer import (
    SlackDeliverer,
)
from platform.notifications.deliverers.slack_deliverer import (
    _classify_response as _classify_slack_response,
)
from platform.notifications.deliverers.teams_deliverer import (
    TeamsDeliverer,
)
from platform.notifications.deliverers.teams_deliverer import (
    _classify_response as _classify_teams_response,
)
from platform.notifications.deliverers.webhook_deliverer import (
    WebhookDeliverer,
)
from platform.notifications.deliverers.webhook_deliverer import (
    _classify_response as _classify_webhook_response,
)
from platform.notifications.models import DeliveryOutcome
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel


def _alert() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        alert_type="attention_request",
        title="Attention requested",
        body="Need review",
        urgency="high",
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_email_deliverer_returns_failed_when_smtp_settings_are_missing() -> None:
    deliverer = EmailDeliverer()

    outcome = await deliverer.send(_alert(), "user@example.com", {"hostname": "smtp.example.com"})

    assert outcome == DeliveryOutcome.failed


@pytest.mark.asyncio
async def test_email_deliverer_returns_success_when_send_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def _send(message, **kwargs):
        calls.append({"subject": message["Subject"], **kwargs})

    monkeypatch.setattr(
        "platform.notifications.deliverers.email_deliverer.import_module",
        lambda name: SimpleNamespace(send=_send),
    )
    deliverer = EmailDeliverer()

    outcome = await deliverer.send(
        _alert(),
        "user@example.com",
        {
            "hostname": "smtp.example.com",
            "port": 587,
            "username": "mailer@example.com",
            "password": "secret",
            "from_address": "alerts@example.com",
        },
    )

    assert outcome == DeliveryOutcome.success
    assert calls == [
        {
            "subject": "Attention requested",
            "hostname": "smtp.example.com",
            "port": 587,
            "username": "mailer@example.com",
            "password": "secret",
            "start_tls": True,
        }
    ]


class _AsyncClientStub:
    def __init__(
        self, *, response: httpx.Response | None = None, exc: Exception | None = None
    ) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self) -> _AsyncClientStub:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(
        self,
        url: str,
        json: dict[str, object] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        self.calls.append((url, {"json": json, "content": content, "headers": headers or {}}))
        if self.exc is not None:
            raise self.exc
        assert self.response is not None
        return self.response


@pytest.mark.asyncio
async def test_webhook_deliverer_handles_success_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alert = _alert()
    deliverer = WebhookDeliverer()

    success_client = _AsyncClientStub(response=httpx.Response(204))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: success_client,
    )
    outcome, detail = await deliverer.send(alert, "https://hooks.example.com/alert")
    assert outcome == DeliveryOutcome.success
    assert detail is None
    assert success_client.calls[0][0] == "https://hooks.example.com/alert"
    assert success_client.calls[0][1]["json"]["id"] == str(alert.id)

    timeout_client = _AsyncClientStub(exc=httpx.TimeoutException("timed out"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: timeout_client,
    )
    outcome, detail = await deliverer.send(alert, "https://hooks.example.com/alert")
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "timed out"

    error_client = _AsyncClientStub(response=httpx.Response(400, text="bad request"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: error_client,
    )
    outcome, detail = await deliverer.send(alert, "https://hooks.example.com/alert")
    assert outcome == DeliveryOutcome.failed
    assert detail == "bad request"



@pytest.mark.asyncio
async def test_email_and_webhook_deliverers_cover_additional_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _failing_send(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("smtp down")

    monkeypatch.setattr(
        "platform.notifications.deliverers.email_deliverer.import_module",
        lambda name: SimpleNamespace(send=_failing_send),
    )
    email_deliverer = EmailDeliverer()
    email_outcome = await email_deliverer.send(
        _alert(),
        "user@example.com",
        {
            "hostname": "smtp.example.com",
            "port": 587,
            "username": "mailer@example.com",
            "password": "secret",
        },
    )
    assert email_outcome == DeliveryOutcome.failed

    alert = _alert()
    webhook_deliverer = WebhookDeliverer()

    http_error_client = _AsyncClientStub(exc=httpx.HTTPError("network"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: http_error_client,
    )
    outcome, detail = await webhook_deliverer.send(alert, "https://hooks.example.com/alert")
    assert outcome == DeliveryOutcome.failed
    assert detail == "network"

    server_error_client = _AsyncClientStub(response=httpx.Response(503, text="retry later"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: server_error_client,
    )
    outcome, detail = await webhook_deliverer.send(alert, "https://hooks.example.com/alert")
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "retry later"


@pytest.mark.asyncio
async def test_email_deliverer_html_config_object_and_invalid_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def _send(message, **kwargs):
        calls.append(
            {
                "content_type": message.get_content_type(),
                "has_alternative": message.is_multipart(),
                **kwargs,
            }
        )

    monkeypatch.setattr(
        "platform.notifications.deliverers.email_deliverer.import_module",
        lambda name: SimpleNamespace(send=_send),
    )
    deliverer = EmailDeliverer()
    config = SimpleNamespace(
        extra={
            "smtp_settings": {
                "hostname": "smtp.example.com",
                "port": "2525",
                "username": "mailer@example.com",
                "password": "secret",
                "email_format": "html",
                "start_tls": False,
            }
        }
    )

    assert await deliverer.send(_alert(), "user@example.com", config) == DeliveryOutcome.success
    assert calls[0]["has_alternative"] is True
    assert calls[0]["port"] == 2525
    assert calls[0]["start_tls"] is False
    assert (
        await deliverer.send(_alert(), "user@example.com", SimpleNamespace(extra=["bad"]))
        == DeliveryOutcome.failed
    )


@pytest.mark.asyncio
async def test_slack_and_teams_deliverers_handle_transport_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeout_client = _AsyncClientStub(exc=httpx.TimeoutException("slow"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.slack_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: timeout_client,
    )
    outcome, detail = await SlackDeliverer().send(_alert(), "https://hooks.slack.test")
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "slow"

    http_error_client = _AsyncClientStub(exc=httpx.TransportError("down"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.slack_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: http_error_client,
    )
    outcome, detail = await SlackDeliverer().send(_alert(), "https://hooks.slack.test")
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "down"

    timeout_client = _AsyncClientStub(exc=httpx.TimeoutException("slow"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.teams_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: timeout_client,
    )
    outcome, detail = await TeamsDeliverer().send(_alert(), "https://hooks.teams.test")
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "slow"

    http_error_client = _AsyncClientStub(exc=httpx.TransportError("down"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.teams_deliverer.httpx.AsyncClient",
        lambda timeout=10.0: http_error_client,
    )
    outcome, detail = await TeamsDeliverer().send(_alert(), "https://hooks.teams.test")
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "down"


@pytest.mark.asyncio
async def test_webhook_signed_delivery_transport_redirect_and_retry_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deliverer = WebhookDeliverer()

    timeout_client = _AsyncClientStub(exc=httpx.TimeoutException("slow"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0, follow_redirects=False: timeout_client,
    )
    outcome, detail, _ = await deliverer.send_signed(
        webhook_id=uuid4(),
        event_id=uuid4(),
        webhook_url="https://hooks.example.com/events",
        payload={"event": "test"},
        secret="secret",
        platform_version="test",
    )
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "slow"

    http_error_client = _AsyncClientStub(exc=httpx.TransportError("down"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0, follow_redirects=False: http_error_client,
    )
    outcome, detail, _ = await deliverer.send_signed(
        webhook_id=uuid4(),
        event_id=uuid4(),
        webhook_url="https://hooks.example.com/events",
        payload={"event": "test"},
        secret="secret",
        platform_version="test",
    )
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "down"

    retry_client = _AsyncClientStub(response=httpx.Response(429, text="slow"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0, follow_redirects=False: retry_client,
    )
    outcome, detail, _ = await deliverer.send_signed(
        webhook_id=uuid4(),
        event_id=uuid4(),
        webhook_url="https://hooks.example.com/events",
        payload={"event": "test"},
        secret="secret",
        platform_version="test",
    )
    assert outcome == DeliveryOutcome.timed_out
    assert detail == "slow"

    redirect_client = _AsyncClientStub(
        response=httpx.Response(302, headers={"location": "https://hooks.example.com/loop"})
    )
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0, follow_redirects=False: redirect_client,
    )
    outcome, detail, _ = await deliverer.send_signed(
        webhook_id=uuid4(),
        event_id=uuid4(),
        webhook_url="https://hooks.example.com/events",
        payload={"event": "test"},
        secret="secret",
        platform_version="test",
    )
    assert outcome == DeliveryOutcome.failed
    assert detail == "redirect_loop"


def test_canonicalise_payload_handles_model_dataclass_sequences_and_binary_values() -> None:
    class PayloadModel(BaseModel):
        item_id: object
        created_at: datetime

    @dataclass(frozen=True)
    class PayloadData:
        nested: object
        blob: bytes

    encoded = canonicalise_payload(
        PayloadData(
            nested=[PayloadModel(item_id=uuid4(), created_at=datetime(2026, 1, 1, tzinfo=UTC))],
            blob=b"hello",
        )
    )

    assert b"hello" in encoded
    assert b"2026-01-01T00:00:00" in encoded

    raw_encoded = canonicalise_payload(
        {
            "id": uuid4(),
            "when": datetime(2026, 1, 1, tzinfo=UTC),
            "items": (b"a", b"b"),
        }
    )
    assert b'"items":["a","b"]' in raw_encoded
    assert b"2026-01-01T00:00:00+00:00" in raw_encoded


def test_direct_response_classifiers_cover_retry_without_headers() -> None:
    assert _classify_slack_response(httpx.Response(429, text="slow")) == (
        DeliveryOutcome.timed_out,
        "slow",
    )
    assert _classify_slack_response(httpx.Response(503, text="down")) == (
        DeliveryOutcome.timed_out,
        "down",
    )
    assert _classify_teams_response(httpx.Response(429, text="slow")) == (
        DeliveryOutcome.timed_out,
        "slow",
    )
    assert _classify_teams_response(httpx.Response(429, headers={"Retry-After": "15"})) == (
        DeliveryOutcome.timed_out,
        "rate_limited; retry_after=15",
    )
    assert _classify_teams_response(httpx.Response(503, text="down")) == (
        DeliveryOutcome.timed_out,
        "down",
    )
    assert _classify_webhook_response(httpx.Response(408, text="late")) == (
        DeliveryOutcome.timed_out,
        "late",
    )


@pytest.mark.asyncio
async def test_webhook_deliverer_signed_delivery_uses_canonical_body_and_hmac_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deliverer = WebhookDeliverer()
    client = _AsyncClientStub(response=httpx.Response(204))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0, follow_redirects=False: client,
    )
    webhook_id = uuid4()
    event_id = uuid4()

    outcome, detail, idempotency_key = await deliverer.send_signed(
        webhook_id=webhook_id,
        event_id=event_id,
        webhook_url="https://hooks.example.com/events",
        payload={"z": 1, "a": "é"},
        secret=b"secret",
        platform_version="test",
    )

    assert outcome == DeliveryOutcome.success
    assert detail is None
    assert client.calls[0][1]["content"] == b'{"a":"\xc3\xa9","z":1}'
    headers = client.calls[0][1]["headers"]
    assert headers["X-Musematic-Signature"].startswith("sha256=")
    assert headers["X-Musematic-Idempotency-Key"] == str(idempotency_key)
    assert headers["User-Agent"] == "musematic-webhook/test"


@pytest.mark.asyncio
async def test_webhook_deliverer_signed_delivery_classifies_retryable_and_permanent_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deliverer = WebhookDeliverer()
    rate_limit_client = _AsyncClientStub(
        response=httpx.Response(429, text="slow", headers={"Retry-After": "30"})
    )
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0, follow_redirects=False: rate_limit_client,
    )

    outcome, detail, _ = await deliverer.send_signed(
        webhook_id=uuid4(),
        event_id=uuid4(),
        webhook_url="https://hooks.example.com/events",
        payload={"event": "test"},
        secret="secret",
        platform_version="test",
    )

    assert outcome == DeliveryOutcome.timed_out
    assert detail == "rate_limited; retry_after=30"

    permanent_client = _AsyncClientStub(response=httpx.Response(400, text="bad request"))
    monkeypatch.setattr(
        "platform.notifications.deliverers.webhook_deliverer.httpx.AsyncClient",
        lambda timeout=10.0, follow_redirects=False: permanent_client,
    )
    outcome, detail, _ = await deliverer.send_signed(
        webhook_id=uuid4(),
        event_id=uuid4(),
        webhook_url="https://hooks.example.com/events",
        payload={"event": "test"},
        secret="secret",
        platform_version="test",
    )
    assert outcome == DeliveryOutcome.failed
    assert detail == "4xx_permanent"
