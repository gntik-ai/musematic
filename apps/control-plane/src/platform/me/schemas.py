from __future__ import annotations

from datetime import datetime
from platform.notifications.models import DeliveryMethod
from platform.privacy_compliance.models import ConsentType, DSRRequestType, DSRStatus
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MANDATORY_EVENT_PREFIXES = ("security.", "incidents.")
VALID_NOTIFICATION_CHANNELS = {item.value for item in DeliveryMethod}


class UserSessionDetail(BaseModel):
    session_id: UUID
    device_info: str | None = None
    ip_address: str | None = None
    location: str | None = None
    created_at: str | datetime | None = None
    last_activity: str | datetime | None = None
    is_current: bool = False


class UserSessionListResponse(BaseModel):
    items: list[UserSessionDetail]


class RevokeOtherSessionsResponse(BaseModel):
    sessions_revoked: int


class UserServiceAccountSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_account_id: UUID
    name: str
    role: str
    status: str
    workspace_id: UUID | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    api_key_prefix: str


class UserServiceAccountListResponse(BaseModel):
    items: list[UserServiceAccountSummary]
    max_active: int = 10


class UserServiceAccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    mfa_token: str | None = Field(default=None, min_length=6, max_length=64)


class UserServiceAccountCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_account_id: UUID
    name: str
    role: str
    api_key: str


class UserConsentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consent_type: ConsentType
    granted: bool
    granted_at: datetime
    revoked_at: datetime | None = None
    workspace_id: UUID | None = None


class UserConsentListResponse(BaseModel):
    items: list[UserConsentItem]


class UserConsentRevokeRequest(BaseModel):
    consent_type: ConsentType


class UserConsentHistoryResponse(BaseModel):
    items: list[UserConsentItem]


class UserDSRSubmitRequest(BaseModel):
    request_type: DSRRequestType
    legal_basis: str | None = Field(default=None, max_length=256)
    hold_hours: int = Field(default=0, ge=0, le=72)
    confirm_text: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _validate_erasure_confirmation(self) -> UserDSRSubmitRequest:
        if self.request_type == DSRRequestType.erasure and self.confirm_text != "DELETE":
            raise ValueError('erasure requests require confirm_text="DELETE"')
        return self


class UserDSRDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_user_id: UUID
    request_type: DSRRequestType
    requested_by: UUID
    status: DSRStatus
    legal_basis: str | None = None
    scheduled_release_at: datetime | None = None
    requested_at: datetime
    completed_at: datetime | None = None
    completion_proof_hash: str | None = None
    failure_reason: str | None = None
    tombstone_id: UUID | None = None


class UserDSRListResponse(BaseModel):
    items: list[UserDSRDetailResponse]
    next_cursor: str | None = None


class UserActivityItem(BaseModel):
    id: UUID
    event_type: str | None = None
    audit_event_source: str
    severity: str
    created_at: datetime
    canonical_payload: dict[str, Any] | None = None


class UserActivityListResponse(BaseModel):
    items: list[UserActivityItem]
    next_cursor: str | None = None


class UserNotificationPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state_transitions: list[str]
    delivery_method: DeliveryMethod
    webhook_url: str | None = None
    per_channel_preferences: dict[str, list[str]] = Field(default_factory=dict)
    digest_mode: dict[str, str] = Field(default_factory=dict)
    quiet_hours: dict[str, Any] | None = None


class UserNotificationPreferencesUpdateRequest(BaseModel):
    state_transitions: list[str] | None = None
    delivery_method: DeliveryMethod | None = None
    webhook_url: str | None = None
    per_channel_preferences: dict[str, list[str]] = Field(default_factory=dict)
    digest_mode: dict[str, str] = Field(default_factory=dict)
    quiet_hours: dict[str, Any] | None = None

    @field_validator("per_channel_preferences")
    @classmethod
    def _validate_channels(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for event_type, channels in value.items():
            unknown = set(channels) - VALID_NOTIFICATION_CHANNELS
            if unknown:
                raise ValueError(f"unknown notification channels: {sorted(unknown)}")
            if event_type.startswith(MANDATORY_EVENT_PREFIXES) and len(channels) == 0:
                raise ValueError("mandatory events must keep at least one channel enabled")
        return value


class UserNotificationTestResponse(BaseModel):
    alert_id: UUID
    event_type: str
    delivery_method: DeliveryMethod = DeliveryMethod.in_app
    success: bool = True
