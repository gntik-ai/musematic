from __future__ import annotations

from datetime import UTC, datetime
from platform.notifications.deliverers.email_deliverer import EmailDeliverer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.models import DeliveryOutcome
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest


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

    async def post(self, url: str, json: dict[str, object]) -> httpx.Response:
        self.calls.append((url, json))
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
    assert success_client.calls[0][1]["id"] == str(alert.id)

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
