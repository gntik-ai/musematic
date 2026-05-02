from __future__ import annotations

from platform.admin.rbac import require_superadmin
from platform.audit.dependencies import build_audit_chain_service
from platform.billing.exceptions import PlanNotFoundError, SubscriptionNotFoundError
from platform.billing.plans.models import PlanVersion
from platform.billing.plans.repository import PlansRepository
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.schemas import SubscriptionMigrate
from platform.billing.subscriptions.service import SubscriptionService
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, text

router = APIRouter(
    prefix="/api/v1/admin/subscriptions",
    tags=["admin", "billing", "subscriptions"],
)


@router.get("")
async def list_subscriptions(
    request: Request,
    status: str | None = None,
    plan_slug: str | None = None,
    limit: int = 500,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    del request
    async with database.PlatformStaffAsyncSessionLocal() as session:
        rows = await session.execute(
            text(
                """
                SELECT
                    s.id,
                    s.tenant_id,
                    t.slug AS tenant_slug,
                    s.scope_type,
                    s.scope_id,
                    p.slug AS plan_slug,
                    p.tier AS plan_tier,
                    s.plan_version,
                    s.status,
                    s.current_period_start,
                    s.current_period_end,
                    s.cancel_at_period_end,
                    s.created_at
                  FROM subscriptions s
                  JOIN plans p ON p.id = s.plan_id
                  LEFT JOIN tenants t ON t.id = s.tenant_id
                 WHERE (:status IS NULL OR s.status = :status)
                   AND (:plan_slug IS NULL OR p.slug = :plan_slug)
                 ORDER BY s.current_period_end ASC, s.created_at DESC
                 LIMIT :limit
                """
            ),
            {"status": status, "plan_slug": plan_slug, "limit": min(limit, 1000)},
        )
        return {"items": [_subscription_row(row) for row in rows.mappings().all()]}


@router.get("/{subscription_id}/usage")
async def get_subscription_usage(
    subscription_id: UUID,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        subscription = await SubscriptionsRepository(session).get_by_id(subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(subscription_id)
        rows = await session.execute(
            text(
                """
                SELECT metric, period_start, period_end, quantity, is_overage
                  FROM usage_records
                 WHERE subscription_id = :subscription_id
                 ORDER BY period_start DESC, metric ASC, is_overage ASC
                 LIMIT 200
                """
            ),
            {"subscription_id": str(subscription_id)},
        )
        return {
            "items": [
                {
                    "metric": row.metric,
                    "period_start": row.period_start.isoformat(),
                    "period_end": row.period_end.isoformat(),
                    "quantity": str(row.quantity),
                    "is_overage": row.is_overage,
                }
                for row in rows
            ]
        }


@router.get("/{subscription_id}")
async def get_subscription(
    subscription_id: UUID,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        rows = await session.execute(
            text(
                """
                SELECT
                    s.id,
                    s.tenant_id,
                    t.slug AS tenant_slug,
                    s.scope_type,
                    s.scope_id,
                    p.slug AS plan_slug,
                    p.tier AS plan_tier,
                    s.plan_version,
                    s.status,
                    s.current_period_start,
                    s.current_period_end,
                    s.cancel_at_period_end,
                    s.created_at,
                    s.stripe_customer_id,
                    s.stripe_subscription_id
                  FROM subscriptions s
                  JOIN plans p ON p.id = s.plan_id
                  LEFT JOIN tenants t ON t.id = s.tenant_id
                 WHERE s.id = :subscription_id
                 LIMIT 1
                """
            ),
            {"subscription_id": str(subscription_id)},
        )
        row = rows.mappings().one_or_none()
        if row is None:
            raise SubscriptionNotFoundError(subscription_id)
        return _subscription_row(row)


@router.post("/{subscription_id}/suspend")
async def suspend_subscription(
    subscription_id: UUID,
    request: Request,
    payload: dict[str, str] | None = None,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        service = _service(session, request)
        updated = await service.suspend(subscription_id, (payload or {}).get("reason", "admin"))
        await session.commit()
        return {"id": str(updated.id), "status": updated.status}


@router.post("/{subscription_id}/reactivate")
async def reactivate_subscription(
    subscription_id: UUID,
    request: Request,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        service = _service(session, request)
        updated = await service.reactivate(subscription_id)
        await session.commit()
        return {"id": str(updated.id), "status": updated.status}


@router.post("/{subscription_id}/migrate-version")
async def migrate_subscription_version(
    subscription_id: UUID,
    payload: SubscriptionMigrate,
    request: Request,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        plans = PlansRepository(session)
        plan = await plans.get_by_slug(payload.plan_slug)
        if plan is None:
            raise PlanNotFoundError(payload.plan_slug)
        version = await session.scalar(
            select(PlanVersion).where(
                PlanVersion.plan_id == plan.id,
                PlanVersion.version == payload.plan_version,
            )
        )
        if version is None:
            raise HTTPException(status_code=404, detail={"code": "plan_version_not_found"})
        service = _service(session, request)
        updated = await service.migrate_version(subscription_id, plan.id, payload.plan_version)
        await session.commit()
        return {"id": str(updated.id), "plan_slug": plan.slug, "plan_version": updated.plan_version}


def _service(session: Any, request: Request) -> SubscriptionService:
    producer = cast(EventProducer | None, request.app.state.clients.get("kafka"))
    settings = cast(PlatformSettings, request.app.state.settings)
    return SubscriptionService(
        session=session,
        subscriptions=SubscriptionsRepository(session),
        plans=PlansRepository(session),
        audit_chain=build_audit_chain_service(session, settings, producer),
        producer=producer,
    )


def _subscription_row(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "tenant_id": str(row["tenant_id"]),
        "tenant_slug": row["tenant_slug"],
        "scope_type": row["scope_type"],
        "scope_id": str(row["scope_id"]),
        "plan_slug": row["plan_slug"],
        "plan_tier": row["plan_tier"],
        "plan_version": row["plan_version"],
        "status": row["status"],
        "current_period_start": row["current_period_start"].isoformat(),
        "current_period_end": row["current_period_end"].isoformat(),
        "cancel_at_period_end": row["cancel_at_period_end"],
        "trial_expires_at": None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "stripe_customer_id": row.get("stripe_customer_id"),
        "stripe_subscription_id": row.get("stripe_subscription_id"),
    }
