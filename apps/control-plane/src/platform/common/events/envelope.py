from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CorrelationContext(BaseModel):
    workspace_id: UUID | None = None
    conversation_id: UUID | None = None
    interaction_id: UUID | None = None
    execution_id: UUID | None = None
    fleet_id: UUID | None = None
    goal_id: UUID | None = None
    agent_fqn: str | None = None
    correlation_id: UUID


class EventEnvelope(BaseModel):
    event_type: str
    version: str = "1.0"
    source: str
    correlation_context: CorrelationContext
    trace_context: dict[str, str] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any]


def make_envelope(
    event_type: str,
    source: str,
    payload: dict[str, Any],
    correlation_context: CorrelationContext | None = None,
    *,
    agent_fqn: str | None = None,
) -> EventEnvelope:
    if correlation_context is None:
        resolved_correlation = CorrelationContext(
            correlation_id=uuid4(),
            agent_fqn=agent_fqn,
        )
    elif agent_fqn is None:
        resolved_correlation = correlation_context
    else:
        resolved_correlation = correlation_context.model_copy(update={"agent_fqn": agent_fqn})

    return EventEnvelope(
        event_type=event_type,
        source=source,
        correlation_context=resolved_correlation,
        payload=payload,
    )
