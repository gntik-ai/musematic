from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from platform.connectors.models import ConnectorHealthStatus
from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@dataclass(slots=True)
class InboundMessage:
    connector_instance_id: UUID
    workspace_id: UUID
    sender_identity: str
    sender_display: str | None
    channel: str
    content_text: str | None
    content_structured: dict[str, Any] | None
    timestamp: datetime
    original_payload: dict[str, Any]
    message_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DeliveryRequest:
    connector_instance_id: UUID
    workspace_id: UUID
    destination: str
    content_text: str | None
    content_structured: dict[str, Any] | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HealthCheckResult:
    status: ConnectorHealthStatus
    latency_ms: float | None = None
    error: str | None = None


@runtime_checkable
class BaseConnector(Protocol):
    async def validate_config(
        self,
        config: dict[str, Any],
        credential_refs: dict[str, str],
    ) -> None: ...

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
    ) -> InboundMessage: ...

    async def deliver_outbound(
        self,
        request: DeliveryRequest,
        config: dict[str, Any],
    ) -> None: ...

    async def health_check(self, config: dict[str, Any]) -> HealthCheckResult: ...
