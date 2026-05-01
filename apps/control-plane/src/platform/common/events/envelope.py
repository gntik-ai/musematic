from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.correlation import goal_id_var
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CorrelationContext(BaseModel):
    tenant_id: UUID | None = None
    tenant_slug: str | None = None
    tenant_kind: str | None = None
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


def parse_event_envelope(raw_message: Any) -> EventEnvelope:
    if isinstance(raw_message, EventEnvelope):
        return raw_message
    if isinstance(raw_message, bytes):
        payload = json.loads(raw_message.decode("utf-8"))
    elif isinstance(raw_message, str):
        payload = json.loads(raw_message)
    elif isinstance(raw_message, dict):
        payload = dict(raw_message)
    else:
        raise TypeError(f"Unsupported Kafka payload type: {type(raw_message)!r}")
    return EventEnvelope.model_validate(_normalize_event_envelope_payload(payload))


def _normalize_event_envelope_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if isinstance(normalized.get("envelope"), dict):
        normalized = dict(normalized["envelope"])
    if "correlation" in normalized and "correlation_context" not in normalized:
        normalized["correlation_context"] = normalized.pop("correlation")

    raw_correlation = normalized.get("correlation_context")
    correlation = dict(raw_correlation) if isinstance(raw_correlation, dict) else {}
    if "workspace_id" not in correlation and normalized.get("workspace_id") is not None:
        correlation["workspace_id"] = normalized["workspace_id"]
    if "conversation_id" not in correlation and normalized.get("conversation_id") is not None:
        correlation["conversation_id"] = normalized["conversation_id"]
    if "interaction_id" not in correlation and normalized.get("interaction_id") is not None:
        correlation["interaction_id"] = normalized["interaction_id"]
    if "execution_id" not in correlation and normalized.get("execution_id") is not None:
        correlation["execution_id"] = normalized["execution_id"]
    if "fleet_id" not in correlation and normalized.get("fleet_id") is not None:
        correlation["fleet_id"] = normalized["fleet_id"]
    if "goal_id" not in correlation and normalized.get("goal_id") is not None:
        correlation["goal_id"] = normalized["goal_id"]
    if correlation.get("correlation_id") is None:
        correlation["correlation_id"] = _fallback_correlation_id(normalized)
    normalized["correlation_context"] = correlation

    normalized.setdefault("version", "1.0")
    normalized.setdefault("source", _infer_legacy_source(normalized))

    trace_context = normalized.get("trace_context")
    if not isinstance(trace_context, dict):
        trace_context = {}
    trace_id = normalized.get("trace_id") or correlation.get("trace_id")
    if trace_id is not None and "trace_id" not in trace_context:
        trace_context["trace_id"] = str(trace_id)
    normalized["trace_context"] = {str(key): str(value) for key, value in trace_context.items()}

    raw_payload = normalized.get("payload")
    if raw_payload is None:
        normalized["payload"] = {}
    elif not isinstance(raw_payload, dict):
        normalized["payload"] = {"value": raw_payload}

    return normalized


def _fallback_correlation_id(payload: dict[str, Any]) -> str:
    raw_event_id = payload.get("event_id")
    if raw_event_id is not None:
        raw_event_id_str = str(raw_event_id)
        try:
            UUID(raw_event_id_str)
        except ValueError:
            pass
        else:
            return raw_event_id_str
    return str(uuid4())


def _infer_legacy_source(payload: dict[str, Any]) -> str:
    event_type = str(payload.get("event_type", ""))
    if event_type.startswith("runtime."):
        return "runtime-controller"
    if event_type.startswith("sandbox."):
        return "sandbox-manager"
    if event_type.startswith("simulation."):
        return "simulation-controller"
    return "legacy-event-source"


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
