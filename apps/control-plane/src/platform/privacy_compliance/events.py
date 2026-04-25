from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID, uuid4

from pydantic import BaseModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class PrivacyEventType(StrEnum):
    dsr_received = "privacy.dsr.received"
    dsr_scheduled_with_hold = "privacy.dsr.scheduled_with_hold"
    dsr_in_progress = "privacy.dsr.in_progress"
    dsr_completed = "privacy.dsr.completed"
    dsr_failed = "privacy.dsr.failed"
    deletion_cascaded = "privacy.deletion.cascaded"
    dlp_event = "privacy.dlp.event"
    pia_drafted = "privacy.pia.drafted"
    pia_submitted_for_review = "privacy.pia.submitted_for_review"
    pia_approved = "privacy.pia.approved"
    pia_rejected = "privacy.pia.rejected"
    pia_superseded = "privacy.pia.superseded"
    residency_configured = "privacy.residency.configured"
    residency_removed = "privacy.residency.removed"
    residency_violated = "privacy.residency.violated"
    consent_revoked = "privacy.consent.revoked"


class DSRLifecyclePayload(BaseModel):
    dsr_id: UUID
    subject_user_id: UUID
    request_type: str
    status: str
    occurred_at: datetime
    workspace_id: UUID | None = None
    tombstone_id: UUID | None = None
    failure_reason: str | None = None


class DeletionCascadedPayload(BaseModel):
    dsr_id: UUID
    store_name: str
    affected_count: int
    occurred_at: datetime


class DLPEventPayload(BaseModel):
    rule_id: UUID
    rule_name: str
    classification: str
    workspace_id: UUID | None = None
    execution_id: UUID | None = None
    action_taken: str
    match_summary: str
    occurred_at: datetime


class PIAPayload(BaseModel):
    pia_id: UUID
    subject_type: str
    subject_id: UUID
    status: str
    occurred_at: datetime
    actor_id: UUID | None = None


class ResidencyPayload(BaseModel):
    workspace_id: UUID
    region_code: str | None = None
    origin_region: str | None = None
    allowed_transfer_regions: list[str] = []
    occurred_at: datetime
    actor_id: UUID | None = None


class ConsentRevokedPayload(BaseModel):
    user_id: UUID
    consent_type: str
    workspace_id: UUID | None = None
    occurred_at: datetime


PRIVACY_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    PrivacyEventType.dsr_received.value: DSRLifecyclePayload,
    PrivacyEventType.dsr_scheduled_with_hold.value: DSRLifecyclePayload,
    PrivacyEventType.dsr_in_progress.value: DSRLifecyclePayload,
    PrivacyEventType.dsr_completed.value: DSRLifecyclePayload,
    PrivacyEventType.dsr_failed.value: DSRLifecyclePayload,
    PrivacyEventType.deletion_cascaded.value: DeletionCascadedPayload,
    PrivacyEventType.dlp_event.value: DLPEventPayload,
    PrivacyEventType.pia_drafted.value: PIAPayload,
    PrivacyEventType.pia_submitted_for_review.value: PIAPayload,
    PrivacyEventType.pia_approved.value: PIAPayload,
    PrivacyEventType.pia_rejected.value: PIAPayload,
    PrivacyEventType.pia_superseded.value: PIAPayload,
    PrivacyEventType.residency_configured.value: ResidencyPayload,
    PrivacyEventType.residency_removed.value: ResidencyPayload,
    PrivacyEventType.residency_violated.value: ResidencyPayload,
    PrivacyEventType.consent_revoked.value: ConsentRevokedPayload,
}


def register_privacy_event_types() -> None:
    for event_type, schema in PRIVACY_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


class PrivacyEventPublisher:
    def __init__(self, producer: EventProducer | None) -> None:
        self.producer = producer

    async def publish(
        self,
        event_type: PrivacyEventType,
        payload: BaseModel,
        *,
        key: str,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        if self.producer is None:
            return
        await self.producer.publish(
            topic=event_type.value,
            key=key,
            event_type=event_type.value,
            payload=payload.model_dump(mode="json"),
            correlation_ctx=correlation_ctx
            or CorrelationContext(correlation_id=uuid4()),
            source="privacy_compliance",
        )


def make_correlation(
    *,
    workspace_id: UUID | str | None = None,
    execution_id: UUID | str | None = None,
) -> CorrelationContext:
    return CorrelationContext(
        workspace_id=workspace_id,
        execution_id=execution_id,
        correlation_id=uuid4(),
    )
