from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MCPEventType(StrEnum):
    server_registered = "mcp.server.registered"
    server_suspended = "mcp.server.suspended"
    server_deregistered = "mcp.server.deregistered"
    catalog_refreshed = "mcp.catalog.refreshed"
    catalog_stale = "mcp.catalog.stale"
    tool_invoked = "mcp.tool.invoked"
    tool_denied = "mcp.tool.denied"


class MCPEventPayload(BaseModel):
    server_id: UUID | None = None
    workspace_id: UUID | None = None
    agent_id: UUID | None = None
    agent_fqn: str | None = None
    tool_identifier: str | None = None
    direction: str | None = None
    outcome: str | None = None
    block_reason: str | None = None
    error_summary: str | None = None
    tool_count: int | None = None
    version_snapshot: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def register_mcp_event_types() -> None:
    for event_type in MCPEventType:
        event_registry.register(event_type.value, MCPEventPayload)


async def publish_mcp_event(
    producer: EventProducer | None,
    event_type: MCPEventType,
    payload: MCPEventPayload,
    correlation_ctx: CorrelationContext,
    *,
    key: str,
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic="mcp.events",
        key=key,
        event_type=event_type.value,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.mcp",
    )
