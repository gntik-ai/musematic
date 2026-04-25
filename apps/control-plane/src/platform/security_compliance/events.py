from __future__ import annotations

from datetime import datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SbomPublishedPayload(BaseModel):
    sbom_id: UUID
    release_version: str
    format: str
    content_sha256: str


class ScanCompletedPayload(BaseModel):
    scan_id: UUID
    release_version: str
    scanner: str
    max_severity: str | None
    gating_result: str


class PentestFindingRaisedPayload(BaseModel):
    finding_id: UUID
    pentest_id: UUID
    severity: str
    overdue: bool = False


class SecretRotatedPayload(BaseModel):
    schedule_id: UUID
    secret_name: str
    rotation_state: str
    overlap_ends_at: datetime | None = None


class JitIssuedPayload(BaseModel):
    grant_id: UUID
    user_id: UUID
    operation: str
    expires_at: datetime


class JitRevokedPayload(BaseModel):
    grant_id: UUID
    user_id: UUID
    revoked_by: UUID


SECURITY_COMPLIANCE_EVENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "security.sbom.published": SbomPublishedPayload,
    "security.scan.completed": ScanCompletedPayload,
    "security.pentest.finding.raised": PentestFindingRaisedPayload,
    "security.secret.rotated": SecretRotatedPayload,
    "security.jit.issued": JitIssuedPayload,
    "security.jit.revoked": JitRevokedPayload,
}


def register_security_compliance_event_types() -> None:
    for event_type, schema in SECURITY_COMPLIANCE_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_security_compliance_event(
    event_type: str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    producer: EventProducer | None,
    *,
    key: str | None = None,
    source: str = "platform.security_compliance",
) -> None:
    if producer is None:
        return
    payload_data: dict[str, Any] = payload.model_dump(mode="json")
    await producer.publish(
        topic=event_type,
        key=key or str(payload_data.get("id") or correlation_ctx.correlation_id),
        event_type=event_type,
        payload=payload_data,
        correlation_ctx=correlation_ctx,
        source=source,
    )


register_security_compliance_event_types()
