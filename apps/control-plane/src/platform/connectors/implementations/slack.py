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


class SlackConnector:
    async def validate_config(
        self,
        config: dict[str, Any],
        credential_refs: dict[str, str],
    ) -> None:
        if not str(config.get("team_id", "")).strip():
            raise ConnectorConfigError("Slack connectors require 'team_id'.")
        _require_ref(config, credential_refs, "bot_token")
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
        del config, raw_body, headers, path
        event = payload.get("event", payload)
        if not isinstance(event, dict):
            event = {}
        timestamp = datetime.now(UTC)
        ts_value = event.get("ts")
        if isinstance(ts_value, str):
            try:
                timestamp = datetime.fromtimestamp(float(ts_value), tz=UTC)
            except ValueError:
                pass
        return InboundMessage(
            connector_instance_id=connector_instance_id,
            workspace_id=workspace_id,
            sender_identity=str(event.get("user", "unknown")),
            sender_display=None,
            channel=str(event.get("channel", "slack")),
            content_text=event.get("text") if isinstance(event.get("text"), str) else None,
            content_structured=event if event else None,
            timestamp=timestamp,
            original_payload=payload,
            message_id=(
                event.get("client_msg_id")
                if isinstance(event.get("client_msg_id"), str)
                else None
            ),
        )

    async def deliver_outbound(
        self,
        request: DeliveryRequest,
        config: dict[str, Any],
    ) -> None:
        body: dict[str, Any] = {
            "channel": request.destination,
            "text": request.content_text or "",
        }
        if request.content_structured and "blocks" in request.content_structured:
            body["blocks"] = request.content_structured["blocks"]
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {config['bot_token']}"},
                json=body,
            )
        if response.status_code >= 500:
            raise DeliveryError("Slack API is unavailable.")
        payload = response.json()
        if response.status_code >= 400 or payload.get("ok") is not True:
            raise DeliveryPermanentError(str(payload.get("error", "Slack delivery failed.")))

    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {config['bot_token']}"},
                )
            latency = (time.perf_counter() - started) * 1000.0
            payload = response.json()
            if response.status_code == 200 and payload.get("ok") is True:
                return HealthCheckResult(
                    status=ConnectorHealthStatus.healthy,
                    latency_ms=latency,
                )
            return HealthCheckResult(
                status=ConnectorHealthStatus.degraded,
                latency_ms=latency,
                error=str(payload.get("error", "Slack auth.test failed.")),
            )
        except httpx.HTTPError as exc:
            return HealthCheckResult(
                status=ConnectorHealthStatus.unreachable,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error=str(exc),
            )
