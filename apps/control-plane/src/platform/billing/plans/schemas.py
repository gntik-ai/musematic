from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

PlanTier = Literal["free", "pro", "enterprise"]
AllowedModelTier = Literal["cheap_only", "standard", "all"]
QuotaPeriodAnchor = Literal["calendar_month", "subscription_anniversary"]


class PlanVersionParameters(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    price_monthly: Decimal = Field(default=Decimal("0.00"), ge=0)
    executions_per_day: int = Field(default=0, ge=0)
    executions_per_month: int = Field(default=0, ge=0)
    minutes_per_day: int = Field(default=0, ge=0)
    minutes_per_month: int = Field(default=0, ge=0)
    max_workspaces: int = Field(default=0, ge=0)
    max_agents_per_workspace: int = Field(default=0, ge=0)
    max_users_per_workspace: int = Field(default=0, ge=0)
    overage_price_per_minute: Decimal = Field(default=Decimal("0.0000"), ge=0)
    trial_days: int = Field(default=0, ge=0)
    quota_period_anchor: QuotaPeriodAnchor = "calendar_month"
    extras_json: dict[str, object] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("extras_json", "extras"),
        serialization_alias="extras",
    )


class PlanCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    tier: PlanTier
    is_public: bool = True
    is_active: bool = True
    allowed_model_tier: AllowedModelTier = "all"


class PlanUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    is_public: bool | None = None
    is_active: bool | None = None
    allowed_model_tier: AllowedModelTier | None = None


class PlanVersionPublish(PlanVersionParameters):
    created_by: UUID | None = None


class PlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    display_name: str
    description: str | None
    tier: PlanTier
    is_public: bool
    is_active: bool
    allowed_model_tier: AllowedModelTier


class PlanVersionView(PlanVersionParameters):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    version: int
    published_at: datetime | None
    deprecated_at: datetime | None
    created_at: datetime
    created_by: UUID | None


class PlanAdminView(PlanPublic):
    created_at: datetime
    current_version: PlanVersionView | None = None
    subscription_count: int = 0


class PlanVersionDiff(BaseModel):
    plan_id: UUID
    prior_version: int | None
    new_version: int
    diff: dict[str, dict[str, object | None]]
