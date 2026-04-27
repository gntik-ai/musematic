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



class OAuthSignInSucceededPayload(BaseModel):
    user_id: UUID
    provider_type: str
    external_id: str


class OAuthSignInFailedPayload(BaseModel):
    provider_type: str
    failure_reason: str
    external_id: str | None = None


class OAuthUserProvisionedPayload(BaseModel):
    user_id: UUID
    provider_type: str
    external_id: str
    email: str


class OAuthAccountLinkedPayload(BaseModel):
    user_id: UUID
    provider_type: str
    external_id: str


class OAuthAccountUnlinkedPayload(BaseModel):
    user_id: UUID
    provider_type: str


class OAuthProviderConfiguredPayload(BaseModel):
    actor_id: UUID
    provider_type: str
    enabled: bool


class OAuthProviderBootstrappedPayload(BaseModel):
    actor_id: UUID | None = None
    provider_type: str
    source: str
    force_update_used: bool = False


class OAuthSecretRotatedPayload(BaseModel):
    actor_id: UUID
    provider_type: str
    old_version: int | None = None
    new_version: int | None = None


class OAuthConfigReseededPayload(BaseModel):
    actor_id: UUID | None = None
    provider_type: str
    force_update: bool
    changed_fields: list[str]


class OAuthRoleMappingUpdatedPayload(BaseModel):
    actor_id: UUID
    provider_type: str
    before_count: int
    after_count: int


class OAuthRateLimitUpdatedPayload(BaseModel):
    actor_id: UUID
    provider_type: str
    before: dict[str, int] | None = None
    after: dict[str, int]


class OAuthConfigImportedPayload(BaseModel):
    actor_id: UUID
    provider_type: str
    vault_path: str


class OAuthConfigExportedPayload(BaseModel):
    actor_id: UUID
    provider_type: str
    target_env: str


AUTH_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    "auth.user.authenticated": UserAuthenticatedPayload,
    "auth.user.locked": UserLockedPayload,
    "auth.session.revoked": SessionRevokedPayload,
    "auth.mfa.enrolled": MfaEnrolledPayload,
    "auth.permission.denied": PermissionDeniedPayload,
    "auth.apikey.rotated": ApiKeyRotatedPayload,
    "ibor_sync_completed": IBORSyncCompletedPayload,
    "auth.oauth.sign_in_succeeded": OAuthSignInSucceededPayload,
    "auth.oauth.sign_in_failed": OAuthSignInFailedPayload,
    "auth.oauth.user_provisioned": OAuthUserProvisionedPayload,
    "auth.oauth.account_linked": OAuthAccountLinkedPayload,
    "auth.oauth.account_unlinked": OAuthAccountUnlinkedPayload,
    "auth.oauth.provider_configured": OAuthProviderConfiguredPayload,
    "auth.oauth.provider_bootstrapped": OAuthProviderBootstrappedPayload,
    "auth.oauth.secret_rotated": OAuthSecretRotatedPayload,
    "auth.oauth.config_reseeded": OAuthConfigReseededPayload,
    "auth.oauth.role_mapping_updated": OAuthRoleMappingUpdatedPayload,
    "auth.oauth.rate_limit_updated": OAuthRateLimitUpdatedPayload,
    "auth.oauth.config_imported": OAuthConfigImportedPayload,
    "auth.oauth.config_exported": OAuthConfigExportedPayload,
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
