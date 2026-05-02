from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.audit.dependencies import build_audit_chain_service
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.plans.repository import PlansRepository
from platform.billing.providers.protocol import PaymentProvider
from platform.billing.quotas.dependencies import build_quota_enforcer
from platform.billing.quotas.models import OverageAuthorization
from platform.billing.quotas.overage import OverageService
from platform.billing.quotas.schemas import OverageAuthorizationCreate
from platform.billing.quotas.usage_repository import UsageRepository
from platform.billing.subscriptions.models import Subscription
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.resolver import SubscriptionResolver
from platform.billing.subscriptions.schemas import SubscriptionDowngrade, SubscriptionUpgrade
from platform.billing.subscriptions.service import SubscriptionService
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user, get_db
from platform.common.events.producer import EventProducer
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/billing",
    tags=["billing", "workspace-billing"],
)


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _payment_provider(request: Request) -> PaymentProvider | None:
    return cast(PaymentProvider | None, getattr(request.app.state, "payment_provider", None))


async def _require_workspace_member(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> str:
    role = await session.scalar(
        text(
            """
            SELECT role::text
              FROM workspaces_memberships
             WHERE workspace_id = :workspace_id
               AND user_id = :user_id
             LIMIT 1
            """
        ),
        {"workspace_id": str(workspace_id), "user_id": str(user_id)},
    )
    if role is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"})
    return str(role)


async def _require_workspace_admin(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> None:
    role = await _require_workspace_member(session, workspace_id, user_id)
    if role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail={"code": "not_workspace_admin"})


async def _subscription_context(
    session: AsyncSession,
    workspace_id: UUID,
) -> tuple[Subscription, Plan, PlanVersion]:
    subscription = await SubscriptionResolver(session).resolve_active_subscription(workspace_id)
    result = await session.execute(
        select(Plan, PlanVersion)
        .join(PlanVersion, PlanVersion.plan_id == Plan.id)
        .where(
            Plan.id == subscription.plan_id,
            PlanVersion.plan_id == subscription.plan_id,
            PlanVersion.version == subscription.plan_version,
        )
        .limit(1)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "billing_plan_not_found"})
    return subscription, row[0], row[1]


