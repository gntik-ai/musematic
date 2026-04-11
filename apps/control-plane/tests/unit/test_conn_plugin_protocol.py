from __future__ import annotations

from platform.connectors.exceptions import ConnectorConfigError
from platform.connectors.implementations.email import EmailConnector
from platform.connectors.implementations.slack import SlackConnector
from platform.connectors.implementations.telegram import TelegramConnector
from platform.connectors.implementations.webhook import WebhookConnector
from platform.connectors.plugin import BaseConnector

import pytest


@pytest.mark.parametrize(
    ("connector", "config", "credential_refs"),
    [
        (
            SlackConnector(),
            {
                "team_id": "T1",
                "bot_token": {"$ref": "bot_token"},
                "signing_secret": {"$ref": "signing_secret"},
            },
            {"bot_token": "vault/bot_token", "signing_secret": "vault/signing_secret"},
        ),
        (
            TelegramConnector(),
            {"bot_token": {"$ref": "bot_token"}},
            {"bot_token": "vault/bot_token"},
        ),
        (
            WebhookConnector(),
            {"signing_secret": {"$ref": "signing_secret"}},
            {"signing_secret": "vault/signing_secret"},
        ),
        (
            EmailConnector(),
            {
                "imap_host": "imap.example.com",
                "imap_port": 993,
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "email_address": "support@example.com",
                "imap_password": {"$ref": "imap_password"},
                "smtp_password": {"$ref": "smtp_password"},
            },
            {"imap_password": "vault/imap_password", "smtp_password": "vault/smtp_password"},
        ),
    ],
)
@pytest.mark.asyncio
async def test_connector_implementations_satisfy_protocol_and_validate_min_config(
    connector: BaseConnector,
    config: dict[str, object],
    credential_refs: dict[str, str],
) -> None:
    assert isinstance(connector, BaseConnector)
    await connector.validate_config(config, credential_refs)


@pytest.mark.parametrize(
    "connector",
    [SlackConnector(), TelegramConnector(), WebhookConnector(), EmailConnector()],
)
@pytest.mark.asyncio
async def test_connector_validate_config_rejects_missing_required_fields(
    connector: BaseConnector,
) -> None:
    with pytest.raises(ConnectorConfigError):
        await connector.validate_config({}, {})
