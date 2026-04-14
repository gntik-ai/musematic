from __future__ import annotations

import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from platform.connectors.exceptions import (
    ConnectorConfigError,
    ConnectorDisabledError,
    ConnectorNameConflictError,
    ConnectorNotFoundError,
    ConnectorTypeDeprecatedError,
    ConnectorTypeNotFoundError,
    CredentialUnavailableError,
    DeadLetterAlreadyResolvedError,
    DeadLetterNotFoundError,
    DeliveryError,
    DeliveryPermanentError,
    WebhookSignatureError,
)
from platform.connectors.implementations.email import EmailConnector, EmailPollingJob
from platform.connectors.implementations.registry import get_connector
from platform.connectors.implementations.slack import SlackConnector
from platform.connectors.implementations.telegram import TelegramConnector
from platform.connectors.implementations.webhook import WebhookConnector
from platform.connectors.models import ConnectorHealthStatus
from platform.connectors.plugin import DeliveryRequest
from platform.connectors.security import (
    VaultResolver,
    assert_slack_signature,
    assert_webhook_signature,
    compute_hmac_sha256,
    payload_to_json,
    scrub_secret_text,
)
from platform.connectors.seed import main as seed_main
from platform.connectors.seed import seed_connector_types
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from tests.connectors_support import build_connectors_settings


class ResponseStub:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class AsyncClientStub:
    def __init__(
        self,
        *,
        post_response: ResponseStub | Exception | None = None,
        get_response: ResponseStub | Exception | None = None,
        head_response: ResponseStub | Exception | None = None,
    ) -> None:
        self.post_response = post_response
        self.get_response = get_response
        self.head_response = head_response
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    async def __aenter__(self) -> AsyncClientStub:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, **kwargs):
        self.calls.append(("post", url, kwargs))
        if isinstance(self.post_response, Exception):
            raise self.post_response
        return self.post_response

    async def get(self, url: str, **kwargs):
        self.calls.append(("get", url, kwargs))
        if isinstance(self.get_response, Exception):
            raise self.get_response
        return self.get_response

    async def head(self, url: str, **kwargs):
        self.calls.append(("head", url, kwargs))
        if isinstance(self.head_response, Exception):
            raise self.head_response
        return self.head_response


def _delivery_request(**overrides: object) -> DeliveryRequest:
    return DeliveryRequest(
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        destination=str(overrides.get("destination", "C123")),
        content_text=overrides.get("content_text", "hello"),
        content_structured=overrides.get("content_structured"),
        metadata=dict(overrides.get("metadata", {"subject": "Status"})),
    )


def test_connector_exceptions_expose_expected_codes() -> None:
    subject = uuid4()
    checks = [
        (ConnectorNotFoundError(subject), "CONNECTOR_NOT_FOUND"),
        (ConnectorTypeNotFoundError("missing"), "CONNECTOR_TYPE_NOT_FOUND"),
        (ConnectorTypeDeprecatedError("slack"), "CONNECTOR_TYPE_DEPRECATED"),
        (ConnectorConfigError("bad"), "CONNECTOR_CONFIG_INVALID"),
        (ConnectorDisabledError(subject), "CONNECTOR_DISABLED"),
        (ConnectorNameConflictError("ops"), "CONNECTOR_NAME_CONFLICT"),
        (CredentialUnavailableError("bot_token"), "CREDENTIAL_UNAVAILABLE"),
        (WebhookSignatureError(), "WEBHOOK_SIGNATURE_INVALID"),
        (DeliveryError("boom"), "DELIVERY_FAILED"),
        (DeliveryPermanentError("boom"), "DELIVERY_FAILED_PERMANENTLY"),
        (DeadLetterNotFoundError(subject), "DEAD_LETTER_NOT_FOUND"),
        (DeadLetterAlreadyResolvedError(subject), "DEAD_LETTER_ALREADY_RESOLVED"),
    ]

    assert all(exc.code == code for exc, code in checks)
    assert DeliveryPermanentError("boom").status_code == 422


