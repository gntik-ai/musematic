from __future__ import annotations

from platform.common.events.registry import event_registry
from platform.registry.events import (
    AgentCreatedPayload,
    AgentDeprecatedPayload,
    AgentPublishedPayload,
    RegistryEventType,
    publish_agent_created,
    publish_agent_deprecated,
    publish_agent_published,
    publish_registry_event,
    register_registry_event_types,
)
from uuid import uuid4

import pytest

from tests.registry_support import build_correlation, build_recording_producer


def test_register_registry_event_types_populates_registry() -> None:
    register_registry_event_types()

    assert event_registry.is_registered(RegistryEventType.agent_created.value) is True
    assert event_registry.is_registered(RegistryEventType.agent_published.value) is True
    assert event_registry.is_registered(RegistryEventType.agent_deprecated.value) is True


@pytest.mark.asyncio
async def test_publish_registry_events_emit_expected_payloads() -> None:
    producer = build_recording_producer()
    correlation = build_correlation(uuid4(), agent_fqn="finance:planner")

    await publish_agent_created(
        producer,
        AgentCreatedPayload(
            agent_profile_id=str(uuid4()),
            fqn="finance:planner",
            namespace="finance",
            workspace_id=str(uuid4()),
            revision_id=str(uuid4()),
            version="1.0.0",
            maturity_level=1,
            role_types=["executor"],
        ),
        correlation,
    )
    await publish_agent_published(
        producer,
        AgentPublishedPayload(
            agent_profile_id=str(uuid4()),
            fqn="finance:planner",
            workspace_id=str(uuid4()),
            published_by=str(uuid4()),
        ),
        correlation,
    )
    await publish_agent_deprecated(
        producer,
        AgentDeprecatedPayload(
            agent_profile_id=str(uuid4()),
            fqn="finance:planner",
            workspace_id=str(uuid4()),
            deprecated_by=str(uuid4()),
            reason="superseded",
        ),
        correlation,
    )
    await publish_registry_event(
        None,
        RegistryEventType.agent_created,
        AgentCreatedPayload(
            agent_profile_id=str(uuid4()),
            fqn="finance:planner",
            namespace="finance",
            workspace_id=str(uuid4()),
            revision_id=str(uuid4()),
            version="1.0.0",
            maturity_level=1,
            role_types=["executor"],
        ),
        correlation,
    )

    assert [event["event_type"] for event in producer.events] == [
        "registry.agent.created",
        "registry.agent.published",
        "registry.agent.deprecated",
    ]
    assert all(event["correlation_ctx"].agent_fqn == "finance:planner" for event in producer.events)
