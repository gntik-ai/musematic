from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SubscriptionScopeType = Literal["workspace", "tenant"]
SubscriptionStatus = Literal[
    "trial",
    "active",
    "past_due",
    "cancellation_pending",
    "canceled",
    "suspended",
]


class SubscriptionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    scope_type: SubscriptionScopeType
    scope_id: UUID
    plan_id: UUID
    plan_version: int
    status: SubscriptionStatus
    started_at: datetime
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    payment_method_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class SubscriptionAdminView(SubscriptionView):
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    created_by_user_id: UUID | None = None


class SubscriptionUpgrade(BaseModel):
    target_plan_slug: str = Field(min_length=1, max_length=32)
    payment_method_token: str | None = Field(default=None, max_length=256)


class SubscriptionDowngrade(BaseModel):
    target_plan_slug: str = Field(min_length=1, max_length=32)
    effective: Literal["period_end"] = "period_end"


class SubscriptionMigrate(BaseModel):
    plan_slug: str = Field(min_length=1, max_length=32)
    plan_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=512)


class SubscriptionUsageView(BaseModel):
    metric: Literal["executions", "minutes"]
    period_start: datetime
    period_end: datetime
    quantity: Decimal
    is_overage: bool = False


class BillingSummary(BaseModel):
    subscription: SubscriptionView
    plan_slug: str
    plan_display_name: str
    current_usage: list[SubscriptionUsageView] = Field(default_factory=list)
    overage_authorized: bool = False
    reset_at: datetime
