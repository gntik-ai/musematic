from __future__ import annotations

import platform.policies as policies
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.policies.events import (
    PolicyAttachedEvent,
    PolicyEventConsumer,
    publish_policy_event,
)
from platform.policies.exceptions import (
    PoliciesError,
    PolicyAttachmentError,
    PolicyCompilationError,
    PolicyNotFoundError,
    PolicyViolationError,
)
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer


def test_policy_package_lazy_exports_and_exceptions() -> None:
    assert callable(policies.get_policy_service)
    assert callable(policies.get_tool_gateway_service)
    assert callable(policies.get_memory_write_gate_service)

    missing_name = "missing_symbol"
    with pytest.raises(AttributeError):
        getattr(policies, missing_name)

    assert PoliciesError("POLICY", "problem").status_code == 400
    assert PolicyNotFoundError("policy-1").status_code == 404
    assert PolicyViolationError("blocked").code == "POLICY_VIOLATION"
    assert PolicyCompilationError("invalid").code == "POLICY_COMPILATION_ERROR"
    assert PolicyAttachmentError("invalid").status_code == 422


@pytest.mark.asyncio
async def test_policy_event_helpers_cover_noop_publish_and_consumer_registration() -> None:
    correlation = CorrelationContext(correlation_id=uuid4())
    await publish_policy_event(
        None,
        "policy.created",
        PolicyAttachedEvent(
            policy_id=uuid4(),
            attachment_id=uuid4(),
            target_type="workspace",
            target_id="workspace-1",
        ),
        correlation,
    )

    subscriptions: list[tuple[str, str]] = []

    class ManagerStub:
        def subscribe(self, topic, group_id, handler):
            del handler
            subscriptions.append((topic, group_id))

    invalidated: list[str] = []

    async def invalidate(revision_id: str) -> None:
        invalidated.append(revision_id)

    consumer = PolicyEventConsumer(invalidate_bundle_by_revision=invalidate)
    consumer.register(ManagerStub())
    await consumer.handle_event(
        EventEnvelope(
            event_type="policy.attached",
            payload={"target_type": "workspace", "target_id": "workspace-1"},
            correlation_context=correlation,
            source="tests",
        )
    )

    assert subscriptions == [("policy.events", "policy-bundle-invalidator")]
    assert invalidated == []


@pytest.mark.asyncio
async def test_publish_policy_event_uses_default_subject_when_key_missing() -> None:
    producer = RecordingProducer()
    correlation = CorrelationContext(correlation_id=uuid4())
    await publish_policy_event(
        producer,
        "policy.custom",
        PolicyAttachedEvent(
            policy_id=uuid4(),
            attachment_id=uuid4(),
            target_type="workspace",
            target_id="workspace-1",
        ),
        correlation,
        key=None,
    )

    assert producer.events[0]["key"]
