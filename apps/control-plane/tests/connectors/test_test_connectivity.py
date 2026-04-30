from __future__ import annotations

import importlib
from platform.connectors.implementations.email import EmailConnector
from platform.connectors.implementations.slack import SlackConnector
from platform.connectors.implementations.telegram import TelegramConnector
from platform.connectors.implementations.webhook import WebhookConnector
from platform.connectors.schemas import TestConnectivityRequest, TestResult
from platform.connectors.service import ConnectorsService
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from tests.connectors_support import build_connector_instance


class _HTTPClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str]] = []

    async def __aenter__(self) -> _HTTPClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, url: str, **_kwargs: object) -> httpx.Response:
        self.requests.append(("POST", url))
        return self.responses.pop(0)

    async def get(self, url: str, **_kwargs: object) -> httpx.Response:
        self.requests.append(("GET", url))
        return self.responses.pop(0)

    async def head(self, url: str, **_kwargs: object) -> httpx.Response:
        self.requests.append(("HEAD", url))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_slack_and_telegram_dry_runs_use_validation_apis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slack_client = _HTTPClient([httpx.Response(200, json={"ok": True})])
    monkeypatch.setattr(
        "platform.connectors.implementations.slack.httpx.AsyncClient",
        lambda **_: slack_client,
    )

    slack = await SlackConnector().test_connectivity({"bot_token": "xoxb-test"}, {})

    assert slack.success is True
    assert slack_client.requests == [("POST", "https://slack.com/api/auth.test")]

    telegram_client = _HTTPClient([httpx.Response(200, json={"ok": True})])
    monkeypatch.setattr(
        "platform.connectors.implementations.telegram.httpx.AsyncClient",
        lambda **_: telegram_client,
    )

    telegram = await TelegramConnector().test_connectivity({"bot_token": "bot-token"}, {})

    assert telegram.success is True
    assert telegram_client.requests == [("GET", "https://api.telegram.org/botbot-token/getMe")]


@pytest.mark.asyncio
async def test_webhook_dry_run_uses_head_not_post(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _HTTPClient([httpx.Response(204)])
    monkeypatch.setattr(
        "platform.connectors.implementations.webhook.httpx.AsyncClient",
        lambda **_: client,
    )

    result = await WebhookConnector().test_connectivity(
        {"destination_url": "https://hooks.example.test/workspace"},
        {},
    )

    assert result.success is True
    assert client.requests == [("HEAD", "https://hooks.example.test/workspace")]


@pytest.mark.asyncio
async def test_email_dry_run_uses_imap_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class _IMAP:
        def __init__(self, host: str, port: int) -> None:
            calls.append(f"connect:{host}:{port}")

        async def wait_hello_from_server(self) -> None:
            calls.append("hello")

        async def login(self, email: str, password: str) -> None:
            calls.append(f"login:{email}:{password}")

        async def select(self, folder: str) -> None:
            calls.append(f"select:{folder}")

        async def noop(self) -> None:
            calls.append("noop")

        async def logout(self) -> None:
            calls.append("logout")

    original_import_module = importlib.import_module

    def _import_module(name: str):
        if name == "aioimaplib":
            return SimpleNamespace(IMAP4_SSL=_IMAP)
        return original_import_module(name)

    monkeypatch.setattr(importlib, "import_module", _import_module)

    result = await EmailConnector().test_connectivity(
        {
            "imap_host": "imap.example.test",
            "imap_port": 993,
            "email_address": "owner@example.test",
            "imap_password": "imap-secret",
        },
        {},
    )

    assert result.success is True
    assert "noop" in calls


@pytest.mark.asyncio
async def test_service_test_connectivity_does_not_create_outbound_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    connector = build_connector_instance(workspace_id=workspace_id)

    class _Repository:
        def __init__(self) -> None:
            self.delivery_creates = 0

        async def get_connector_instance(self, connector_id, candidate_workspace_id):
            assert connector_id == connector.id
            assert candidate_workspace_id == workspace_id
            return connector

        async def create_delivery(self, *_args: object, **_kwargs: object) -> None:
            self.delivery_creates += 1

    class _SecretProvider:
        async def get(self, _path: str, key: str) -> str:
            return f"{key}-secret"

    class _Connector:
        async def validate_config(self, config, credential_refs) -> None:
            del config, credential_refs
            return None

        async def test_connectivity(self, config, credential_refs) -> TestResult:
            del config, credential_refs
            return TestResult(success=True, diagnostic="dry-run ok", latency_ms=4.0)

    repository = _Repository()
    monkeypatch.setattr("platform.connectors.service.get_connector", lambda _slug: _Connector())
    service = ConnectorsService(
        repository=repository,
        settings=SimpleNamespace(connectors=SimpleNamespace(route_cache_ttl_seconds=30)),
        producer=None,
        redis_client=SimpleNamespace(delete=lambda *_args: None),
        object_storage=None,
        secret_provider=_SecretProvider(),
    )

    result = await service.test_connectivity(
        workspace_id,
        connector.id,
        TestConnectivityRequest(
            config={"bot_token": {"$ref": "bot_token"}, "team_id": "T123"},
            credential_refs={"bot_token": "secret/data/connectors/test"},
        ),
    )

    assert result.result.success is True
    assert repository.delivery_creates == 0
