from __future__ import annotations

from datetime import datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from uuid import UUID

from pydantic import BaseModel


class DebugLoggingSessionCreatedPayload(BaseModel):
    session_id: UUID
    requested_by: UUID
    target_type: str
    target_id: UUID
    justification: str
    started_at: datetime
    expires_at: datetime
    correlation_id: UUID


class DebugLoggingSessionExpiredPayload(BaseModel):
    session_id: UUID
    duration_ms: int
    capture_count: int
    termination_reason: str


class DebugLoggingCaptureWrittenPayload(BaseModel):
    session_id: UUID
    capture_id: UUID
    captured_at: datetime
    method: str
    path: str
    response_status: int
    duration_ms: int
    correlation_id: UUID


DEBUG_LOGGING_EVENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "debug_logging.session.created": DebugLoggingSessionCreatedPayload,
    "debug_logging.session.expired": DebugLoggingSessionExpiredPayload,
    "debug_logging.capture.written": DebugLoggingCaptureWrittenPayload,
}


def register_debug_logging_event_types() -> None:
    for event_type, schema in DEBUG_LOGGING_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_debug_logging_event(
    event_type: str,
    payload: BaseModel,
    correlation_id: UUID,
    producer: EventProducer | None,
    *,
    workspace_id: UUID | None = None,
    source: str = "platform.debug_logging",
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic="debug_logging.events",
        key=str(payload.model_dump(mode="json").get("session_id") or correlation_id),
        event_type=event_type,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=CorrelationContext(
            correlation_id=correlation_id,
            workspace_id=workspace_id,
        ),
        source=source,
    )
