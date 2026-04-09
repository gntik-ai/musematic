from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class CorrelationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str | None = None
    execution_id: str | None = None
    interaction_id: str | None = None
    fleet_id: str | None = None
    goal_id: str | None = None
    trace_id: str | None = None


class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID
    event_type: str
    schema_version: str
    occurred_at: datetime
    actor: str
    correlation: CorrelationContext = Field(default_factory=CorrelationContext)
    payload: dict[str, Any]


def make_envelope(
    event_type: str,
    actor: str,
    payload: dict[str, Any],
    correlation: CorrelationContext | None = None,
    schema_version: str = "1.0.0",
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        schema_version=schema_version,
        occurred_at=datetime.now(timezone.utc),
        actor=actor,
        correlation=correlation or CorrelationContext(),
        payload=payload,
    )

