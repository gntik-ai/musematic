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
from platform.connectors.schemas import TestResult
from typing import Any
from uuid import UUID

import httpx


def _require_ref(config: dict[str, Any], credential_refs: dict[str, str], key: str) -> None:
    value = config.get(key)
    if not isinstance(value, dict) or value.get("$ref") != key:
        raise ConnectorConfigError(f"Config field '{key}' must be a credential reference.")
    if key not in credential_refs:
        raise ConnectorConfigError(f"Missing credential ref mapping for '{key}'.")


class TelegramConnector:
    async def validate_config(
        self,
        config: dict[str, Any],
        credential_refs: dict[str, str],
    ) -> None:
        _require_ref(config, credential_refs, "bot_token")

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
        message = payload.get("message") or payload.get("edited_message") or {}
        if not isinstance(message, dict):
            message = {}
        chat = message.get("chat", {})
        if not isinstance(chat, dict):
            chat = {}
        sender = message.get("from", {})
        if not isinstance(sender, dict):
            sender = {}
        timestamp = datetime.now(UTC)
        if isinstance(message.get("date"), int):
            timestamp = datetime.fromtimestamp(message["date"], tz=UTC)
        sender_display = sender.get("username") or sender.get("first_name") or None
        return InboundMessage(
            connector_instance_id=connector_instance_id,
            workspace_id=workspace_id,
            sender_identity=str(sender.get("id", "unknown")),
            sender_display=str(sender_display) if sender_display else None,
            channel=str(chat.get("id", "telegram")),
            content_text=message.get("text") if isinstance(message.get("text"), str) else None,
            content_structured=message if message else None,
            timestamp=timestamp,
            original_payload=payload,
            message_id=(
                str(message.get("message_id")) if message.get("message_id") is not None else None
            ),
        )

    async def deliver_outbound(
        self,
        request: DeliveryRequest,
        config: dict[str, Any],
    ) -> None:
        body: dict[str, Any] = {
            "chat_id": request.destination,
            "text": request.content_text or "",
            "parse_mode": "Markdown",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{config['bot_token']}/sendMessage",
                json=body,
            )
        if response.status_code >= 500:
            raise DeliveryError("Telegram API is unavailable.")
        payload = response.json()
        if response.status_code >= 400 or payload.get("ok") is not True:
            raise DeliveryPermanentError(
                str(payload.get("description", "Telegram delivery failed."))
            )

    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{config['bot_token']}/getMe"
                )
            latency = (time.perf_counter() - started) * 1000.0
            payload = response.json()
            if response.status_code == 200 and payload.get("ok") is True:
                return HealthCheckResult(ConnectorHealthStatus.healthy, latency_ms=latency)
            return HealthCheckResult(
                ConnectorHealthStatus.degraded,
                latency_ms=latency,
                error=str(payload.get("description", "Telegram health check failed.")),
            )
        except httpx.HTTPError as exc:
            return HealthCheckResult(
                ConnectorHealthStatus.unreachable,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error=str(exc),
            )

    async def test_connectivity(
        self,
        config: dict[str, Any],
        credential_refs: dict[str, str],
    ) -> TestResult:
        del credential_refs
        result = await self.health_check(config)
        return TestResult(
            success=result.status is ConnectorHealthStatus.healthy,
            diagnostic=result.error or "Telegram getMe succeeded.",
            latency_ms=float(result.latency_ms or 0.0),
        )
