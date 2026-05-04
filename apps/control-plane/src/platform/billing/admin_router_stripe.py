"""UPD-052 — Enterprise tenant billing admin endpoints (super-admin only)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from platform.billing.payment_failure_grace.repository import (
    PaymentFailureGraceRepository,
)
from platform.billing.payment_failure_grace.service import (
    PaymentFailureGraceService,
)
from platform.billing.subscriptions.models import Subscription
from platform.common.dependencies import get_current_user
from platform.common.events.envelope import CorrelationContext
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)

admin_billing_router = APIRouter(
    prefix="/api/v1/admin/tenants/{tenant_id}/billing",
    tags=["billing:admin"],
)


async def _get_session(request: Request) -> AsyncIterator[AsyncSession]:
    from platform.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def _require_platform_admin(current_user: dict[str, Any]) -> None:
    roles = {
        str(item.get("role")) for item in current_user.get("roles", []) if isinstance(item, dict)
    }
    if "platform_admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="platform_admin_required",
        )


class ManualResolveRequest(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


@admin_billing_router.post("/grace/{grace_id}/resolve")
async def manually_resolve_grace(
    tenant_id: UUID,
    grace_id: UUID,
    payload: ManualResolveRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    _require_platform_admin(current_user)
    del payload, request, tenant_id
    service = PaymentFailureGraceService(
        repository=PaymentFailureGraceRepository(session),
        producer=None,
    )
    correlation = CorrelationContext(correlation_id=uuid4())
    resolved = await service.resolve_manually(
        grace_id=grace_id,
        correlation_ctx=correlation,
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="grace_not_found",
        )
    await session.commit()
    return {
        "grace_id": str(resolved.id),
        "resolved_at": resolved.resolved_at.isoformat() if resolved.resolved_at else None,
        "resolution": resolved.resolution,
    }


@admin_billing_router.get("")
async def get_tenant_billing(
    tenant_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    _require_platform_admin(current_user)
    stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
    sub = (await session.execute(stmt)).scalars().first()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant_billing_not_found",
        )
    return {
        "tenant_id": str(tenant_id),
        "stripe_customer_id": sub.stripe_customer_id,
        "subscription": {
            "id": str(sub.id),
            "stripe_subscription_id": sub.stripe_subscription_id,
            "status": sub.status,
            "plan_id": str(sub.plan_id),
            "plan_version": sub.plan_version,
            "current_period_start": (
                sub.current_period_start.isoformat() if sub.current_period_start else None
            ),
            "current_period_end": (
                sub.current_period_end.isoformat() if sub.current_period_end else None
            ),
            "cancel_at_period_end": getattr(sub, "cancel_at_period_end", False),
        },
    }