@router.get("")
async def get_billing_summary(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    actor_id = _actor_id(current_user)
    await _require_workspace_member(session, workspace_id, actor_id)
    subscription, plan, version = await _subscription_context(session, workspace_id)
    usage = await UsageRepository(session).get_current_usage(
        subscription.id,
        subscription.current_period_start,
    )
    overage = await _current_overage_state(session, workspace_id, subscription)
    active_workspaces = await session.scalar(
        text(
            """
            SELECT count(*)
              FROM workspaces_workspaces
             WHERE owner_id = :user_id
               AND status != 'deleted'
            """
        ),
        {"user_id": str(actor_id)},
    )
    active_agents = await session.scalar(
        text(
            """
            SELECT count(*)
              FROM registry_agent_profiles
             WHERE workspace_id = :workspace_id
               AND status = 'published'
            """
        ),
        {"workspace_id": str(workspace_id)},
    )
    active_users = await session.scalar(
        text("SELECT count(*) FROM workspaces_memberships WHERE workspace_id = :workspace_id"),
        {"workspace_id": str(workspace_id)},
    )
    burn_rate = _burn_rate(
        Decimal(usage["minutes"]),
        subscription.current_period_start,
        subscription.current_period_end,
    )
    forecast_minutes = burn_rate * Decimal(
        max((subscription.current_period_end - datetime.now(UTC)).days, 0)
    ) + Decimal(usage["minutes"])
    estimated_overage = max(forecast_minutes - Decimal(version.minutes_per_month), Decimal("0"))
    return {
        "subscription": {
            "id": str(subscription.id),
            "scope_type": subscription.scope_type,
            "plan_slug": plan.slug,
            "plan_version": subscription.plan_version,
            "status": subscription.status,
            "current_period_start": subscription.current_period_start.isoformat(),
            "current_period_end": subscription.current_period_end.isoformat(),
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "trial_expires_at": None,
            "next_billing_eur": str(version.price_monthly),
        },
        "plan_caps": {
            "executions_per_day": version.executions_per_day,
            "executions_per_month": version.executions_per_month,
            "minutes_per_day": version.minutes_per_day,
            "minutes_per_month": version.minutes_per_month,
            "max_workspaces": version.max_workspaces,
            "max_agents_per_workspace": version.max_agents_per_workspace,
            "max_users_per_workspace": version.max_users_per_workspace,
            "overage_price_per_minute": str(version.overage_price_per_minute),
            "allowed_model_tier": plan.allowed_model_tier,
        },
        "usage": {
            "executions_today": int(usage["executions"]),
            "executions_this_period": int(usage["executions"]),
            "minutes_today": str(usage["minutes"]),
            "minutes_this_period": str(usage["minutes"]),
            "active_workspaces": int(active_workspaces or 0),
            "active_agents_in_this_workspace": int(active_agents or 0),
            "active_users_in_this_workspace": int(active_users or 0),
        },
        "forecast": {
            "executions_at_period_end": int(usage["executions"]),
            "minutes_at_period_end": str(forecast_minutes),
            "estimated_overage_eur": str(estimated_overage * version.overage_price_per_minute),
            "burn_rate_minutes_per_day": str(burn_rate),
        },
        "overage": overage,
        "payment_method": {"status": "stub", "last_four": None, "expires": None},
        "available_actions": _available_actions(plan.slug, subscription.status),
    }


@router.get("/overage-authorization")
async def get_overage_authorization(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_workspace_member(session, workspace_id, _actor_id(current_user))
    subscription, _, _ = await _subscription_context(session, workspace_id)
    return await _current_overage_state(session, workspace_id, subscription)


@router.post("/overage-authorization", status_code=201)
async def authorize_overage(
    workspace_id: UUID,
    payload: OverageAuthorizationCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    actor_id = _actor_id(current_user)
    await _require_workspace_admin(session, workspace_id, actor_id)
    service = OverageService(
        session=session,
        producer=_producer(request),
    )
    authorization = await service.authorize(
        workspace_id,
        None,
        payload.max_overage_eur,
        actor_id,
    )
    return _authorization_response(authorization, is_authorized=True)


@router.delete("/overage-authorization", status_code=204)
async def revoke_overage(
    workspace_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    actor_id = _actor_id(current_user)
    await _require_workspace_admin(session, workspace_id, actor_id)
    subscription, _, _ = await _subscription_context(session, workspace_id)
    authorization = await _current_authorization(session, workspace_id, subscription)
    if authorization is not None:
        await OverageService(session=session, producer=_producer(request)).revoke(
            authorization.id,
            actor_id,
        )
    return Response(status_code=204)


@router.get("/usage-history")
async def get_usage_history(
    workspace_id: UUID,
    periods: int = 12,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_workspace_member(session, workspace_id, _actor_id(current_user))
    subscription, _, _ = await _subscription_context(session, workspace_id)
    rows = await UsageRepository(session).get_period_history(subscription.id, limit=periods)
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


@router.post("/upgrade")
async def upgrade_subscription(
    workspace_id: UUID,
    payload: SubscriptionUpgrade,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    actor_id = _actor_id(current_user)
    await _require_workspace_admin(session, workspace_id, actor_id)
    provider = _payment_provider(request)
    subscription, _, _ = await _subscription_context(session, workspace_id)
    preview = await _preview_proration(session, provider, subscription, payload.target_plan_slug)
    service = _subscription_service(session, request, payment_provider=provider)
    updated = await service.upgrade(
        workspace_id,
        payload.target_plan_slug,
        payload.payment_method_token,
        actor_id=actor_id,
    )
    return {
        "preview": {
            "prorated_charge_eur": str(preview["prorated_charge_eur"]),
            "prorated_credit_eur": str(preview["prorated_credit_eur"]),
            "next_full_invoice_eur": str(preview["next_full_invoice_eur"]),
            "effective_at": preview["effective_at"].isoformat(),
        },
        "subscription_after": {
            "plan_slug": payload.target_plan_slug,
            "plan_version": updated.plan_version,
            "current_period_end": updated.current_period_end.isoformat(),
        },
    }


@router.post("/downgrade")
async def downgrade_subscription(
    workspace_id: UUID,
    payload: SubscriptionDowngrade,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    actor_id = _actor_id(current_user)
    await _require_workspace_admin(session, workspace_id, actor_id)
    updated = await _subscription_service(session, request).downgrade_at_period_end(
        workspace_id,
        payload.target_plan_slug,
    )
    return {
        "subscription_id": str(updated.id),
        "status": updated.status,
        "cancel_at_period_end": updated.cancel_at_period_end,
        "current_period_end": updated.current_period_end.isoformat(),
    }


@router.post("/cancel-downgrade")
async def cancel_downgrade(
    workspace_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    actor_id = _actor_id(current_user)
    await _require_workspace_admin(session, workspace_id, actor_id)
    updated = await _subscription_service(session, request).cancel_scheduled_downgrade(
        workspace_id,
    )
    return {
        "subscription_id": str(updated.id),
        "status": updated.status,
        "cancel_at_period_end": updated.cancel_at_period_end,
    }


@router.post("/cancel")
async def cancel_subscription(
    workspace_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    actor_id = _actor_id(current_user)
    await _require_workspace_admin(session, workspace_id, actor_id)
    subscription, _, _ = await _subscription_context(session, workspace_id)
    updated = await _subscription_service(session, request).cancel(subscription.id)
    return {
        "subscription_id": str(updated.id),
        "status": updated.status,
        "cancel_at_period_end": updated.cancel_at_period_end,
    }


def _subscription_service(
    session: AsyncSession,
    request: Request,
    *,
    payment_provider: PaymentProvider | None = None,
) -> SubscriptionService:
    producer = _producer(request)
    settings = cast(PlatformSettings, request.app.state.settings)
    return SubscriptionService(
        session=session,
        subscriptions=SubscriptionsRepository(session),
        plans=PlansRepository(session),
        payment_provider=payment_provider,
        audit_chain=build_audit_chain_service(session, settings, producer),
        producer=producer,
        quota_enforcer=build_quota_enforcer(
            session=session,
            settings=settings,
            redis_client=cast(AsyncRedisClient | None, request.app.state.clients.get("redis")),
        ),
    )


async def _preview_proration(
    session: AsyncSession,
    provider: PaymentProvider | None,
    subscription: Subscription,
    target_plan_slug: str,
) -> dict[str, Any]:
    plan = await PlansRepository(session).get_by_slug(target_plan_slug)
    if plan is None:
        now = datetime.now(UTC)
        return {
            "prorated_charge_eur": Decimal("0.00"),
            "prorated_credit_eur": Decimal("0.00"),
            "next_full_invoice_eur": Decimal("0.00"),
            "effective_at": now,
        }
    version = await PlansRepository(session).get_published_version(plan.id)
    if provider is None or version is None:
        now = datetime.now(UTC)
        return {
            "prorated_charge_eur": Decimal("0.00"),
            "prorated_credit_eur": Decimal("0.00"),
            "next_full_invoice_eur": Decimal("0.00"),
            "effective_at": now,
        }
    preview = await provider.preview_proration(
        subscription.stripe_subscription_id or f"stub_sub_{subscription.id.hex[:24]}",
        f"{plan.slug}:v{version.version}",
    )
    return {
        "prorated_charge_eur": preview.prorated_charge_eur,
        "prorated_credit_eur": preview.prorated_credit_eur,
        "next_full_invoice_eur": preview.next_full_invoice_eur,
        "effective_at": preview.effective_at,
    }


async def _current_overage_state(
    session: AsyncSession,
    workspace_id: UUID,
    subscription: Subscription,
) -> dict[str, Any]:
    authorization = await _current_authorization(session, workspace_id, subscription)
    service = OverageService(session=session)
    current_overage = await service.current_overage_eur(
        subscription.id,
        subscription.current_period_start,
    )
    return {
        "billing_period_start": subscription.current_period_start.isoformat(),
        "billing_period_end": subscription.current_period_end.isoformat(),
        "is_authorized": authorization is not None and authorization.revoked_at is None,
        "authorization_id": str(authorization.id) if authorization is not None else None,
        "authorization_required": authorization is None or authorization.revoked_at is not None,
        "current_overage_eur": str(current_overage),
        "max_overage_eur": (
            None
            if authorization is None or authorization.max_overage_eur is None
            else str(authorization.max_overage_eur)
        ),
        "authorized_by": (
            str(authorization.authorized_by_user_id) if authorization is not None else None
        ),
        "authorized_at": (
            authorization.authorized_at.isoformat() if authorization is not None else None
        ),
        "forecast_total_overage_eur": str(current_overage),
    }


async def _current_authorization(
    session: AsyncSession,
    workspace_id: UUID,
    subscription: Subscription,
) -> OverageAuthorization | None:
    result = await session.execute(
        select(OverageAuthorization)
        .where(
            OverageAuthorization.workspace_id == workspace_id,
            OverageAuthorization.subscription_id == subscription.id,
            OverageAuthorization.billing_period_start == subscription.current_period_start,
        )
        .order_by(OverageAuthorization.authorized_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _authorization_response(
    authorization: OverageAuthorization,
    *,
    is_authorized: bool,
) -> dict[str, Any]:
    return {
        "id": str(authorization.id),
        "billing_period_start": authorization.billing_period_start.isoformat(),
        "billing_period_end": authorization.billing_period_end.isoformat(),
        "is_authorized": is_authorized,
        "max_overage_eur": (
            None
            if authorization.max_overage_eur is None
            else str(authorization.max_overage_eur)
        ),
        "authorized_by": str(authorization.authorized_by_user_id),
        "authorized_at": authorization.authorized_at.isoformat(),
    }


def _burn_rate(
    minutes: Decimal,
    period_start: datetime,
    period_end: datetime,
) -> Decimal:
    del period_end
    elapsed_days = max((datetime.now(UTC) - period_start).days, 1)
    return minutes / Decimal(elapsed_days)


def _available_actions(plan_slug: str, status: str) -> list[str]:
    if status == "cancellation_pending":
        return ["cancel_downgrade"]
    if plan_slug == "free":
        return ["upgrade_to_pro"]
    if plan_slug == "pro":
        return ["downgrade_to_free", "upgrade_to_enterprise"]
    return []
