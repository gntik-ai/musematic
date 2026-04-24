from __future__ import annotations

from datetime import datetime
from platform.common.debug_logging.models import DebugLoggingTargetType
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DebugLoggingSessionCreateRequest(BaseModel):
    target_type: DebugLoggingTargetType
    target_id: UUID
    justification: str = Field(min_length=10)
    duration_minutes: int = Field(default=60, ge=1, le=240)


class DebugLoggingSessionResponse(BaseModel):
    session_id: UUID
    target_type: DebugLoggingTargetType
    target_id: UUID
    justification: str
    started_at: datetime
    expires_at: datetime
    terminated_at: datetime | None = None
    termination_reason: str | None = None
    capture_count: int
    requested_by: UUID
    correlation_id: UUID


class DebugLoggingSessionListResponse(BaseModel):
    items: list[DebugLoggingSessionResponse]
    next_cursor: str | None = None


class DebugLoggingCaptureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    captured_at: datetime
    method: str
    path: str
    response_status: int
    duration_ms: int
    correlation_id: UUID
    request_headers: dict[str, str]
    request_body: str | None = None
    response_headers: dict[str, str]
    response_body: str | None = None


class DebugLoggingCaptureListResponse(BaseModel):
    items: list[DebugLoggingCaptureResponse]
    next_cursor: str | None = None
