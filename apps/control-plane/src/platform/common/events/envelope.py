from __future__ import annotations

from datetime import UTC, datetime
from platform.common.correlation import goal_id_var
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
    goal_id: UUID | None = None,
) -> EventEnvelope:
    resolved_goal_id = _resolve_goal_id(correlation_context, goal_id)
    if correlation_context is None:
        resolved_correlation = CorrelationContext(
            correlation_id=uuid4(),
            agent_fqn=agent_fqn,
            goal_id=resolved_goal_id,
        )
    elif agent_fqn is None and (
        resolved_goal_id is None or correlation_context.goal_id is not None
    ):
        resolved_correlation = correlation_context
    else:
        updates: dict[str, Any] = {}
        if agent_fqn is not None:
            updates["agent_fqn"] = agent_fqn
        if correlation_context.goal_id is None and resolved_goal_id is not None:
            updates["goal_id"] = resolved_goal_id
        resolved_correlation = correlation_context.model_copy(update=updates)

    return EventEnvelope(
        event_type=event_type,
        source=source,
        correlation_context=resolved_correlation,
        payload=payload,
    )


def _resolve_goal_id(
    correlation_context: CorrelationContext | None,
    goal_id: UUID | None,
) -> UUID | None:
    if correlation_context is not None and correlation_context.goal_id is not None:
        return correlation_context.goal_id
    if goal_id is not None:
        return goal_id
    context_goal_id = goal_id_var.get().strip()
    if not context_goal_id:
        return None
    return UUID(context_goal_id)
