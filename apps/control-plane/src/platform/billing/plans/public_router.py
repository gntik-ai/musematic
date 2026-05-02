from __future__ import annotations

from decimal import Decimal
from platform.billing.plans.models import PlanVersion
from platform.billing.plans.repository import PlansRepository
from platform.common.dependencies import get_db
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/public/plans", tags=["billing", "public-plans"])


@router.get("")
async def list_public_plans(
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    response.headers["Cache-Control"] = "public, max-age=60"
    repository = PlansRepository(session)
    plans = await repository.list_public()
    items: list[dict[str, Any]] = []
    for plan in plans:
        current = await repository.get_published_version(plan.id)
        if current is None:
            continue
        items.append(
            {
                "slug": plan.slug,
                "display_name": plan.display_name,
                "description": plan.description,
                "tier": plan.tier,
                "allowed_model_tier": plan.allowed_model_tier,
                "current_version": _public_version(current),
            }
        )
    return {"plans": items}


def _public_version(version: PlanVersion) -> dict[str, Any]:
    return {
        "version": version.version,
        "price_monthly_eur": _decimal(version.price_monthly),
        "executions_per_day": version.executions_per_day,
        "executions_per_month": version.executions_per_month,
        "minutes_per_day": version.minutes_per_day,
        "minutes_per_month": version.minutes_per_month,
        "max_workspaces": version.max_workspaces,
        "max_agents_per_workspace": version.max_agents_per_workspace,
        "max_users_per_workspace": version.max_users_per_workspace,
        "overage_price_per_minute_eur": _decimal(version.overage_price_per_minute),
        "trial_days": version.trial_days,
    }


def _decimal(value: Decimal) -> str:
    return format(value, "f")
