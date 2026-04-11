from __future__ import annotations

from datetime import datetime
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


AUTH_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    "auth.user.authenticated": UserAuthenticatedPayload,
    "auth.user.locked": UserLockedPayload,
    "auth.session.revoked": SessionRevokedPayload,
    "auth.mfa.enrolled": MfaEnrolledPayload,
    "auth.permission.denied": PermissionDeniedPayload,
    "auth.apikey.rotated": ApiKeyRotatedPayload,
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
    subject_id = (
        payload.model_dump().get("user_id")
        or payload.model_dump().get("service_account_id")
        or correlation_id
    )
    await producer.publish(
        topic="auth.events",
        key=str(subject_id),
        event_type=event_type,
        payload=payload.model_dump(mode="json"),
        correlation_ctx=CorrelationContext(
            correlation_id=correlation_id,
            workspace_id=workspace_id,
        ),
        source=source,
    )
