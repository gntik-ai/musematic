"""Admin marketplace-review router (UPD-049).

Mounts under the existing `/api/v1/admin/*` composite router. Endpoints
defined here serve the platform-staff review queue per
`specs/099-marketplace-scope/contracts/admin-marketplace-review-rest.md`:

- ``GET /api/v1/admin/marketplace-review/queue`` — list pending submissions
  cross-tenant via the platform-staff session (UPD-046 BYPASSRLS pool).
- ``POST /api/v1/admin/marketplace-review/{agent_id}/claim`` — optimistic
  conditional claim per research R6.
- ``POST /api/v1/admin/marketplace-review/{agent_id}/release`` — release a
  prior claim.
- ``POST /api/v1/admin/marketplace-review/{agent_id}/approve`` — approve and
  transition the agent to ``review_status='published'``.
- ``POST /api/v1/admin/marketplace-review/{agent_id}/reject`` — reject with a
  required reason; notification delivered to the submitter via UPD-042.
"""

from __future__ import annotations

from platform.admin.rbac import require_superadmin
from platform.common import database
from platform.common.events.producer import EventProducer
from platform.marketplace.notifications import MarketplaceNotificationService
from platform.marketplace.review_service import MarketplaceAdminService
from platform.notifications.service import AlertService
from platform.registry.schemas import (
    ReviewApprovalRequest,
    ReviewQueueResponse,
    ReviewRejectionRequest,
)
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(prefix="/marketplace-review", tags=["admin.marketplace_review"])


def _event_producer(request: Request) -> EventProducer | None:
    return getattr(request.app.state, "event_producer", None)


def _alert_service(request: Request) -> AlertService | None:
    return getattr(request.app.state, "alert_service", None)


@router.get("/queue", response_model=ReviewQueueResponse)
async def list_review_queue(
    request: Request,
    claimed_by: str | None = Query(default=None, description="Filter by reviewer user id."),
    unclaimed: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> ReviewQueueResponse:
    """List ``pending_review`` submissions cross-tenant.

    Cursor pagination: pass the response's ``next_cursor`` back as
    ``cursor`` for the next page; ``None`` means no more pages.
    """
    async with database.PlatformStaffAsyncSessionLocal() as session:
        alert_service = _alert_service(request)
        notifications = (
            MarketplaceNotificationService(alert_service) if alert_service is not None else None
        )
        service = MarketplaceAdminService(
            platform_staff_session=session,
            event_producer=_event_producer(request),
            notifications=notifications,
        )
        return await service.list_queue(
            claimed_by=UUID(claimed_by) if claimed_by else None,
            unclaimed_only=unclaimed,
            limit=limit,
            cursor=cursor,
        )


@router.post("/{agent_id}/claim")
async def claim_submission(
    agent_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, str]:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        service = _build_admin_service(request, session)
        await service.claim(agent_id, _actor_id(current_user))
    return {"status": "claimed"}


@router.post("/{agent_id}/release")
async def release_submission(
    agent_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, str]:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        service = _build_admin_service(request, session)
        await service.release(agent_id, _actor_id(current_user))
    return {"status": "released"}


@router.post("/{agent_id}/approve")
async def approve_submission(
    agent_id: UUID,
    payload: ReviewApprovalRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, str]:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        service = _build_admin_service(request, session)
        await service.approve(agent_id, _actor_id(current_user), payload.notes)
    return {"status": "approved"}


@router.post("/{agent_id}/reject")
async def reject_submission(
    agent_id: UUID,
    payload: ReviewRejectionRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, str]:
    async with database.PlatformStaffAsyncSessionLocal() as session:
        service = _build_admin_service(request, session)
        await service.reject(agent_id, _actor_id(current_user), payload.reason)
    return {"status": "rejected"}


def _build_admin_service(
    request: Request, session: Any
) -> MarketplaceAdminService:
    alert_service = _alert_service(request)
    notifications = (
        MarketplaceNotificationService(alert_service) if alert_service is not None else None
    )
    return MarketplaceAdminService(
        platform_staff_session=session,
        event_producer=_event_producer(request),
        notifications=notifications,
    )


def _actor_id(current_user: dict[str, Any]) -> UUID:
    raw = current_user.get("user_id") or current_user.get("id")
    if raw is None:
        raise RuntimeError("require_superadmin returned a user without an id")
    return UUID(str(raw))
