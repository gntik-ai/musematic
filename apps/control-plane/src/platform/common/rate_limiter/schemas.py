from __future__ import annotations

from datetime import datetime
from platform.common.rate_limiter.models import RateLimitPrincipalType
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionTierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    description: str
    created_at: datetime
    updated_at: datetime


class RateLimitConfigUpsertRequest(BaseModel):
    principal_type: RateLimitPrincipalType
    principal_id: UUID
    subscription_tier_name: str = Field(min_length=1, max_length=32)
    requests_per_minute_override: int | None = Field(default=None, ge=1)
    requests_per_hour_override: int | None = Field(default=None, ge=1)
    requests_per_day_override: int | None = Field(default=None, ge=1)


class RateLimitConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    principal_type: RateLimitPrincipalType
    principal_id: UUID
    subscription_tier_id: UUID
    requests_per_minute_override: int | None
    requests_per_hour_override: int | None
    requests_per_day_override: int | None
    created_at: datetime
    updated_at: datetime
    subscription_tier: SubscriptionTierResponse
