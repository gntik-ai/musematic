from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.common.events.registry import event_registry
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

BILLING_TOPIC = "billing.lifecycle"


class BillingPlanPublishedPayload(BaseModel):
    plan_id: UUID | str
    plan_slug: str
    new_version: int
    prior_version: int | None = None
    diff: dict[str, Any]
    deprecated_prior_at: datetime | str | None = None


class BillingPlanDeprecatedPayload(BaseModel):
    plan_id: UUID | str
    plan_slug: str | None = None
    version: int
    subscriptions_pinned_count: int


class BillingSubscriptionCreatedPayload(BaseModel):
    scope_type: Literal["workspace", "tenant"]
    scope_id: UUID | str
    plan_id: UUID | str
    plan_slug: str
    plan_version: int
    status: str
    started_at: datetime | str
    current_period_start: datetime | str
    current_period_end: datetime | str
    trial_expires_at: datetime | str | None = None


class BillingSubscriptionUpgradedPayload(BaseModel):
    from_plan_slug: str
    from_plan_version: int
    to_plan_slug: str
    to_plan_version: int
    effective_at: datetime | str
    prorated_charge_eur: Decimal


class BillingSubscriptionDowngradeScheduledPayload(BaseModel):
    from_plan_slug: str
    to_plan_slug: str
    scheduled_for: datetime | str


class BillingSubscriptionDowngradeCancelledPayload(BaseModel):
    had_been_scheduled_for: datetime | str


class BillingSubscriptionDowngradeEffectivePayload(BaseModel):
    from_plan_slug: str
    from_plan_version: int
    to_plan_slug: str
    to_plan_version: int
    data_exceeding_free_limits: dict[str, int] = Field(default_factory=dict)


class BillingSubscriptionSuspendedPayload(BaseModel):
    reason: str


class BillingSubscriptionReactivatedPayload(BaseModel):
    previous_status: str


class BillingSubscriptionCanceledPayload(BaseModel):
    canceled_at: datetime | str
    final_invoice_eur: Decimal = Decimal("0.00")


class BillingSubscriptionPeriodRenewedPayload(BaseModel):
    previous_period_start: datetime | str
    previous_period_end: datetime | str
    new_period_start: datetime | str
    new_period_end: datetime | str
    previous_period_overage_eur: Decimal = Decimal("0.00")


class BillingOverageAuthorizedPayload(BaseModel):
    billing_period_start: datetime | str
    max_overage_eur: Decimal | None = None
    authorized_by_user_id: UUID | str


class BillingOverageRevokedPayload(BaseModel):
    billing_period_start: datetime | str
    revoked_by_user_id: UUID | str


class BillingOverageCapReachedPayload(BaseModel):
    billing_period_start: datetime | str
    max_overage_eur: Decimal
    current_overage_eur: Decimal


def register_billing_event_types() -> None:
    event_registry.register("billing.plan.published", BillingPlanPublishedPayload)
    event_registry.register("billing.plan.deprecated", BillingPlanDeprecatedPayload)
    event_registry.register("billing.subscription.created", BillingSubscriptionCreatedPayload)
    event_registry.register("billing.subscription.upgraded", BillingSubscriptionUpgradedPayload)
    event_registry.register(
        "billing.subscription.downgrade_scheduled",
        BillingSubscriptionDowngradeScheduledPayload,
    )
    event_registry.register(
        "billing.subscription.downgrade_cancelled",
        BillingSubscriptionDowngradeCancelledPayload,
    )
    event_registry.register(
        "billing.subscription.downgrade_effective",
        BillingSubscriptionDowngradeEffectivePayload,
    )
    event_registry.register("billing.subscription.suspended", BillingSubscriptionSuspendedPayload)
    event_registry.register(
        "billing.subscription.reactivated",
        BillingSubscriptionReactivatedPayload,
    )
    event_registry.register("billing.subscription.canceled", BillingSubscriptionCanceledPayload)
    event_registry.register(
        "billing.subscription.period_renewed",
        BillingSubscriptionPeriodRenewedPayload,
    )
    event_registry.register("billing.overage.authorized", BillingOverageAuthorizedPayload)
    event_registry.register("billing.overage.revoked", BillingOverageRevokedPayload)
    event_registry.register("billing.overage.cap_reached", BillingOverageCapReachedPayload)
