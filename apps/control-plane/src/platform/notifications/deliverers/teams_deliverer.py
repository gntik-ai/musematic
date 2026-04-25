from __future__ import annotations

from platform.notifications.models import DeliveryOutcome, UserAlert
from typing import Any

import httpx


class TeamsDeliverer:
    async def send(
        self,
        alert: UserAlert,
        webhook_url: str,
        config: object | None = None,
    ) -> tuple[DeliveryOutcome, str | None]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json=_build_teams_payload(alert, config),
                )
        except httpx.TimeoutException as exc:
            return DeliveryOutcome.timed_out, str(exc)
        except httpx.HTTPError as exc:
            return DeliveryOutcome.timed_out, str(exc)
        return _classify_response(response)


def _build_teams_payload(alert: UserAlert, config: object | None) -> dict[str, Any]:
    extra = _extra(config)
    workspace_name = str(extra.get("workspace_name", "Workspace"))
    deep_link = str(extra.get("deep_link", extra.get("deep_link_url", "https://app.musematic.ai")))
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": alert.title,
                            "weight": "Bolder",
                            "size": "Medium",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Severity", "value": alert.urgency},
                                {"title": "Workspace", "value": workspace_name},
                            ],
                        },
                        {"type": "TextBlock", "text": alert.body or "", "wrap": True},
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "Open in Musematic",
                            "url": deep_link,
                        }
                    ],
                },
            }
        ],
    }


def _extra(config: object | None) -> dict[str, Any]:
    value = getattr(config, "extra", None)
    return value if isinstance(value, dict) else {}


def _classify_response(response: httpx.Response) -> tuple[DeliveryOutcome, str | None]:
    if 200 <= response.status_code < 300:
        return DeliveryOutcome.success, None
    if response.status_code == 429:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            return DeliveryOutcome.timed_out, f"rate_limited; retry_after={retry_after}"
        return DeliveryOutcome.timed_out, response.text or response.reason_phrase
    if response.status_code >= 500:
        return DeliveryOutcome.timed_out, response.text or response.reason_phrase
    return DeliveryOutcome.failed, "4xx_permanent"
