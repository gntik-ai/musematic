from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID, uuid4

from pydantic import BaseModel


class TrustEventType(StrEnum):
    certification_created = "certification.created"
    certification_activated = "certification.activated"
    certification_revoked = "certification.revoked"
    certification_expired = "certification.expired"
    certification_superseded = "certification.superseded"
    trust_tier_updated = "trust_tier.updated"
    guardrail_blocked = "guardrail.blocked"
    circuit_breaker_activated = "circuit_breaker.activated"
    recertification_triggered = "recertification.triggered"
    prescreener_rule_set_activated = "prescreener.rule_set.activated"


class CertificationEventPayload(BaseModel):
    certification_id: UUID
    agent_id: str
    agent_fqn: str
    agent_revision_id: str
    occurred_at: datetime
    actor_id: str | None = None
    reason: str | None = None


class CertificationSupersededPayload(BaseModel):
    old_certification_id: UUID
    new_certification_id: UUID
    agent_id: str
    occurred_at: datetime


class TrustTierUpdatedPayload(BaseModel):
    agent_id: str
    agent_fqn: str
    tier: str
    trust_score: float
    occurred_at: datetime


class GuardrailBlockedPayload(BaseModel):
    blocked_action_id: UUID
    agent_id: str
    agent_fqn: str
    layer: str
    policy_basis: str
    execution_id: str | None = None
    workspace_id: str | None = None
    occurred_at: datetime


class CircuitBreakerActivatedPayload(BaseModel):
    agent_id: str
    workspace_id: str
    failure_count: int
    threshold: int
    occurred_at: datetime


class RecertificationTriggeredPayload(BaseModel):
    trigger_id: UUID
    agent_id: str
    trigger_type: str
    new_certification_id: UUID | None = None
    occurred_at: datetime


class PreScreenerRuleSetActivatedPayload(BaseModel):
    version: int
    rule_count: int
    occurred_at: datetime


TRUST_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    TrustEventType.certification_created.value: CertificationEventPayload,
    TrustEventType.certification_activated.value: CertificationEventPayload,
    TrustEventType.certification_revoked.value: CertificationEventPayload,
    TrustEventType.certification_expired.value: CertificationEventPayload,
    TrustEventType.certification_superseded.value: CertificationSupersededPayload,
    TrustEventType.trust_tier_updated.value: TrustTierUpdatedPayload,
    TrustEventType.guardrail_blocked.value: GuardrailBlockedPayload,
    TrustEventType.circuit_breaker_activated.value: CircuitBreakerActivatedPayload,
    TrustEventType.recertification_triggered.value: RecertificationTriggeredPayload,
    TrustEventType.prescreener_rule_set_activated.value: PreScreenerRuleSetActivatedPayload,
}


def register_trust_event_types() -> None:
    for event_type, schema in TRUST_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


class TrustEventPublisher:
    def __init__(self, producer: EventProducer | None) -> None:
        self.producer = producer

    async def publish_certification_created(
        self,
        payload: CertificationEventPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.certification_created,
            payload,
            key=payload.agent_id,
            correlation_ctx=correlation_ctx,
        )

    async def publish_certification_activated(
        self,
        payload: CertificationEventPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.certification_activated,
            payload,
            key=payload.agent_id,
            correlation_ctx=correlation_ctx,
        )

    async def publish_certification_revoked(
        self,
        payload: CertificationEventPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.certification_revoked,
            payload,
            key=payload.agent_id,
            correlation_ctx=correlation_ctx,
        )

    async def publish_certification_expired(
        self,
        payload: CertificationEventPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.certification_expired,
            payload,
            key=payload.agent_id,
            correlation_ctx=correlation_ctx,
        )

    async def publish_certification_superseded(
        self,
        payload: CertificationSupersededPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.certification_superseded,
            payload,
            key=payload.agent_id,
            correlation_ctx=correlation_ctx,
        )

    async def publish_trust_tier_updated(
        self,
        payload: TrustTierUpdatedPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.trust_tier_updated,
            payload,
            key=payload.agent_id,
            correlation_ctx=correlation_ctx,
        )

    async def publish_guardrail_blocked(
        self,
        payload: GuardrailBlockedPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.guardrail_blocked,
            payload,
            key=payload.agent_id,
            correlation_ctx=correlation_ctx,
        )

    async def publish_circuit_breaker_activated(
        self,
        payload: CircuitBreakerActivatedPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.circuit_breaker_activated,
            payload,
            key=payload.agent_id,
            correlation_ctx=correlation_ctx,
        )

    async def publish_recertification_triggered(
        self,
        payload: RecertificationTriggeredPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.recertification_triggered,
            payload,
            key=payload.agent_id,
            correlation_ctx=correlation_ctx,
        )

    async def publish_prescreener_rule_set_activated(
        self,
        payload: PreScreenerRuleSetActivatedPayload,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        await self._publish(
            TrustEventType.prescreener_rule_set_activated,
            payload,
            key=str(payload.version),
            correlation_ctx=correlation_ctx,
        )

    async def _publish(
        self,
        event_type: TrustEventType,
        payload: BaseModel,
        *,
        key: str,
        correlation_ctx: CorrelationContext | None,
    ) -> None:
        if self.producer is None:
            return
        await self.producer.publish(
            topic="trust.events",
            key=key,
            event_type=event_type.value,
            payload=payload.model_dump(mode="json"),
            correlation_ctx=correlation_ctx or CorrelationContext(correlation_id=uuid4()),
            source="platform.trust",
        )


def make_correlation(
    *,
    workspace_id: str | UUID | None = None,
    execution_id: str | UUID | None = None,
    interaction_id: str | UUID | None = None,
    goal_id: str | UUID | None = None,
    fleet_id: str | UUID | None = None,
) -> CorrelationContext:
    def _as_uuid(value: str | UUID | None) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except ValueError:
            return None

    return CorrelationContext(
        workspace_id=_as_uuid(workspace_id),
        execution_id=_as_uuid(execution_id),
        interaction_id=_as_uuid(interaction_id),
        goal_id=_as_uuid(goal_id),
        fleet_id=_as_uuid(fleet_id),
        correlation_id=uuid4(),
    )


def utcnow() -> datetime:
    return datetime.now(UTC)
