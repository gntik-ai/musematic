from __future__ import annotations

from platform.notifications.models import DeliveryOutcome, UserAlert

import httpx


class WebhookDeliverer:
    async def send(
        self,
        alert: UserAlert,
        webhook_url: str,
    ) -> tuple[DeliveryOutcome, str | None]:
        payload = {
            "id": str(alert.id),
            "alert_type": alert.alert_type,
            "title": alert.title,
            "body": alert.body,
            "urgency": alert.urgency,
            "created_at": alert.created_at.isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=payload)
        except httpx.TimeoutException as exc:
            return DeliveryOutcome.timed_out, str(exc)
        except httpx.HTTPError as exc:
            return DeliveryOutcome.failed, str(exc)
        if 200 <= response.status_code < 300:
            return DeliveryOutcome.success, None
        if response.status_code >= 500:
            return DeliveryOutcome.timed_out, response.text or response.reason_phrase
        return DeliveryOutcome.failed, response.text or response.reason_phrase
