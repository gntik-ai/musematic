from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel, Field


class TenantEventType(StrEnum):
    created = "tenants.created"
    suspended = "tenants.suspended"
    reactivated = "tenants.reactivated"
    scheduled_for_deletion = "tenants.scheduled_for_deletion"
    deletion_cancelled = "tenants.deletion_cancelled"
    deleted = "tenants.deleted"
    branding_updated = "tenants.branding_updated"


class TenantEventPayload(BaseModel):
    tenant_id: UUID


class TenantCreatedPayload(TenantEventPayload):
    slug: str
    subdomain: str
    kind: str
    region: str
    display_name: str
    first_admin_email: str
    dpa_version: str
    dpa_artifact_sha256: str | None = None


class TenantSuspendedPayload(TenantEventPayload):
    reason: str
    previous_status: str


class TenantReactivatedPayload(TenantEventPayload):
    previous_status: str


class TenantScheduledForDeletionPayload(TenantEventPayload):
    reason: str
    scheduled_deletion_at: datetime
    grace_period_hours: int
    two_pa_principal_secondary: UUID | None = None


class TenantDeletionCancelledPayload(TenantEventPayload):
    scheduled_deletion_at_was: datetime | None = None


class TenantDeletedPayload(TenantEventPayload):
    row_count_digest: dict[str, int]
    cascade_completed_at: datetime
    tombstone_sha256: str
    audit_chain_entry_seq: int | None = None


class TenantBrandingUpdatedPayload(TenantEventPayload):
    fields_changed: list[str] = Field(default_factory=list)
    previous_hash: str
    new_hash: str


TENANT_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    TenantEventType.created.value: TenantCreatedPayload,
    TenantEventType.suspended.value: TenantSuspendedPayload,
    TenantEventType.reactivated.value: TenantReactivatedPayload,
    TenantEventType.scheduled_for_deletion.value: TenantScheduledForDeletionPayload,
    TenantEventType.deletion_cancelled.value: TenantDeletionCancelledPayload,
    TenantEventType.deleted.value: TenantDeletedPayload,
    TenantEventType.branding_updated.value: TenantBrandingUpdatedPayload,
}


def register_tenant_event_types() -> None:
    for event_type, schema in TENANT_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_tenant_event(
    *,
    producer: EventProducer | None,
    event_type: TenantEventType,
    payload: TenantEventPayload,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    tenant_id = payload.tenant_id
    await producer.publish(
        topic="tenants.lifecycle",
        key=str(tenant_id),
        event_type=event_type.value,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.tenants",
    )
