from __future__ import annotations

import json
from platform.common.correlation import goal_id_var
from platform.common.events.envelope import CorrelationContext, make_envelope, parse_event_envelope
from uuid import uuid4

import pytest


def test_correlation_context_with_agent_fqn() -> None:
    context = CorrelationContext(
        correlation_id=uuid4(),
        workspace_id=uuid4(),
        agent_fqn="finance-ops:kyc-verifier",
    )

    payload = context.model_dump(mode="json")

    assert payload["agent_fqn"] == "finance-ops:kyc-verifier"


def test_correlation_context_without_agent_fqn() -> None:
    context = CorrelationContext(correlation_id=uuid4())

    assert context.agent_fqn is None


def test_correlation_context_backwards_compatible() -> None:
    legacy_payload = {
        "correlation_id": str(uuid4()),
        "workspace_id": str(uuid4()),
    }

    context = CorrelationContext.model_validate(legacy_payload)

    assert context.agent_fqn is None
    assert context.goal_id is None


def test_make_envelope_picks_up_goal_id_from_context_var() -> None:
    goal_id = uuid4()
    token = goal_id_var.set(str(goal_id))
    try:
        envelope = make_envelope("agent.created", "registry", payload={})
    finally:
        goal_id_var.reset(token)

    assert envelope.correlation_context.goal_id == goal_id


def test_explicit_goal_id_kwarg_overrides_context_var() -> None:
    context_goal_id = uuid4()
    explicit_goal_id = uuid4()
    token = goal_id_var.set(str(context_goal_id))
    try:
        envelope = make_envelope(
            "agent.created",
            "registry",
            payload={},
            goal_id=explicit_goal_id,
        )
    finally:
        goal_id_var.reset(token)

    assert envelope.correlation_context.goal_id == explicit_goal_id


def test_correlation_context_goal_id_overrides_both() -> None:
    context_goal_id = uuid4()
    explicit_goal_id = uuid4()
    token = goal_id_var.set(str(uuid4()))
    try:
        envelope = make_envelope(
            "agent.created",
            "registry",
            payload={},
            correlation_context=CorrelationContext(
                correlation_id=uuid4(),
                goal_id=context_goal_id,
            ),
            goal_id=explicit_goal_id,
        )
    finally:
        goal_id_var.reset(token)

    assert envelope.correlation_context.goal_id == context_goal_id


def test_no_goal_id_anywhere_leaves_none() -> None:
    envelope = make_envelope("agent.created", "registry", payload={})

    assert envelope.correlation_context.goal_id is None


def test_make_envelope_updates_existing_context_and_invalid_goal_var() -> None:
    goal_id = uuid4()
    context = CorrelationContext(correlation_id=uuid4())
    envelope = make_envelope(
        "agent.created",
        "registry",
        payload={},
        correlation_context=context,
        agent_fqn="ops:agent",
        goal_id=goal_id,
    )
    assert envelope.correlation_context.agent_fqn == "ops:agent"
    assert envelope.correlation_context.goal_id == goal_id

    preserved = make_envelope(
        "agent.created",
        "registry",
        payload={},
        correlation_context=CorrelationContext(correlation_id=uuid4(), goal_id=goal_id),
    )
    assert preserved.correlation_context.goal_id == goal_id

    token = goal_id_var.set("not-a-uuid")
    try:
        with pytest.raises(ValueError, match="badly formed hexadecimal UUID string"):
            make_envelope("agent.created", "registry", payload={})
    finally:
        goal_id_var.reset(token)


def test_make_envelope_updates_existing_context_one_field_at_a_time() -> None:
    goal_id = uuid4()
    with_goal = make_envelope(
        "agent.created",
        "registry",
        payload={},
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            agent_fqn="ops:agent",
        ),
        goal_id=goal_id,
    )
    assert with_goal.correlation_context.agent_fqn == "ops:agent"
    assert with_goal.correlation_context.goal_id == goal_id

    with_fqn = make_envelope(
        "agent.created",
        "registry",
        payload={},
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            goal_id=goal_id,
        ),
        agent_fqn="ops:agent",
    )
    assert with_fqn.correlation_context.goal_id == goal_id
    assert with_fqn.correlation_context.agent_fqn == "ops:agent"


