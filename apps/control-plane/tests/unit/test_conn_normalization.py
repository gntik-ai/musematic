from __future__ import annotations

from platform.connectors.implementations.email import EmailConnector
from platform.connectors.implementations.slack import SlackConnector
from platform.connectors.implementations.telegram import TelegramConnector
from platform.connectors.implementations.webhook import WebhookConnector
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_all_connector_types_normalize_to_shared_shape() -> None:
    connector_id = uuid4()
    workspace_id = uuid4()

    slack = await SlackConnector().normalize_inbound(
        connector_instance_id=connector_id,
        workspace_id=workspace_id,
        config={},
        payload={
            "type": "event_callback",
            "event": {
                "user": "U123",
                "channel": "#support-general",
                "text": "Help",
                "ts": "1712846400.000000",
            },
        },
        raw_body=b"{}",
        headers={},
    )
    telegram = await TelegramConnector().normalize_inbound(
        connector_instance_id=connector_id,
        workspace_id=workspace_id,
        config={},
        payload={
            "message": {
                "message_id": 12,
                "date": 1712846400,
                "text": "Hello",
                "from": {"id": 42, "username": "alice"},
                "chat": {"id": 99},
            }
        },
        raw_body=b"{}",
        headers={},
    )
    webhook = await WebhookConnector().normalize_inbound(
        connector_instance_id=connector_id,
        workspace_id=workspace_id,
        config={"sender_header": "x-user-id"},
        payload={"id": "evt-1", "text": "Webhook", "channel": "github"},
        raw_body=b'{"id":"evt-1"}',
        headers={"x-user-id": "octocat"},
        path="/api/v1/inbound/webhook/test",
    )
    email = await EmailConnector().normalize_inbound(
        connector_instance_id=connector_id,
        workspace_id=workspace_id,
        config={"email_address": "support@example.com"},
        payload={},
        raw_body=(
            b"From: Alice <alice@example.com>\r\n"
            b"To: support@example.com\r\n"
            b"Date: Thu, 11 Apr 2026 10:00:00 +0000\r\n"
            b"Subject: Hello\r\n\r\n"
            b"Body text"
        ),
        headers={},
    )

    for item in (slack, telegram, webhook, email):
        assert item.connector_instance_id == connector_id
        assert item.workspace_id == workspace_id
        assert hasattr(item, "sender_identity")
        assert hasattr(item, "channel")
        assert hasattr(item, "content_text")
        assert isinstance(item.original_payload, dict)

    assert slack.channel == "#support-general"
    assert telegram.sender_identity == "42"
    assert webhook.sender_identity == "octocat"
    assert email.channel == "support@example.com"
