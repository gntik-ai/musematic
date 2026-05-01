from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

QuotaDecision = Literal[
    "OK",
    "HARD_CAP_EXCEEDED",
    "OVERAGE_REQUIRED",
    "OVERAGE_AUTHORIZED",
    "OVERAGE_CAP_EXCEEDED",
    "MODEL_TIER_NOT_ALLOWED",
    "NO_ACTIVE_SUBSCRIPTION",
    "SUSPENDED",
]


class UsageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    subscription_id: UUID
    metric: Literal["executions", "minutes"]
    period_start: datetime
    period_end: datetime
    quantity: Decimal
    is_overage: bool


class OverageAuthorizationCreate(BaseModel):
    max_overage_eur: Decimal | None = Field(default=None, ge=0)


class OverageAuthorizationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    subscription_id: UUID
    billing_period_start: datetime
    billing_period_end: datetime
    authorized_at: datetime
    authorized_by_user_id: UUID
    max_overage_eur: Decimal | None = None
    revoked_at: datetime | None = None
    revoked_by_user_id: UUID | None = None


class QuotaCheckResult(BaseModel):
    decision: QuotaDecision
    quota_name: str | None = None
    current: Decimal | int | None = None
    limit: Decimal | int | None = None
    reset_at: datetime | None = None
    plan_slug: str | None = None
    upgrade_url: str | None = None
    overage_available: bool = False
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.decision in {"OK", "OVERAGE_AUTHORIZED"}
