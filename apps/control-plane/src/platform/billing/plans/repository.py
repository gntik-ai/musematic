from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.billing.exceptions import PlanVersionInProgressError
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.subscriptions.models import Subscription
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

PLAN_VERSION_FIELDS = (
    "price_monthly",
    "executions_per_day",
    "executions_per_month",
    "minutes_per_day",
    "minutes_per_month",
    "max_workspaces",
    "max_agents_per_workspace",
    "max_users_per_workspace",
    "overage_price_per_minute",
    "trial_days",
    "quota_period_anchor",
    "extras_json",
)


class PlansRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_slug(self, slug: str) -> Plan | None:
        result = await self.session.execute(select(Plan).where(Plan.slug == slug).limit(1))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Plan]:
        result = await self.session.execute(select(Plan).order_by(Plan.tier.asc(), Plan.slug.asc()))
        return list(result.scalars().all())

    async def list_filtered(
        self,
        *,
        tier: str | None = None,
        is_active: bool | None = None,
        is_public: bool | None = None,
    ) -> list[Plan]:
        statement = select(Plan)
        if tier is not None:
            statement = statement.where(Plan.tier == tier)
        if is_active is not None:
            statement = statement.where(Plan.is_active.is_(is_active))
        if is_public is not None:
            statement = statement.where(Plan.is_public.is_(is_public))
        result = await self.session.execute(statement.order_by(Plan.tier.asc(), Plan.slug.asc()))
        return list(result.scalars().all())

    async def list_public(self) -> list[Plan]:
        result = await self.session.execute(
            select(Plan)
            .where(Plan.is_public.is_(True), Plan.is_active.is_(True))
            .order_by(Plan.tier.asc(), Plan.slug.asc())
        )
        return list(result.scalars().all())

    async def create_plan(
        self,
        *,
        slug: str,
        display_name: str,
        description: str | None,
        tier: str,
        is_public: bool,
        is_active: bool,
        allowed_model_tier: str,
    ) -> Plan:
        plan = Plan(
            slug=slug,
            display_name=display_name,
            description=description,
            tier=tier,
            is_public=is_public,
            is_active=is_active,
            allowed_model_tier=allowed_model_tier,
        )
        self.session.add(plan)
        await self.session.flush()
        return plan

    async def update_plan(
        self,
        plan: Plan,
        *,
        display_name: str | None = None,
        description: str | None = None,
        is_public: bool | None = None,
        is_active: bool | None = None,
        allowed_model_tier: str | None = None,
    ) -> Plan:
        if display_name is not None:
            plan.display_name = display_name
        if description is not None:
            plan.description = description
        if is_public is not None:
            plan.is_public = is_public
        if is_active is not None:
            plan.is_active = is_active
        if allowed_model_tier is not None:
            plan.allowed_model_tier = allowed_model_tier
        await self.session.flush()
        return plan

    async def get_published_version(self, plan_id: UUID) -> PlanVersion | None:
        result = await self.session.execute(
            select(PlanVersion)
            .where(
                PlanVersion.plan_id == plan_id,
                PlanVersion.published_at.is_not(None),
                PlanVersion.deprecated_at.is_(None),
            )
            .order_by(PlanVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_versions(self, plan_id: UUID) -> list[PlanVersion]:
        result = await self.session.execute(
            select(PlanVersion)
            .where(PlanVersion.plan_id == plan_id)
            .order_by(PlanVersion.version.desc())
        )
        return list(result.scalars().all())

    async def publish_new_version(
        self,
        plan: Plan,
        parameters: dict[str, Any],
        *,
        created_by: UUID | None = None,
    ) -> tuple[PlanVersion | None, PlanVersion]:
        lock_result = await self.session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:plan_id)::bigint)"),
            {"plan_id": str(plan.id)},
        )
        if not bool(lock_result.scalar_one()):
            raise PlanVersionInProgressError(plan.id)
        current = await self.get_published_version(plan.id)
        next_version = (current.version if current is not None else 0) + 1
        now = datetime.now(UTC)
        values = _coerce_version_values(parameters)
        new_version = PlanVersion(
            plan_id=plan.id,
            version=next_version,
            published_at=now,
            created_by=created_by,
            **values,
        )
        self.session.add(new_version)
        if current is not None:
            current.deprecated_at = now
        await self.session.flush()
        return current, new_version

    async def deprecate_version(self, plan_id: UUID, version: int) -> PlanVersion | None:
        result = await self.session.execute(
            update(PlanVersion)
            .where(
                PlanVersion.plan_id == plan_id,
                PlanVersion.version == version,
                PlanVersion.deprecated_at.is_(None),
            )
            .values(deprecated_at=datetime.now(UTC))
            .returning(PlanVersion)
        )
        row = result.scalar_one_or_none()
        await self.session.flush()
        if row is not None:
            return row
        result = await self.session.execute(
            select(PlanVersion).where(
                PlanVersion.plan_id == plan_id,
                PlanVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def count_subscriptions_on_version(self, plan_id: UUID, version: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.plan_id == plan_id, Subscription.plan_version == version)
        )
        return int(result.scalar_one() or 0)

    async def count_subscriptions_for_plan(self, plan_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Subscription).where(Subscription.plan_id == plan_id)
        )
        return int(result.scalar_one() or 0)


def _coerce_version_values(parameters: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in PLAN_VERSION_FIELDS:
        if field not in parameters:
            continue
        value = parameters[field]
        if field in {"price_monthly", "overage_price_per_minute"} and not isinstance(
            value,
            Decimal,
        ):
            value = Decimal(str(value))
        if field == "extras_json":
            value = dict(value or {})
        values[field] = value
    return values