def test_registry_returns_connector_and_security_helpers_cover_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b'{"hello":"world"}'
    secret = "top-secret"
    webhook_signature = "sha256=" + compute_hmac_sha256(secret, payload)
    assert_webhook_signature(secret, payload, webhook_signature)

    slack_payload = b'{"type":"event_callback"}'
    timestamp = "1234567890"
    slack_signature = "v0=" + compute_hmac_sha256(secret, f"v0:{timestamp}:".encode() + slack_payload)
    assert_slack_signature(secret, slack_payload, slack_signature, timestamp)

    with pytest.raises(WebhookSignatureError):
        assert_slack_signature(secret, slack_payload, None, timestamp)
    with pytest.raises(WebhookSignatureError):
        assert_webhook_signature(secret, payload, "sha256=bad")

    assert scrub_secret_text("token=top-secret", [secret]) == "token=[REDACTED]"
    assert scrub_secret_text(None, [secret]) is None
    assert payload_to_json({"b": 2, "a": 1}) == b'{"a":1,"b":2}'

    vault_file = tmp_path / "vault.json"
    vault_file.write_text(json.dumps({"vault/slack": "slack-secret"}), encoding="utf-8")
    settings = build_connectors_settings(vault_file=vault_file)
    resolver = VaultResolver(settings)
    assert resolver.resolve("vault/slack", "bot_token") == "slack-secret"

    monkeypatch.setenv("CONNECTOR_SECRET_BOT_TOKEN_VAULT_ENV_PATH", "env-secret")
    assert resolver.resolve("vault/env-path", "bot_token") == "env-secret"
    with pytest.raises(CredentialUnavailableError):
        resolver.resolve("vault/missing", "bot_token")

    assert isinstance(get_connector("slack"), SlackConnector)
    assert isinstance(get_connector("telegram"), TelegramConnector)
    assert isinstance(get_connector("webhook"), WebhookConnector)
    assert isinstance(get_connector("email"), EmailConnector)
    with pytest.raises(ConnectorTypeNotFoundError):
        get_connector("missing")


