from __future__ import annotations

from platform.common.correlation import goal_id_var
from platform.common.events.envelope import CorrelationContext, make_envelope
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
