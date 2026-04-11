from __future__ import annotations

import time
from datetime import UTC, datetime
from platform.connectors.exceptions import (
    ConnectorConfigError,
    DeliveryError,
    DeliveryPermanentError,
)
from platform.connectors.models import ConnectorHealthStatus
from platform.connectors.plugin import DeliveryRequest, HealthCheckResult, InboundMessage
from typing import Any
from uuid import UUID

import httpx


def _require_ref(config: dict[str, Any], credential_refs: dict[str, str], key: str) -> None:
    value = config.get(key)
    if not isinstance(value, dict) or value.get("$ref") != key:
        raise ConnectorConfigError(f"Config field '{key}' must be a credential reference.")
    if key not in credential_refs:
        raise ConnectorConfigError(f"Missing credential ref mapping for '{key}'.")


class WebhookConnector:
    async def validate_config(
        self,
        config: dict[str, Any],
        credential_refs: dict[str, str],
    ) -> None:
        _require_ref(config, credential_refs, "signing_secret")

    async def normalize_inbound(
        self,
        *,
        connector_instance_id: UUID,
        workspace_id: UUID,
        config: dict[str, Any],
        payload: dict[str, Any],
        raw_body: bytes,
        headers: dict[str, str],
        path: str | None = None,
    ) -> InboundMessage:
        del raw_body
        sender_header = str(config.get("sender_header", "x-sender-id")).lower()
        sender_identity = headers.get(sender_header, "webhook")
        timestamp = datetime.now(UTC)
        if isinstance(payload.get("timestamp"), str):
            try:
                timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                pass
        channel = (
            str(payload.get("channel"))
            if payload.get("channel") is not None
            else (path or config.get("default_channel") or "webhook")
        )
        return InboundMessage(
            connector_instance_id=connector_instance_id,
            workspace_id=workspace_id,
            sender_identity=str(sender_identity),
            sender_display=None,
            channel=str(channel),
            content_text=payload.get("text") if isinstance(payload.get("text"), str) else None,
            content_structured=payload,
            timestamp=timestamp,
            original_payload=payload,
            message_id=str(payload.get("id")) if payload.get("id") is not None else None,
        )

    async def deliver_outbound(
        self,
        request: DeliveryRequest,
        config: dict[str, Any],
    ) -> None:
        destination_url = config.get("destination_url")
        if not isinstance(destination_url, str) or not destination_url.strip():
            raise DeliveryPermanentError("Webhook connector requires 'destination_url'.")
        body = {
            "destination": request.destination,
            "content_text": request.content_text,
            "content_structured": request.content_structured,
            "metadata": request.metadata,
        }
        async with httpx.AsyncClient(timeout=float(config.get("timeout_seconds", 10))) as client:
            response = await client.post(destination_url, json=body)
        if response.status_code >= 500:
            raise DeliveryError("Webhook destination is unavailable.")
        if response.status_code >= 400:
            raise DeliveryPermanentError(
                f"Webhook destination rejected delivery ({response.status_code})."
            )

    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult:
        destination_url = config.get("destination_url")
        if not isinstance(destination_url, str) or not destination_url.strip():
            return HealthCheckResult(status=ConnectorHealthStatus.healthy, latency_ms=0.0)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.head(destination_url)
            latency = (time.perf_counter() - started) * 1000.0
            if response.status_code < 400:
                return HealthCheckResult(ConnectorHealthStatus.healthy, latency_ms=latency)
            return HealthCheckResult(
                ConnectorHealthStatus.degraded,
                latency_ms=latency,
                error=f"Destination responded with {response.status_code}.",
            )
        except httpx.HTTPError as exc:
            return HealthCheckResult(
                ConnectorHealthStatus.unreachable,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error=str(exc),
            )
