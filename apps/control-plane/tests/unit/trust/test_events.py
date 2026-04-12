from __future__ import annotations

from platform.common.events.registry import event_registry
from platform.trust.events import (
    CertificationEventPayload,
    CircuitBreakerActivatedPayload,
    GuardrailBlockedPayload,
    PreScreenerRuleSetActivatedPayload,
    RecertificationTriggeredPayload,
    TrustEventPublisher,
    TrustEventType,
    TrustTierUpdatedPayload,
    make_correlation,
    register_trust_event_types,
    utcnow,
)
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer


@pytest.mark.asyncio
async def test_trust_events_register_and_publish() -> None:
    register_trust_event_types()
    producer = RecordingProducer()
    publisher = TrustEventPublisher(producer)
    correlation = make_correlation(workspace_id=str(uuid4()), execution_id=str(uuid4()))

    await publisher.publish_certification_created(
        CertificationEventPayload(
            certification_id=uuid4(),
            agent_id="agent-1",
            agent_fqn="fleet:agent-1",
            agent_revision_id="rev-1",
            occurred_at=utcnow(),
        ),
        correlation,
    )
    await publisher.publish_guardrail_blocked(
        GuardrailBlockedPayload(
            blocked_action_id=uuid4(),
            agent_id="agent-1",
            agent_fqn="fleet:agent-1",
            layer="prompt_injection",
            policy_basis="blocked",
            occurred_at=utcnow(),
        ),
        correlation,
    )
    await publisher.publish_circuit_breaker_activated(
        CircuitBreakerActivatedPayload(
            agent_id="agent-1",
            workspace_id="workspace-1",
            failure_count=5,
            threshold=5,
            occurred_at=utcnow(),
        ),
        correlation,
    )
    await publisher.publish_trust_tier_updated(
        TrustTierUpdatedPayload(
            agent_id="agent-1",
            agent_fqn="fleet:agent-1",
            tier="certified",
            trust_score=0.9,
            occurred_at=utcnow(),
        ),
        correlation,
    )
    await publisher.publish_recertification_triggered(
        RecertificationTriggeredPayload(
            trigger_id=uuid4(),
            agent_id="agent-1",
            trigger_type="revision_changed",
            new_certification_id=uuid4(),
            occurred_at=utcnow(),
        ),
        correlation,
    )
    await publisher.publish_prescreener_rule_set_activated(
        PreScreenerRuleSetActivatedPayload(version=1, rule_count=2, occurred_at=utcnow()),
        correlation,
    )

    assert event_registry.is_registered(TrustEventType.certification_created.value)
    assert [event["event_type"] for event in producer.events] == [
        "certification.created",
        "guardrail.blocked",
        "circuit_breaker.activated",
        "trust_tier.updated",
        "recertification.triggered",
        "prescreener.rule_set.activated",
    ]
