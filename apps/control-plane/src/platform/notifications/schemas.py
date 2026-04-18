from __future__ import annotations

from datetime import datetime
from platform.notifications.models import DeliveryMethod, DeliveryOutcome
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


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