@pytest.mark.asyncio
async def test_seed_connector_types_creates_and_updates_records(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[object] = []
    existing = SimpleNamespace(
        display_name="Old",
        description="Old description",
        config_schema={},
        is_deprecated=True,
        deprecated_at=datetime.now(UTC),
        deprecation_note="old",
    )

    class ResultStub:
        def __init__(self, value) -> None:
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class SessionStub:
        def __init__(self) -> None:
            self.execute_calls = 0
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def execute(self, statement):
            del statement
            self.execute_calls += 1
            return ResultStub(None if self.execute_calls == 1 else existing)

        def add(self, item) -> None:
            created.append(item)

        async def commit(self) -> None:
            self.committed = True

    session = SessionStub()
    monkeypatch.setattr(
        "platform.connectors.seed.database.AsyncSessionLocal",
        lambda: session,
    )

    await seed_connector_types()

    assert len(created) == 1
    assert created[0].slug == "slack"
    assert existing.display_name == "Email"
    assert existing.is_deprecated is False
    assert session.committed is True

    called: list[bool] = []

    async def _seed_main() -> None:
        return None

    def _run(coro) -> None:
        called.append(True)
        coro.close()

    monkeypatch.setattr("platform.connectors.seed.seed_connector_types", _seed_main)
    monkeypatch.setattr("platform.connectors.seed.asyncio.run", _run)
    seed_main()
    assert called == [True]


@pytest.mark.asyncio
async def test_slack_connector_delivery_and_health(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = SlackConnector()
    stub = AsyncClientStub(
        post_response=ResponseStub(200, {"ok": True}),
    )
    monkeypatch.setattr("platform.connectors.implementations.slack.httpx.AsyncClient", lambda **kwargs: stub)

    request = _delivery_request(content_structured={"blocks": [{"type": "section"}]})
    await connector.deliver_outbound(request, {"bot_token": "xoxb-test"})
    health = await connector.health_check({"bot_token": "xoxb-test"})

    assert stub.calls[0][1].endswith("/chat.postMessage")
    assert stub.calls[0][2]["json"]["blocks"] == [{"type": "section"}]
    assert health.status is ConnectorHealthStatus.healthy

    failing_stub = AsyncClientStub(post_response=ResponseStub(503, {"ok": False}))
    monkeypatch.setattr(
        "platform.connectors.implementations.slack.httpx.AsyncClient",
        lambda **kwargs: failing_stub,
    )
    with pytest.raises(DeliveryError):
        await connector.deliver_outbound(_delivery_request(), {"bot_token": "x"})

    permanent_stub = AsyncClientStub(post_response=ResponseStub(400, {"ok": False, "error": "bad"}))
    monkeypatch.setattr(
        "platform.connectors.implementations.slack.httpx.AsyncClient",
        lambda **kwargs: permanent_stub,
    )
    with pytest.raises(DeliveryPermanentError):
        await connector.deliver_outbound(_delivery_request(), {"bot_token": "x"})

    unreachable_stub = AsyncClientStub(post_response=httpx.HTTPError("down"))
    monkeypatch.setattr(
        "platform.connectors.implementations.slack.httpx.AsyncClient",
        lambda **kwargs: unreachable_stub,
    )
    degraded = await connector.health_check({"bot_token": "x"})
    assert degraded.status is ConnectorHealthStatus.unreachable

    inbound = await connector.normalize_inbound(
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        config={},
        payload={"event": {"user": "U1", "channel": "#ops", "text": "ping", "ts": "1710000000"}},
        raw_body=b"{}",
        headers={},
    )
    assert inbound.sender_identity == "U1"
    assert inbound.channel == "#ops"

    degraded_stub = AsyncClientStub(post_response=ResponseStub(200, {"ok": False, "error": "bad"}))
    monkeypatch.setattr(
        "platform.connectors.implementations.slack.httpx.AsyncClient",
        lambda **kwargs: degraded_stub,
    )
    degraded_health = await connector.health_check({"bot_token": "x"})
    assert degraded_health.status is ConnectorHealthStatus.degraded

    fallback_inbound = await connector.normalize_inbound(
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        config={},
        payload={"event": "invalid"},
        raw_body=b"{}",
        headers={},
    )
    assert fallback_inbound.sender_identity == "unknown"
    assert fallback_inbound.content_structured is None

    with pytest.raises(ConnectorConfigError):
        await connector.validate_config({}, {})
    with pytest.raises(ConnectorConfigError):
        await connector.validate_config(
            {"team_id": "T1", "bot_token": {"$ref": "bot_token"}, "signing_secret": {"$ref": "signing_secret"}},
            {"bot_token": "vault/bot_token"},
        )


@pytest.mark.asyncio
async def test_telegram_and_webhook_connectors_cover_delivery_and_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telegram = TelegramConnector()
    telegram_stub = AsyncClientStub(
        post_response=ResponseStub(200, {"ok": True}),
        get_response=ResponseStub(200, {"ok": True}),
    )
    monkeypatch.setattr(
        "platform.connectors.implementations.telegram.httpx.AsyncClient",
        lambda **kwargs: telegram_stub,
    )
    await telegram.deliver_outbound(_delivery_request(destination="42"), {"bot_token": "bot"})
    healthy = await telegram.health_check({"bot_token": "bot"})
    assert healthy.status is ConnectorHealthStatus.healthy

    telegram_error = AsyncClientStub(post_response=ResponseStub(500, {"ok": False}))
    monkeypatch.setattr(
        "platform.connectors.implementations.telegram.httpx.AsyncClient",
        lambda **kwargs: telegram_error,
    )
    with pytest.raises(DeliveryError):
        await telegram.deliver_outbound(_delivery_request(destination="42"), {"bot_token": "bot"})

    telegram_perm = AsyncClientStub(post_response=ResponseStub(400, {"ok": False, "description": "bad"}))
    monkeypatch.setattr(
        "platform.connectors.implementations.telegram.httpx.AsyncClient",
        lambda **kwargs: telegram_perm,
    )
    with pytest.raises(DeliveryPermanentError):
        await telegram.deliver_outbound(_delivery_request(destination="42"), {"bot_token": "bot"})

    telegram_unreachable = AsyncClientStub(get_response=httpx.HTTPError("down"))
    monkeypatch.setattr(
        "platform.connectors.implementations.telegram.httpx.AsyncClient",
        lambda **kwargs: telegram_unreachable,
    )
    unreachable_health = await telegram.health_check({"bot_token": "bot"})
    assert unreachable_health.status is ConnectorHealthStatus.unreachable

    telegram_fallback = await telegram.normalize_inbound(
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        config={},
        payload={"message": "bad"},
        raw_body=b"{}",
        headers={},
    )
    assert telegram_fallback.sender_identity == "unknown"
    assert telegram_fallback.content_structured is None

    with pytest.raises(ConnectorConfigError):
        await telegram.validate_config({}, {})

    webhook = WebhookConnector()
    no_destination = await webhook.health_check({})
    assert no_destination.status is ConnectorHealthStatus.healthy

    webhook_stub = AsyncClientStub(
        post_response=ResponseStub(202, {}),
        head_response=ResponseStub(418, {}),
    )
    monkeypatch.setattr(
        "platform.connectors.implementations.webhook.httpx.AsyncClient",
        lambda **kwargs: webhook_stub,
    )
    await webhook.deliver_outbound(
        _delivery_request(metadata={"flag": True}),
        {"destination_url": "https://example.test/hook", "timeout_seconds": 1},
    )
    degraded = await webhook.health_check({"destination_url": "https://example.test/hook"})
    assert degraded.status is ConnectorHealthStatus.degraded

    with pytest.raises(DeliveryPermanentError):
        await webhook.deliver_outbound(_delivery_request(), {})

    webhook_server_error = AsyncClientStub(post_response=ResponseStub(500, {}))
    monkeypatch.setattr(
        "platform.connectors.implementations.webhook.httpx.AsyncClient",
        lambda **kwargs: webhook_server_error,
    )
    with pytest.raises(DeliveryError):
        await webhook.deliver_outbound(
            _delivery_request(),
            {"destination_url": "https://example.test/hook"},
        )

    webhook_perm = AsyncClientStub(post_response=ResponseStub(400, {}))
    monkeypatch.setattr(
        "platform.connectors.implementations.webhook.httpx.AsyncClient",
        lambda **kwargs: webhook_perm,
    )
    with pytest.raises(DeliveryPermanentError):
        await webhook.deliver_outbound(
            _delivery_request(),
            {"destination_url": "https://example.test/hook"},
        )

    inbound = await webhook.normalize_inbound(
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        config={"sender_header": "x-user", "default_channel": "#default"},
        payload={"text": "hello", "id": 7},
        raw_body=b"{}",
        headers={"x-user": "bot"},
        path="/incoming",
    )
    assert inbound.sender_identity == "bot"
    assert inbound.channel == "/incoming"

    fallback_webhook = await webhook.normalize_inbound(
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        config={},
        payload={"timestamp": "bad-date"},
        raw_body=b"{}",
        headers={},
        path=None,
    )
    assert fallback_webhook.channel == "webhook"

    webhook_unreachable = AsyncClientStub(head_response=httpx.HTTPError("down"))
    monkeypatch.setattr(
        "platform.connectors.implementations.webhook.httpx.AsyncClient",
        lambda **kwargs: webhook_unreachable,
    )
    unreachable = await webhook.health_check({"destination_url": "https://example.test/hook"})
    assert unreachable.status is ConnectorHealthStatus.unreachable

    with pytest.raises(ConnectorConfigError):
        await webhook.validate_config({}, {})


@pytest.mark.asyncio
async def test_email_connector_delivery_health_and_polling_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector = EmailConnector()
    raw_email = (
        "From: alice@example.com\r\n"
        "To: ops@example.com\r\n"
        "Subject: Alert\r\n"
        "Date: Tue, 02 Jan 2024 03:04:05 +0000\r\n"
        "Message-Id: <msg-1>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "Hello team\r\n"
    ).encode("utf-8")
    inbound = await connector.normalize_inbound(
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        config={"email_address": "ops@example.com"},
        payload={},
        raw_body=raw_email,
        headers={},
    )
    assert inbound.content_text == "Hello team"
    assert inbound.message_id == "<msg-1>"

    fallback_inbound = await connector.normalize_inbound(
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        config={"email_address": "ops@example.com"},
        payload={"raw_email": raw_email.decode("utf-8")},
        raw_body=b"",
        headers={},
    )
    assert fallback_inbound.original_payload["raw_email"].startswith("From: alice")

    sent_messages: list[object] = []

    class AioSmtpStub:
        async def send(self, message, **kwargs):
            sent_messages.append((message, kwargs))

    monkeypatch.setattr(
        "platform.connectors.implementations.email.importlib.import_module",
        lambda name: AioSmtpStub() if name == "aiosmtplib" else None,
    )
    await connector.deliver_outbound(
        _delivery_request(destination="ops@example.com", content_structured={"html": "<b>Hi</b>"}),
        {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "email_address": "noreply@example.com",
            "smtp_password": "secret",
        },
    )
    assert sent_messages[0][1]["hostname"] == "smtp.example.com"

    class ImapClientStub:
        def __init__(self, host: str, port: int) -> None:
            self.host = host
            self.port = port
            self.logged_out = False

        async def wait_hello_from_server(self) -> None:
            return None

        async def login(self, username: str, password: str) -> None:
            self.username = username
            self.password = password

        async def select(self, folder: str) -> None:
            self.folder = folder

        async def noop(self) -> None:
            return None

        async def logout(self) -> None:
            self.logged_out = True

    class AioImapStub:
        IMAP4_SSL = ImapClientStub

    monkeypatch.setattr(
        "platform.connectors.implementations.email.importlib.import_module",
        lambda name: AioImapStub if name == "aioimaplib" else AioSmtpStub(),
    )
    health = await connector.health_check(
        {
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "email_address": "noreply@example.com",
            "imap_password": "secret",
        }
    )
    assert health.status is ConnectorHealthStatus.healthy

    class FailingSmtpStub:
        async def send(self, message, **kwargs):
            del message, kwargs
            raise ValueError("bad recipient")

    monkeypatch.setattr(
        "platform.connectors.implementations.email.importlib.import_module",
        lambda name: FailingSmtpStub() if name == "aiosmtplib" else AioImapStub,
    )
    with pytest.raises(DeliveryPermanentError):
        await connector.deliver_outbound(
            _delivery_request(destination="ops@example.com"),
            {
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "email_address": "noreply@example.com",
                "smtp_password": "secret",
            },
        )

    class RuntimeFailingSmtpStub:
        async def send(self, message, **kwargs):
            del message, kwargs
            raise RuntimeError("smtp down")

    monkeypatch.setattr(
        "platform.connectors.implementations.email.importlib.import_module",
        lambda name: RuntimeFailingSmtpStub() if name == "aiosmtplib" else AioImapStub,
    )
    with pytest.raises(DeliveryError):
        await connector.deliver_outbound(
            _delivery_request(destination="ops@example.com"),
            {
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "email_address": "noreply@example.com",
                "smtp_password": "secret",
            },
        )

    class BrokenImapClient:
        def __init__(self, host: str, port: int) -> None:
            del host, port

        async def wait_hello_from_server(self) -> None:
            raise RuntimeError("imap down")

        async def logout(self) -> None:
            return None

    class BrokenImapStub:
        IMAP4_SSL = BrokenImapClient

    monkeypatch.setattr(
        "platform.connectors.implementations.email.importlib.import_module",
        lambda name: BrokenImapStub if name == "aioimaplib" else AioSmtpStub(),
    )
    unreachable = await connector.health_check(
        {
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "email_address": "noreply@example.com",
            "imap_password": "secret",
        }
    )
    assert unreachable.status is ConnectorHealthStatus.unreachable

    ran: list[bool] = []
    job = EmailPollingJob(runner=lambda: _mark_ran(ran))
    await job.run()
    assert ran == [True]

    with pytest.raises(ConnectorConfigError):
        await connector.validate_config({}, {})
    with pytest.raises(ConnectorConfigError):
        await connector.validate_config(
            {
                "imap_host": "imap.example.com",
                "imap_port": 993,
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "email_address": "ops@example.com",
                "imap_password": {"$ref": "imap_password"},
                "smtp_password": {"$ref": "smtp_password"},
            },
            {"imap_password": "vault/imap_password"},
        )


def test_security_schema_and_seed_edge_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from platform.connectors import schemas as schema_module
    from platform.connectors.schemas import ConnectorInstanceUpdate

    with pytest.raises(WebhookSignatureError):
        assert_slack_signature("secret", b"{}", "v0=bad", "1")

    non_mock_settings = build_connectors_settings(vault_file=tmp_path / "vault.json")
    non_mock_settings.connectors.vault_mode = "external"
    with pytest.raises(CredentialUnavailableError):
        VaultResolver(non_mock_settings).resolve("vault/path", "token")

    assert schema_module._sanitize_config(["a", {"token": "secret"}], "token") == ["[masked]", {"token": "[masked]"}]
    assert schema_module._validate_ref_shape(["x", {"$ref": " token "}])[1] == {"$ref": "token"}
    assert schema_module._normalize_optional_text("  ") is None
    with pytest.raises(ValueError):
        ConnectorInstanceUpdate.model_validate({"credential_refs": {" ": "path"}})
    with pytest.raises(ValueError):
        ConnectorInstanceUpdate.model_validate({"config": {"token": {"$ref": ""}}})

    class ResultStub:
        def scalar_one_or_none(self):
            return SimpleNamespace(
                display_name="Bad",
                description="Bad",
                config_schema={},
                is_deprecated=False,
                deprecated_at=None,
                deprecation_note=None,
            )

    class SessionStub:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def execute(self, statement):
            del statement
            return ResultStub()

        async def commit(self) -> None:
            return None

        def add(self, item) -> None:
            del item

    monkeypatch.setattr("platform.connectors.seed.database.AsyncSessionLocal", lambda: SessionStub())
    monkeypatch.setattr(
        "platform.connectors.seed._connector_type_seed_data",
        lambda: [
            {
                "slug": "broken",
                "display_name": "Broken",
                "description": "Broken",
                "config_schema": [],
            }
        ],
    )
    with pytest.raises(TypeError):
        asyncio.run(seed_connector_types())

    invoked: list[bool] = []

    def _run(coro) -> None:
        invoked.append(True)
        coro.close()

    monkeypatch.setattr("platform.connectors.seed.asyncio.run", _run)
    runpy.run_module("platform.connectors.seed", run_name="__main__")
    assert invoked == [True]


async def _mark_ran(store: list[bool]) -> None:
    store.append(True)
