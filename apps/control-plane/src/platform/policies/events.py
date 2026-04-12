from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Any, Final
from uuid import UUID

from pydantic import BaseModel


class PolicyEventType(StrEnum):
    policy_created = "policy.created"
    policy_updated = "policy.updated"
    policy_archived = "policy.archived"
    policy_attached = "policy.attached"
    policy_detached = "policy.detached"
    gate_blocked = "policy.gate.blocked"
    gate_allowed = "policy.gate.allowed"


class PolicyCreatedEvent(BaseModel):
    policy_id: UUID
    policy_name: str
    scope_type: str
    version_id: UUID
    workspace_id: UUID | None = None
    created_by: UUID | None = None


class PolicyUpdatedEvent(BaseModel):
    policy_id: UUID
    version_id: UUID
    version_number: int
    updated_by: UUID | None = None


class PolicyArchivedEvent(BaseModel):
    policy_id: UUID
    archived_by: UUID | None = None


class PolicyAttachedEvent(BaseModel):
    policy_id: UUID
    attachment_id: UUID
    target_type: str
    target_id: str | None = None


class PolicyDetachedEvent(BaseModel):
    policy_id: UUID
    attachment_id: UUID
    target_type: str
    target_id: str | None = None


class GateBlockedEvent(BaseModel):
    agent_id: UUID
    agent_fqn: str
    enforcement_component: str
    action_type: str
    target: str
    block_reason: str
    execution_id: UUID | None = None
    workspace_id: UUID | None = None
    policy_rule_ref: dict[str, Any] | None = None


class GateAllowedEvent(BaseModel):
    agent_id: UUID
    agent_fqn: str
    target: str
    execution_id: UUID | None = None
    workspace_id: UUID | None = None


POLICY_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    PolicyEventType.policy_created.value: PolicyCreatedEvent,
    PolicyEventType.policy_updated.value: PolicyUpdatedEvent,
    PolicyEventType.policy_archived.value: PolicyArchivedEvent,
    PolicyEventType.policy_attached.value: PolicyAttachedEvent,
    PolicyEventType.policy_detached.value: PolicyDetachedEvent,
    PolicyEventType.gate_blocked.value: GateBlockedEvent,
    PolicyEventType.gate_allowed.value: GateAllowedEvent,
}


def register_policies_event_types() -> None:
    for event_type, schema in POLICY_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_policy_event(
    producer: EventProducer | None,
    event_type: PolicyEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    topic: str = "policy.events",
    key: str | None = None,
    source: str = "platform.policies",
) -> None:
    if producer is None:
        return
    event_name = event_type.value if isinstance(event_type, PolicyEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    subject_id = key or str(
        payload_dict.get("policy_id")
        or payload_dict.get("agent_id")
        or correlation_ctx.correlation_id
    )
    await producer.publish(
        topic=topic,
        key=subject_id,
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )


async def publish_gate_blocked(
    producer: EventProducer | None,
    payload: GateBlockedEvent,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_policy_event(
        producer,
        PolicyEventType.gate_blocked,
        payload,
        correlation_ctx,
        topic="policy.gate.blocked",
        key=str(payload.agent_id),
    )


async def publish_gate_allowed(
    producer: EventProducer | None,
    payload: GateAllowedEvent,
    correlation_ctx: CorrelationContext,
) -> None:
    await publish_policy_event(
        producer,
        PolicyEventType.gate_allowed,
        payload,
        correlation_ctx,
        topic="policy.gate.allowed",
        key=str(payload.agent_id),
    )


@dataclass(slots=True)
class PolicyEventConsumer:
    invalidate_bundle_by_revision: Callable[[str], Awaitable[Any]]
    group_id: str = "policy-bundle-invalidator"

    def register(self, consumer_manager: EventConsumerManager) -> None:
        consumer_manager.subscribe("policy.events", self.group_id, self.handle_event)

    async def handle_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type not in {
            PolicyEventType.policy_attached.value,
            PolicyEventType.policy_detached.value,
        }:
            return
        target_id = envelope.payload.get("target_id")
        target_type = envelope.payload.get("target_type")
        if target_type != "agent_revision" or not target_id:
            return
        await self.invalidate_bundle_by_revision(str(target_id))
