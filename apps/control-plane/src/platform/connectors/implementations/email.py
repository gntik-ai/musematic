from __future__ import annotations

import importlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
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


def _require_ref(config: dict[str, Any], credential_refs: dict[str, str], key: str) -> None:
    value = config.get(key)
    if not isinstance(value, dict) or value.get("$ref") != key:
        raise ConnectorConfigError(f"Config field '{key}' must be a credential reference.")
    if key not in credential_refs:
        raise ConnectorConfigError(f"Missing credential ref mapping for '{key}'.")


class EmailConnector:
    async def validate_config(
        self,
        config: dict[str, Any],
        credential_refs: dict[str, str],
    ) -> None:
        required = ["imap_host", "imap_port", "smtp_host", "smtp_port", "email_address"]
        for key in required:
            if config.get(key) in {None, ""}:
                raise ConnectorConfigError(f"Email connectors require '{key}'.")
        _require_ref(config, credential_refs, "imap_password")
        _require_ref(config, credential_refs, "smtp_password")

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
        del headers, path
        message_bytes = raw_body
        if not message_bytes and isinstance(payload.get("raw_email"), str):
            message_bytes = payload["raw_email"].encode("utf-8")
        parsed = BytesParser(policy=policy.default).parsebytes(message_bytes)
        content = parsed.get_body(preferencelist=("plain", "html"))
        text = content.get_content().strip() if content is not None else None
        received_at = datetime.now(UTC)
        if parsed.get("Date"):
            try:
                received_at = parsedate_to_datetime(parsed["Date"]).astimezone(UTC)
            except (TypeError, ValueError):
                pass
        original_payload = payload or {
            "subject": parsed.get("Subject"),
            "from": parsed.get("From"),
            "to": parsed.get("To"),
        }
        return InboundMessage(
            connector_instance_id=connector_instance_id,
            workspace_id=workspace_id,
            sender_identity=str(parsed.get("From", "unknown")),
            sender_display=str(parsed.get("From", "unknown")),
            channel=str(parsed.get("To", config.get("email_address", "email"))),
            content_text=text,
            content_structured=(
                {"subject": parsed.get("Subject")} if parsed.get("Subject") else None
            ),
            timestamp=received_at,
            original_payload=original_payload,
            message_id=parsed.get("Message-Id"),
        )

    async def deliver_outbound(
        self,
        request: DeliveryRequest,
        config: dict[str, Any],
    ) -> None:
        message = EmailMessage()
        message["From"] = str(config.get("from_address") or config.get("email_address"))
        message["To"] = request.destination
        message["Subject"] = str(request.metadata.get("subject", "Musematic notification"))
        if request.content_structured and isinstance(request.content_structured.get("html"), str):
            message.set_content(request.content_text or "")
            message.add_alternative(request.content_structured["html"], subtype="html")
        else:
            message.set_content(request.content_text or "")

        aiosmtplib = importlib.import_module("aiosmtplib")
        try:
            await aiosmtplib.send(
                message,
                hostname=config["smtp_host"],
                port=int(config["smtp_port"]),
                username=config["email_address"],
                password=config["smtp_password"],
                start_tls=True,
            )
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise DeliveryPermanentError(str(exc)) from exc
            raise DeliveryError(str(exc)) from exc

    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult:
        aioimaplib = importlib.import_module("aioimaplib")
        started = time.perf_counter()
        client = None
        try:
            client = aioimaplib.IMAP4_SSL(config["imap_host"], int(config["imap_port"]))
            await client.wait_hello_from_server()
            await client.login(config["email_address"], config["imap_password"])
            await client.select(config.get("inbox_folder", "INBOX"))
            await client.noop()
            await client.logout()
            return HealthCheckResult(
                ConnectorHealthStatus.healthy,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        except Exception as exc:
            return HealthCheckResult(
                ConnectorHealthStatus.unreachable,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error=str(exc),
            )
        finally:
            if client is not None:
                logout = getattr(client, "logout", None)
                if callable(logout):
                    try:
                        result = logout()
                        if hasattr(result, "__await__"):
                            await result
                    except Exception:
                        pass

    async def test_connectivity(
        self,
        config: dict[str, Any],
        credential_refs: dict[str, str],
    ) -> TestResult:
        del credential_refs
        result = await self.health_check(config)
        return TestResult(
            success=result.status is ConnectorHealthStatus.healthy,
            diagnostic=result.error or "Email IMAP NOOP succeeded.",
            latency_ms=float(result.latency_ms or 0.0),
        )


@dataclass(slots=True)
class EmailPollingJob:
    runner: Callable[[], Awaitable[None]]

    async def run(self) -> None:
        await self.runner()
