from __future__ import annotations

from decimal import Decimal
from platform.billing.plans.schemas import PlanCreate, PlanVersionPublish

import pytest
from pydantic import ValidationError


def test_plan_schema_validates_tier_and_quota_nonnegative() -> None:
    created = PlanCreate(slug="pro", display_name="Pro", tier="pro")
    assert created.tier == "pro"

    payload = PlanVersionPublish(
        price_monthly=Decimal("49.00"),
        executions_per_day=500,
        quota_period_anchor="subscription_anniversary",
    )
    assert payload.price_monthly == Decimal("49.00")

    with pytest.raises(ValidationError):
        PlanCreate(slug="bad", display_name="Bad", tier="premium")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        PlanVersionPublish(executions_per_month=-1)