def test_parse_event_envelope_normalizes_legacy_runtime_controller_payload() -> None:
    execution_id = uuid4()
    workspace_id = uuid4()
    event_id = uuid4()

    envelope = parse_event_envelope(
        {
            "event_id": str(event_id),
            "event_type": "runtime.drift.mismatch",
            "execution_id": str(execution_id),
            "occurred_at": "2026-04-22T22:13:00.000000Z",
            "correlation_context": {
                "workspace_id": str(workspace_id),
                "execution_id": str(execution_id),
            },
            "payload": {"reason": "runtime.drift.mismatch"},
        }
    )

    assert envelope.source == "runtime-controller"
    assert envelope.version == "1.0"
    assert envelope.correlation_context.correlation_id == event_id
    assert envelope.correlation_context.workspace_id == workspace_id
    assert envelope.correlation_context.execution_id == execution_id
    assert envelope.payload == {"reason": "runtime.drift.mismatch"}


def test_parse_event_envelope_unwraps_nested_envelope_bytes() -> None:
    correlation_id = uuid4()
    raw = {
        "event": {"type": "ignored"},
        "envelope": {
            "event_type": "sandbox.created",
            "source": "sandbox-manager",
            "correlation_context": {"correlation_id": str(correlation_id)},
            "payload": {"state": "creating"},
        },
    }

    envelope = parse_event_envelope(json.dumps(raw).encode("utf-8"))

    assert envelope.event_type == "sandbox.created"
    assert envelope.source == "sandbox-manager"
    assert envelope.correlation_context.correlation_id == correlation_id
    assert envelope.payload == {"state": "creating"}


def test_parse_event_envelope_promotes_legacy_fields_and_scalar_payload() -> None:
    workspace_id = uuid4()
    conversation_id = uuid4()
    interaction_id = uuid4()
    execution_id = uuid4()
    fleet_id = uuid4()
    goal_id = uuid4()

    envelope = parse_event_envelope(
        json.dumps(
            {
                "event_id": "not-a-uuid",
                "event_type": "simulation.completed",
                "workspace_id": str(workspace_id),
                "conversation_id": str(conversation_id),
                "interaction_id": str(interaction_id),
                "execution_id": str(execution_id),
                "fleet_id": str(fleet_id),
                "goal_id": str(goal_id),
                "trace_context": "not-a-dict",
                "trace_id": 123,
                "payload": ["done"],
            }
        )
    )

    assert envelope.source == "simulation-controller"
    assert envelope.correlation_context.workspace_id == workspace_id
    assert envelope.correlation_context.conversation_id == conversation_id
    assert envelope.correlation_context.interaction_id == interaction_id
    assert envelope.correlation_context.execution_id == execution_id
    assert envelope.correlation_context.fleet_id == fleet_id
    assert envelope.correlation_context.goal_id == goal_id
    assert envelope.trace_context == {"trace_id": "123"}
    assert envelope.payload == {"value": ["done"]}


def test_parse_event_envelope_uses_valid_event_id_and_empty_payload() -> None:
    event_id = uuid4()

    envelope = parse_event_envelope(
        {
            "event_id": str(event_id),
            "event_type": "sandbox.completed",
            "correlation": {},
            "payload": None,
        }
    )

    assert envelope.source == "sandbox-manager"
    assert envelope.correlation_context.correlation_id == event_id
    assert envelope.payload == {}

    generated = parse_event_envelope({"event_type": "legacy.event", "payload": {}})
    assert generated.correlation_context.correlation_id is not None
