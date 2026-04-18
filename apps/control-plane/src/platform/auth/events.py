from __future__ import annotations

from datetime import datetime
from platform.auth.models import IBORSyncMode, IBORSyncRunStatus
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class UserAuthenticatedPayload(BaseModel):
    user_id: UUID
    session_id: UUID
    ip_address: str
    device_info: str


class UserLockedPayload(BaseModel):
    user_id: UUID
    attempt_count: int
    locked_until: datetime


class SessionRevokedPayload(BaseModel):
    user_id: UUID
    session_id: UUID
    reason: str


class MfaEnrolledPayload(BaseModel):
    user_id: UUID
    method: str


class PermissionDeniedPayload(BaseModel):
    user_id: UUID
    resource_type: str
    action: str
    reason: str


class ApiKeyRotatedPayload(BaseModel):
    service_account_id: UUID


class IBORSyncCompletedPayload(BaseModel):
    run_id: UUID
    connector_id: UUID
    connector_name: str
    mode: IBORSyncMode
    status: IBORSyncRunStatus
    duration_ms: int
    counts: dict[str, int]


AUTH_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    "auth.user.authenticated": UserAuthenticatedPayload,
    "auth.user.locked": UserLockedPayload,
    "auth.session.revoked": SessionRevokedPayload,
    "auth.mfa.enrolled": MfaEnrolledPayload,
    "auth.permission.denied": PermissionDeniedPayload,
    "auth.apikey.rotated": ApiKeyRotatedPayload,
    "ibor_sync_completed": IBORSyncCompletedPayload,
}


def register_auth_event_types() -> None:
    for event_type, schema in AUTH_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_auth_event(
    event_type: str,
    payload: BaseModel,
    correlation_id: UUID,
    producer: EventProducer | None,
    *,
    workspace_id: UUID | None = None,
    source: str = "platform.auth",
) -> None:
    if producer is None:
        return
    payload_data = payload.model_dump(mode="json")
    subject_id = (
        payload_data.get("user_id")
        or payload_data.get("service_account_id")
        or payload_data.get("connector_id")
        or correlation_id
    )
    await producer.publish(
        topic="auth.events",
        key=str(subject_id),
        event_type=event_type,
        payload=payload_data,
        correlation_ctx=CorrelationContext(
            correlation_id=correlation_id,
            workspace_id=workspace_id,
        ),
        source=source,
    )


async def publish_ibor_sync_completed(
    payload: IBORSyncCompletedPayload,
    correlation_id: UUID,
    producer: EventProducer | None,
) -> None:
    await publish_auth_event(
        "ibor_sync_completed",
        payload,
        correlation_id,
        producer,
    )
