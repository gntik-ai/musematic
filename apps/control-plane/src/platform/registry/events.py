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
    agent_decommissioned = "registry.agent.decommissioned"


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


class AgentDecommissionedPayload(BaseModel):
    agent_profile_id: str
    fqn: str
    decommissioned_by: str
    decommissioned_at: str
    reason: str
    active_instance_count_at_decommission: int


REGISTRY_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    RegistryEventType.agent_created.value: AgentCreatedPayload,
    RegistryEventType.agent_published.value: AgentPublishedPayload,
    RegistryEventType.agent_deprecated.value: AgentDeprecatedPayload,
    RegistryEventType.agent_decommissioned.value: AgentDecommissionedPayload,
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


async def publish_agent_decommissioned(
    producer: EventProducer | None,
    payload: AgentDecommissionedPayload,
    correlation: CorrelationContext,
) -> None:
    await publish_registry_event(
        producer,
        RegistryEventType.agent_decommissioned,
        payload,
        correlation,
    )


# --- UPD-049 marketplace lifecycle events ----------------------------------
# All published to the `marketplace.events` topic (NOT `registry.events`)
# per specs/099-marketplace-scope/contracts/marketplace-events-kafka.md.
# Partition key is `tenant_id` per UPD-046 R7 (set by EventProducer from
# CorrelationContext.tenant_id).


class MarketplaceEventType(StrEnum):
    scope_changed = "marketplace.scope_changed"
    submitted = "marketplace.submitted"
    approved = "marketplace.approved"
    rejected = "marketplace.rejected"
    published = "marketplace.published"
    deprecated = "marketplace.deprecated"
    forked = "marketplace.forked"
    source_updated = "marketplace.source_updated"


class MarketplaceScopeChangedPayload(BaseModel):
    agent_id: str
    from_scope: str
    to_scope: str
    actor_user_id: str


class MarketplaceSubmittedPayload(BaseModel):
    agent_id: str
    submitter_user_id: str
    category: str
    tags: list[str]
    marketing_description_hash: str


class MarketplaceApprovedPayload(BaseModel):
    agent_id: str
    reviewer_user_id: str
    approval_notes: str | None = None


class MarketplaceRejectedPayload(BaseModel):
    agent_id: str
    reviewer_user_id: str
    rejection_reason: str


class MarketplacePublishedPayload(BaseModel):
    agent_id: str
    published_at: str


class MarketplaceDeprecatedPayload(BaseModel):
    agent_id: str
    actor_user_id: str
    deprecation_reason: str


class MarketplaceForkedPayload(BaseModel):
    source_agent_id: str
    fork_agent_id: str
    target_scope: str
    consumer_user_id: str
    consumer_tenant_id: str


class MarketplaceSourceUpdatedPayload(BaseModel):
    source_agent_id: str
    new_version_id: str
    diff_summary_hash: str


MARKETPLACE_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    MarketplaceEventType.scope_changed.value: MarketplaceScopeChangedPayload,
    MarketplaceEventType.submitted.value: MarketplaceSubmittedPayload,
    MarketplaceEventType.approved.value: MarketplaceApprovedPayload,
    MarketplaceEventType.rejected.value: MarketplaceRejectedPayload,
    MarketplaceEventType.published.value: MarketplacePublishedPayload,
    MarketplaceEventType.deprecated.value: MarketplaceDeprecatedPayload,
    MarketplaceEventType.forked.value: MarketplaceForkedPayload,
    MarketplaceEventType.source_updated.value: MarketplaceSourceUpdatedPayload,
}


def register_marketplace_event_types() -> None:
    for event_type, schema in MARKETPLACE_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_marketplace_event(
    producer: EventProducer | None,
    event_type: MarketplaceEventType | str,
    payload: BaseModel,
    correlation: CorrelationContext,
    *,
    source: str = "platform.marketplace",
) -> None:
    if producer is None:
        return
    event_name = (
        event_type.value if isinstance(event_type, MarketplaceEventType) else event_type
    )
    payload_dict = payload.model_dump(mode="json")
    # Use agent_id (or fork_agent_id / source_agent_id for the cross-agent
    # event types) as Kafka key — keeps all events for one agent on the
    # same partition. Envelope tenant_id is set by the producer from
    # CorrelationContext.
    key = (
        payload_dict.get("agent_id")
        or payload_dict.get("fork_agent_id")
        or payload_dict.get("source_agent_id")
        or str(correlation.correlation_id)
    )
    await producer.publish(
        topic="marketplace.events",
        key=str(key),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation,
        source=source,
    )
