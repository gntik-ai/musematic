from __future__ import annotations

import re
from datetime import datetime
from platform.notifications.models import DeliveryMethod, DeliveryOutcome
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

_E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")
_SEVERITY_RANK = {
    "info": 0,
    "low": 0,
    "medium": 1,
    "warn": 2,
    "warning": 2,
    "high": 3,
    "critical": 4,
}


class UserAlertSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    state_transitions: list[str]
    delivery_method: DeliveryMethod
    webhook_url: str | None
    created_at: datetime
    updated_at: datetime


class UserAlertSettingsUpdate(BaseModel):
    state_transitions: list[str] = Field(min_length=1)
    delivery_method: DeliveryMethod
    webhook_url: AnyHttpUrl | None = None

    @model_validator(mode="after")
    def _validate_webhook(self) -> UserAlertSettingsUpdate:
        if self.delivery_method == DeliveryMethod.webhook and self.webhook_url is None:
            raise ValueError("webhook_url is required when delivery_method is webhook")
        return self


class UserAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alert_type: str
    title: str
    body: str | None
    urgency: str
    read: bool
    interaction_id: UUID | None
    source_reference: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class AlertDeliveryOutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_method: DeliveryMethod
    attempt_count: int
    outcome: DeliveryOutcome | None
    error_detail: str | None
    next_retry_at: datetime | None
    delivered_at: datetime | None


class UserAlertDetail(UserAlertRead):
    delivery_outcome: AlertDeliveryOutcomeRead | None


class AlertListResponse(BaseModel):
    items: list[UserAlertRead]
    next_cursor: str | None
    total_unread: int


class UnreadCountResponse(BaseModel):
    count: int


class QuietHoursConfig(BaseModel):
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str

    @field_validator("start", "end")
    @classmethod
    def _validate_hhmm(cls, value: str) -> str:
        hour, minute = value.split(":")
        if int(hour) > 23 or int(minute) > 59:
            raise ValueError("quiet-hours time must be HH:MM in 24-hour format")
        return value

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("quiet-hours timezone must be a valid IANA zone") from exc
        return value


class ChannelConfigCreate(BaseModel):
    channel_type: DeliveryMethod
    target: str = Field(min_length=1, max_length=2048)
    display_name: str | None = Field(default=None, max_length=256)
    quiet_hours: QuietHoursConfig | None = None
    alert_type_filter: list[str] | None = None
    severity_floor: str | None = Field(default=None, max_length=16)
    extra: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_target_shape(self) -> ChannelConfigCreate:
        if self.channel_type == DeliveryMethod.sms:
            if not _E164_RE.fullmatch(self.target):
                raise ValueError("sms targets must be E.164 phone numbers")
            if self.severity_floor is not None and _severity_rank(
                self.severity_floor
            ) < _severity_rank("high"):
                raise ValueError("sms severity_floor must be high or critical")
        if self.channel_type in {
            DeliveryMethod.webhook,
            DeliveryMethod.slack,
            DeliveryMethod.teams,
        } and not self.target.startswith(("http://", "https://")):
            raise ValueError("webhook, slack, and teams targets must be URLs")
        return self


class ChannelConfigUpdate(BaseModel):
    target: str | None = Field(default=None, min_length=1, max_length=2048)
    display_name: str | None = Field(default=None, max_length=256)
    enabled: bool | None = None
    quiet_hours: QuietHoursConfig | None = None
    alert_type_filter: list[str] | None = None
    severity_floor: str | None = Field(default=None, max_length=16)
    extra: dict[str, Any] | None = None


class ChannelConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    channel_type: DeliveryMethod
    target: str
    display_name: str | None
    signing_secret_ref: str | None
    enabled: bool
    verified_at: datetime | None
    verification_expires_at: datetime | None
    quiet_hours: dict[str, Any] | None
    alert_type_filter: list[str] | None
    severity_floor: str | None
    extra: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class OutboundWebhookCreate(BaseModel):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=120)
    url: AnyHttpUrl
    event_types: list[str] = Field(default_factory=list)
    retry_policy: dict[str, Any] | None = None
    region_pinned_to: str | None = Field(default=None, max_length=64)


class OutboundWebhookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: AnyHttpUrl | None = None
    event_types: list[str] | None = None
    active: bool | None = None
    retry_policy: dict[str, Any] | None = None
    region_pinned_to: str | None = Field(default=None, max_length=64)


class OutboundWebhookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    url: str
    event_types: list[str]
    signing_secret_ref: str
    active: bool
    retry_policy: dict[str, Any]
    region_pinned_to: str | None
    last_rotated_at: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class OutboundWebhookCreateResponse(OutboundWebhookRead):
    signing_secret: str


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    webhook_id: UUID
    idempotency_key: UUID
    event_id: UUID
    event_type: str
    payload: dict[str, Any]
    status: str
    failure_reason: str | None
    attempts: int
    last_attempt_at: datetime | None
    last_response_status: int | None
    next_attempt_at: datetime | None
    dead_lettered_at: datetime | None
    replayed_from: UUID | None
    replayed_by: UUID | None
    resolved_at: datetime | None = None
    resolved_by: UUID | None = None
    resolution_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class DeadLetterListItem(WebhookDeliveryRead):
    workspace_id: UUID | None = None
    webhook_name: str | None = None


class DeadLetterReplayRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=256)


class DeadLetterResolveRequest(BaseModel):
    resolution: str = Field(min_length=1, max_length=256)


class DeadLetterReplayBatchRequest(BaseModel):
    workspace_id: UUID
    webhook_id: UUID | None = None
    failure_reason: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=100, ge=1, le=500)


class DeadLetterReplayBatchResponse(BaseModel):
    job_id: UUID
    replayed: int


def _severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity.lower(), 1)
