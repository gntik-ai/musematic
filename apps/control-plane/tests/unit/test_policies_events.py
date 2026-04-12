from __future__ import annotations

from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.policies.events import (
    GateAllowedEvent,
    GateBlockedEvent,
    PolicyAttachedEvent,
    PolicyEventConsumer,
    publish_gate_allowed,
    publish_gate_blocked,
    publish_policy_event,
    register_policies_event_types,
)
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer


@pytest.mark.asyncio
async def test_publish_helpers_emit_expected_topics_and_keys() -> None:
    producer = RecordingProducer()
    correlation = CorrelationContext(correlation_id=uuid4())
    policy_id = uuid4()
    agent_id = uuid4()

    await publish_policy_event(
        producer,
        "policy.created",
        PolicyAttachedEvent(
            policy_id=policy_id,
            attachment_id=uuid4(),
            target_type="workspace",
            target_id="workspace-1",
        ),
        correlation,
    )
    await publish_gate_blocked(
        producer,
        GateBlockedEvent(
            agent_id=agent_id,
            agent_fqn="finance:agent",
            enforcement_component="tool_gateway",
            action_type="tool_invocation",
            target="finance:wire",
            block_reason="permission_denied",
        ),
        correlation,
    )
    await publish_gate_allowed(
        producer,
        GateAllowedEvent(
            agent_id=agent_id,
            agent_fqn="finance:agent",
            target="finance:read",
        ),
        correlation,
    )

    assert [event["topic"] for event in producer.events] == [
        "policy.events",
        "policy.gate.blocked",
        "policy.gate.allowed",
    ]
    assert producer.events[1]["key"] == str(agent_id)


@pytest.mark.asyncio
async def test_policy_event_consumer_invalidates_agent_revision_only() -> None:
    invalidated: list[str] = []

    async def _invalidate(revision_id: str) -> None:
        invalidated.append(revision_id)

    consumer = PolicyEventConsumer(invalidate_bundle_by_revision=_invalidate)
    register_policies_event_types()

    await consumer.handle_event(
        EventEnvelope(
            event_type="policy.attached",
            payload={"target_type": "agent_revision", "target_id": "revision-1"},
            correlation_context=CorrelationContext(correlation_id=uuid4()),
            source="tests",
        )
    )
    await consumer.handle_event(
        EventEnvelope(
            event_type="policy.updated",
            payload={"target_type": "workspace", "target_id": "workspace-1"},
            correlation_context=CorrelationContext(correlation_id=uuid4()),
            source="tests",
        )
    )

    assert invalidated == ["revision-1"]
