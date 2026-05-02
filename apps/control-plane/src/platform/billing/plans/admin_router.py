from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.admin.rbac import require_superadmin
from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.billing.exceptions import PlanNotFoundError
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.plans.repository import PlansRepository
from platform.billing.plans.schemas import PlanCreate, PlanUpdate, PlanVersionPublish
from platform.billing.plans.service import PlansService
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.common.tenant_context import current_tenant
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1/admin/plans",
    tags=["admin", "billing", "plans"],
    dependencies=[Depends(require_superadmin)],
)


@router.get("")
async def list_plans(
    tier: str | None = None,
    is_active: bool | None = None,
    is_public: bool | None = None,
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    repository = PlansRepository(session)
    plans = await repository.list_filtered(tier=tier, is_active=is_active, is_public=is_public)
    return {"items": [await _admin_list_item(repository, plan) for plan in plans]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanCreate,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repository = PlansRepository(session)
    try:
        plan = await repository.create_plan(**payload.model_dump())
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "plan_slug_taken",
                "message": "A billing plan already exists for this slug",
                "details": {"slug": payload.slug},
            },
        ) from exc
    return await _admin_detail(repository, plan)


@router.get("/{slug}")
async def get_plan(
    slug: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repository = PlansRepository(session)
    plan = await repository.get_by_slug(slug)
    if plan is None:
        raise PlanNotFoundError(slug)
    return await _admin_detail(repository, plan)


@router.get("/{slug}/versions")
async def list_plan_versions(
    slug: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    repository = PlansRepository(session)
    service = PlansService(repository)
    plan = await repository.get_by_slug(slug)
    if plan is None:
        raise PlanNotFoundError(slug)
    versions = await repository.list_versions(plan.id)
    lower_version_by_version = {
        current.version: prior
        for prior, current in zip(reversed(versions), list(reversed(versions))[1:], strict=False)
    }
    items: list[dict[str, Any]] = []
    for version in versions:
        prior = lower_version_by_version.get(version.version)
        item = _version_payload(version)
        item["subscription_count"] = await repository.count_subscriptions_on_version(
            plan.id,
            version.version,
        )
        item["diff_against_prior"] = service.compute_diff_against_prior(prior, version)
        items.append(item)
    return {"items": items}


@router.post("/{slug}/versions", status_code=status.HTTP_201_CREATED)
async def publish_plan_version(
    slug: str,
    payload: PlanVersionPublish,
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    repository = PlansRepository(session)
    service = PlansService(
        repository,
        audit_chain=_audit_chain_service(request, session),
        producer=_event_producer(request),
    )
    actor_id = _principal_id(current_user)
    new_version = await service.publish_new_version(
        slug,
        payload,
        actor_id=actor_id,
        tenant_id=_tenant_id(),
    )
    versions = await repository.list_versions(new_version.plan_id)
    prior = next(
        (version for version in versions if version.version == new_version.version - 1),
        None,
    )
    return {
        "id": str(new_version.id),
        "version": new_version.version,
        "published_at": _iso(new_version.published_at),
        "diff_against_prior": service.compute_diff_against_prior(prior, new_version),
    }


@router.post("/{slug}/versions/{version}/deprecate")
async def deprecate_plan_version(
    slug: str,
    version: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repository = PlansRepository(session)
    service = PlansService(
        repository,
        audit_chain=_audit_chain_service(request, session),
        producer=_event_producer(request),
    )
    plan = await repository.get_by_slug(slug)
    if plan is None:
        raise PlanNotFoundError(slug)
    stored = await service.deprecate_version(plan.id, version, tenant_id=_tenant_id())
    if stored is None:
        raise PlanNotFoundError(f"{slug}@{version}")
    payload = _version_payload(stored)
    payload["subscription_count"] = await repository.count_subscriptions_on_version(
        plan.id,
        version,
    )
    return payload


@router.patch("/{slug}")
async def update_plan_metadata(
    slug: str,
    payload: PlanUpdate,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repository = PlansRepository(session)
    service = PlansService(repository)
    plan = await service.update_plan_metadata(slug, payload)
    return await _admin_detail(repository, plan)


async def _admin_list_item(repository: PlansRepository, plan: Plan) -> dict[str, Any]:
    current = await repository.get_published_version(plan.id)
    return {
        "id": str(plan.id),
        "slug": plan.slug,
        "display_name": plan.display_name,
        "tier": plan.tier,
        "is_public": plan.is_public,
        "is_active": plan.is_active,
        "allowed_model_tier": plan.allowed_model_tier,
        "current_published_version": current.version if current is not None else None,
        "active_subscription_count": await repository.count_subscriptions_for_plan(plan.id),
        "created_at": _iso(plan.created_at),
    }


async def _admin_detail(repository: PlansRepository, plan: Plan) -> dict[str, Any]:
    versions = await repository.list_versions(plan.id)
    current = await repository.get_published_version(plan.id)
    payload = await _admin_list_item(repository, plan)
    payload.update(
        {
            "description": plan.description,
            "current_version": _version_payload(current) if current is not None else None,
            "version_count": len(versions),
        }
    )
    return payload


def _version_payload(version: PlanVersion) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "plan_id": str(version.plan_id),
        "version": version.version,
        "price_monthly": _decimal(version.price_monthly),
        "executions_per_day": version.executions_per_day,
        "executions_per_month": version.executions_per_month,
        "minutes_per_day": version.minutes_per_day,
        "minutes_per_month": version.minutes_per_month,
        "max_workspaces": version.max_workspaces,
        "max_agents_per_workspace": version.max_agents_per_workspace,
        "max_users_per_workspace": version.max_users_per_workspace,
        "overage_price_per_minute": _decimal(version.overage_price_per_minute),
        "trial_days": version.trial_days,
        "quota_period_anchor": version.quota_period_anchor,
        "extras": version.extras_json,
        "published_at": _iso(version.published_at),
        "deprecated_at": _iso(version.deprecated_at),
        "created_at": _iso(version.created_at),
        "created_by": str(version.created_by) if version.created_by is not None else None,
    }


def _audit_chain_service(request: Request, session: AsyncSession) -> AuditChainService:
    return AuditChainService(
        AuditChainRepository(session),
        _settings(request),
        producer=_event_producer(request),
    )


def _event_producer(request: Request) -> EventProducer | None:
    clients = getattr(request.app.state, "clients", {})
    producer = clients.get("kafka") if isinstance(clients, dict) else None
    return cast(EventProducer | None, producer)


def _settings(request: Request) -> PlatformSettings:
    return getattr(request.app.state, "settings", default_settings)


def _tenant_id() -> UUID | None:
    tenant = current_tenant.get(None)
    return tenant.id if tenant is not None else None


def _principal_id(current_user: dict[str, Any]) -> UUID | None:
    value = current_user.get("principal_id") or current_user.get("sub")
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
