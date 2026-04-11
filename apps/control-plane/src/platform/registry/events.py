from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final

from pydantic import BaseModel


class RegistryEventType(StrEnum):
    agent_created = "registry.agent.created"
    agent_published = "registry.agent.published"
    agent_deprecated = "registry.agent.deprecated"


class AgentCreatedPayload(BaseModel):
    agent_profile_id: str
    fqn: str
    namespace: str
    workspace_id: str
    revision_id: str
    version: str
    maturity_level: int
    role_types: list[str]


class AgentPublishedPayload(BaseModel):
    agent_profile_id: str
    fqn: str
    workspace_id: str
    published_by: str


class AgentDeprecatedPayload(BaseModel):
    agent_profile_id: str
    fqn: str
    workspace_id: str
    deprecated_by: str
    reason: str | None = None


REGISTRY_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    RegistryEventType.agent_created.value: AgentCreatedPayload,
    RegistryEventType.agent_published.value: AgentPublishedPayload,
    RegistryEventType.agent_deprecated.value: AgentDeprecatedPayload,
}


def register_registry_event_types() -> None:
    for event_type, schema in REGISTRY_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_registry_event(
    producer: EventProducer | None,
    event_type: RegistryEventType | str,
    payload: BaseModel,
    correlation: CorrelationContext,
    *,
    source: str = "platform.registry",
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, RegistryEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    subject_id = payload_dict.get("agent_profile_id") or str(correlation.correlation_id)
    await producer.publish(
        topic="registry.events",
        key=str(subject_id),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation,
        source=source,
    )


async def publish_agent_created(
    producer: EventProducer | None,
    payload: AgentCreatedPayload,
    correlation: CorrelationContext,
) -> None:
    await publish_registry_event(
        producer,
        RegistryEventType.agent_created,
        payload,
        correlation,
    )


async def publish_agent_published(
    producer: EventProducer | None,
    payload: AgentPublishedPayload,
    correlation: CorrelationContext,
) -> None:
    await publish_registry_event(
        producer,
        RegistryEventType.agent_published,
        payload,
        correlation,
    )


async def publish_agent_deprecated(
    producer: EventProducer | None,
    payload: AgentDeprecatedPayload,
    correlation: CorrelationContext,
) -> None:
    await publish_registry_event(
        producer,
        RegistryEventType.agent_deprecated,
        payload,
        correlation,
    )
