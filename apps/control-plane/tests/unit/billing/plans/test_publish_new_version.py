from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.plans.schemas import PlanVersionPublish
from platform.billing.plans.service import PlansService
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError


def _plan(plan_id: UUID) -> Plan:
    return Plan(
        id=plan_id,
        slug="pro",
        display_name="Pro",
        tier="pro",
        description=None,
        is_public=True,
        is_active=True,
        allowed_model_tier="all",
    )


def _version(plan_id: UUID, *, version: int, price: str) -> PlanVersion:
    return PlanVersion(
        id=uuid4(),
        plan_id=plan_id,
        version=version,
        price_monthly=Decimal(price),
        executions_per_day=500,
        executions_per_month=5000,
        minutes_per_day=240,
        minutes_per_month=2400,
        max_workspaces=5,
        max_agents_per_workspace=50,
        max_users_per_workspace=25,
        overage_price_per_minute=Decimal("0.1000"),
        trial_days=14,
        quota_period_anchor="subscription_anniversary",
        extras_json={},
        published_at=datetime(2026, 5, 1, tzinfo=UTC),
        deprecated_at=None,
    )


class _PlansRepository:
    def __init__(self) -> None:
        self.plan_id = uuid4()
        self.plan = _plan(self.plan_id)
        self.prior = _version(self.plan_id, version=1, price="49.00")
        self.created_by: UUID | None = None

    async def get_by_slug(self, slug: str) -> Plan | None:
        return self.plan if slug == self.plan.slug else None

    async def publish_new_version(
        self,
        plan: Plan,
        parameters: dict[str, Any],
        *,
        created_by: UUID | None = None,
    ) -> tuple[PlanVersion, PlanVersion]:
        self.created_by = created_by
        published_at = datetime(2026, 5, 2, tzinfo=UTC)
        self.prior.deprecated_at = published_at
        return self.prior, PlanVersion(
            id=uuid4(),
            plan_id=plan.id,
            version=self.prior.version + 1,
            price_monthly=parameters["price_monthly"],
            executions_per_day=parameters["executions_per_day"],
            executions_per_month=parameters["executions_per_month"],
            minutes_per_day=parameters["minutes_per_day"],
            minutes_per_month=parameters["minutes_per_month"],
            max_workspaces=parameters["max_workspaces"],
            max_agents_per_workspace=parameters["max_agents_per_workspace"],
            max_users_per_workspace=parameters["max_users_per_workspace"],
            overage_price_per_minute=parameters["overage_price_per_minute"],
            trial_days=parameters["trial_days"],
            quota_period_anchor=parameters["quota_period_anchor"],
            extras_json=parameters["extras_json"],
            published_at=published_at,
            deprecated_at=None,
            created_by=created_by,
        )


class _AuditChain:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def append(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append({"args": args, "kwargs": kwargs})


@pytest.mark.asyncio
async def test_publish_new_version_increments_deprecates_and_audits_diff() -> None:
    repository = _PlansRepository()
    audit_chain = _AuditChain()
    service = PlansService(repository, audit_chain=audit_chain)  # type: ignore[arg-type]
    actor_id = uuid4()
    tenant_id = uuid4()

    new_version = await service.publish_new_version(
        "pro",
        PlanVersionPublish(
            price_monthly=Decimal("59.00"),
            executions_per_day=500,
            executions_per_month=5000,
            minutes_per_day=240,
            minutes_per_month=2400,
            max_workspaces=5,
            max_agents_per_workspace=50,
            max_users_per_workspace=25,
            overage_price_per_minute=Decimal("0.1000"),
            trial_days=14,
            quota_period_anchor="subscription_anniversary",
        ),
        actor_id=actor_id,
        tenant_id=tenant_id,
    )

    assert new_version.version == 2
    assert new_version.created_by == actor_id
    assert repository.prior.deprecated_at == new_version.published_at
    assert audit_chain.calls[0]["kwargs"]["event_type"] == "billing.plan.published"
    assert audit_chain.calls[0]["kwargs"]["tenant_id"] == tenant_id
    assert audit_chain.calls[0]["kwargs"]["canonical_payload_json"]["diff"][
        "price_monthly"
    ] == {"from": "49.00", "to": "59.00"}


def test_publish_payload_refuses_negative_quota_fields() -> None:
    with pytest.raises(ValidationError):
        PlanVersionPublish(executions_per_day=-1)
