from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry

from pydantic import BaseModel


class AuditChainVerifiedPayload(BaseModel):
    valid: bool
    entries_checked: int
    broken_at: int | None = None
    start_seq: int | None = None
    end_seq: int | None = None


AUDIT_EVENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "security.audit.chain.verified": AuditChainVerifiedPayload,
}


def register_audit_event_types() -> None:
    for event_type, schema in AUDIT_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_audit_chain_verified_event(
    payload: AuditChainVerifiedPayload,
    correlation_ctx: CorrelationContext,
    producer: EventProducer | None,
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic="security.audit.chain.verified",
        key=str(correlation_ctx.correlation_id),
        event_type="security.audit.chain.verified",
        payload=payload.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.audit",
    )


register_audit_event_types()
