from __future__ import annotations

from collections.abc import Mapping
from platform.notifications.canonical import (
    build_signature_headers,
    canonicalise_payload,
    derive_idempotency_key,
)
from platform.notifications.models import DeliveryOutcome, UserAlert
from typing import Any
from uuid import UUID

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

    async def send_signed(
        self,
        *,
        webhook_id: UUID,
        event_id: UUID,
        webhook_url: str,
        payload: Mapping[str, Any] | object,
        secret: bytes | str,
        platform_version: str,
    ) -> tuple[DeliveryOutcome, str | None, UUID]:
        body = canonicalise_payload(payload)
        idempotency_key = derive_idempotency_key(webhook_id, event_id)
        headers = build_signature_headers(
            webhook_id=webhook_id,
            payload=body,
            secret=secret,
            idempotency_key=idempotency_key,
            platform_version=platform_version,
        )
        try:
            response = await self._post_signed(webhook_url, body, headers)
        except httpx.TimeoutException as exc:
            return DeliveryOutcome.timed_out, str(exc), idempotency_key
        except httpx.HTTPError as exc:
            return DeliveryOutcome.timed_out, str(exc), idempotency_key
        return (*_classify_response(response), idempotency_key)

    async def _post_signed(
        self,
        webhook_url: str,
        body: bytes,
        headers: dict[str, str],
        *,
        redirects_remaining: int = 3,
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.post(webhook_url, content=body, headers=headers)
        if 300 <= response.status_code < 400 and response.headers.get("location"):
            if redirects_remaining <= 0:
                return httpx.Response(310, text="redirect_loop")
            return await self._post_signed(
                response.headers["location"],
                body,
                headers,
                redirects_remaining=redirects_remaining - 1,
            )
        return response


def _classify_response(response: httpx.Response) -> tuple[DeliveryOutcome, str | None]:
    detail = response.text or response.reason_phrase
    if 200 <= response.status_code < 300:
        return DeliveryOutcome.success, None
    if response.status_code == 310:
        return DeliveryOutcome.failed, "redirect_loop"
    if response.status_code == 429:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            return DeliveryOutcome.timed_out, f"rate_limited; retry_after={retry_after}"
        return DeliveryOutcome.timed_out, detail
    if response.status_code == 408 or response.status_code >= 500:
        return DeliveryOutcome.timed_out, detail
    return DeliveryOutcome.failed, "4xx_permanent"
