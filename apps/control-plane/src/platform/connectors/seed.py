from __future__ import annotations

import asyncio
from platform.common import database
from platform.connectors.models import ConnectorType

from sqlalchemy import select


def _connector_type_seed_data() -> list[dict[str, object]]:
    return [
        {
            "slug": "slack",
            "display_name": "Slack",
            "description": "Slack Events API and outbound chat.postMessage connector.",
            "config_schema": {
                "type": "object",
                "properties": {
                    "team_id": {"type": "string"},
                    "default_channel": {"type": "string"},
                    "bot_token": {"type": "object"},
                    "signing_secret": {"type": "object"},
                },
                "required": ["team_id", "bot_token", "signing_secret"],
            },
        },
        {
            "slug": "telegram",
            "display_name": "Telegram",
            "description": "Telegram Bot API connector.",
            "config_schema": {
                "type": "object",
                "properties": {
                    "bot_token": {"type": "object"},
                    "default_chat_id": {"type": "string"},
                },
                "required": ["bot_token"],
            },
        },
        {
            "slug": "webhook",
            "display_name": "Webhook",
            "description": "Generic webhook ingress and outbound HTTP POST connector.",
            "config_schema": {
                "type": "object",
                "properties": {
                    "signing_secret": {"type": "object"},
                    "destination_url": {"type": "string"},
                    "sender_header": {"type": "string"},
                },
                "required": ["signing_secret"],
            },
        },
        {
            "slug": "email",
            "display_name": "Email",
            "description": "IMAP/SMTP email connector with polling for inbound messages.",
            "config_schema": {
                "type": "object",
                "properties": {
                    "imap_host": {"type": "string"},
                    "imap_port": {"type": "integer"},
                    "smtp_host": {"type": "string"},
                    "smtp_port": {"type": "integer"},
                    "email_address": {"type": "string"},
                    "imap_password": {"type": "object"},
                    "smtp_password": {"type": "object"},
                    "poll_interval_seconds": {"type": "integer"},
                    "inbox_folder": {"type": "string"},
                },
                "required": [
                    "imap_host",
                    "imap_port",
                    "smtp_host",
                    "smtp_port",
                    "email_address",
                    "imap_password",
                    "smtp_password",
                ],
            },
        },
    ]


async def seed_connector_types() -> None:
    async with database.AsyncSessionLocal() as session:
        for item in _connector_type_seed_data():
            result = await session.execute(
                select(ConnectorType).where(ConnectorType.slug == str(item["slug"]))
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                session.add(ConnectorType(**item))
                continue
            existing.display_name = str(item["display_name"])
            existing.description = (
                item["description"] if isinstance(item["description"], str) else None
            )
            config_schema = item["config_schema"]
            if not isinstance(config_schema, dict):
                raise TypeError("Connector config_schema seed must be a mapping.")
            existing.config_schema = dict(config_schema)
            existing.is_deprecated = False
            existing.deprecated_at = None
            existing.deprecation_note = None
        await session.commit()


def main() -> None:
    asyncio.run(seed_connector_types())


if __name__ == "__main__":
    main()
