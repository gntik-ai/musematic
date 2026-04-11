from __future__ import annotations

from platform.connectors.exceptions import ConnectorTypeNotFoundError
from platform.connectors.implementations.email import EmailConnector
from platform.connectors.implementations.slack import SlackConnector
from platform.connectors.implementations.telegram import TelegramConnector
from platform.connectors.implementations.webhook import WebhookConnector
from platform.connectors.models import ConnectorTypeSlug
from platform.connectors.plugin import BaseConnector

CONNECTOR_TYPE_REGISTRY: dict[str, type[BaseConnector]] = {
    ConnectorTypeSlug.slack.value: SlackConnector,
    ConnectorTypeSlug.telegram.value: TelegramConnector,
    ConnectorTypeSlug.webhook.value: WebhookConnector,
    ConnectorTypeSlug.email.value: EmailConnector,
}


def get_connector(type_slug: str) -> BaseConnector:
    connector_cls = CONNECTOR_TYPE_REGISTRY.get(type_slug)
    if connector_cls is None:
        raise ConnectorTypeNotFoundError(type_slug)
    return connector_cls()
