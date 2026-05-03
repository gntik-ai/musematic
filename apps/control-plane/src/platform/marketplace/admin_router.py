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
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.marketplace.notifications import MarketplaceNotificationService
from platform.marketplace.parity_probe import MarketplaceParityProbe
from platform.marketplace.review_service import MarketplaceAdminService
from platform.notifications.service import AlertService
from platform.registry.schemas import (
    AssignReviewerRequest,
    ReviewApprovalRequest,
    ReviewerAssignmentResponse,
    ReviewerUnassignmentResponse,
    ReviewQueueResponse,
    ReviewRejectionRequest,
)
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

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
    assigned_to: str | None = Query(
        default=None,
        description=(
            "UPD-049 refresh — filter by assigned reviewer. Special values: "
            "'me' resolves to caller's user_id; 'unassigned' filters "
            "assigned_reviewer_user_id IS NULL."
        ),
    ),
    include_self_authored: bool = Query(
        default=False,
        description=(
            "When false (default) submissions where caller is the submitter "
            "are excluded so reviewers cannot accidentally action their own work."
        ),
    ),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> ReviewQueueResponse:
    """List ``pending_review`` submissions cross-tenant.

    Cursor pagination: pass the response's ``next_cursor`` back as
    ``cursor`` for the next page; ``None`` means no more pages.
    """
    actor_id = _actor_id(current_user)
    # UPD-049 refresh — resolve the special 'me'/'unassigned' values for
    # assigned_to BEFORE we hit the service layer. Mutually exclusive
    # with each other (the unassigned_only path takes priority).
    unassigned_only = False
    assigned_filter: UUID | None = None
    if assigned_to == "unassigned":
        unassigned_only = True
    elif assigned_to == "me":
        assigned_filter = actor_id
    elif assigned_to:
        assigned_filter = UUID(assigned_to)
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
            assigned_to=assigned_filter,
            unassigned_only=unassigned_only,
            include_self_authored=include_self_authored,
            current_user_id=actor_id,
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


# UPD-049 refresh (102) — reviewer assignment endpoints. Per
# `contracts/reviewer-assignment-rest.md`. Both gated by
# `require_superadmin`. Self-review prevention is enforced server-side
# in `MarketplaceAdminService.assign` (FR-741.9 / R9).


@router.post(
    "/{agent_id}/assign",
    response_model=ReviewerAssignmentResponse,
)
async def assign_reviewer(
    agent_id: UUID,
    payload: AssignReviewerRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> ReviewerAssignmentResponse:
    """Assign a pending-review submission to a specific reviewer."""
    async with database.PlatformStaffAsyncSessionLocal() as session:
        service = _build_admin_service(request, session)
        result = await service.assign(
            agent_id,
            payload.reviewer_user_id,
            _actor_id(current_user),
        )
    return ReviewerAssignmentResponse(**result)


@router.delete(
    "/{agent_id}/assign",
    response_model=ReviewerUnassignmentResponse,
)
async def unassign_reviewer(
    agent_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> ReviewerUnassignmentResponse:
    """Clear the assignment of a pending-review submission. Idempotent."""
    async with database.PlatformStaffAsyncSessionLocal() as session:
        service = _build_admin_service(request, session)
        result = await service.unassign(agent_id, _actor_id(current_user))
    return ReviewerUnassignmentResponse(**result)


# UPD-049 refresh (102) T045 — non-leakage parity probe (DEV-ONLY).
# Per `contracts/non-leakage-parity-probe-rest.md`: returns 404 in
# production (FEATURE_E2E_MODE != true) so the endpoint is invisible
# to non-dev clients per constitutional rule 26.

DEFAULT_TENANT_UUID = UUID("00000000-0000-0000-0000-000000000001")


@router.get("/parity-probe")
async def parity_probe(
    request: Request,
    query: str = Query(..., min_length=1, max_length=256),
    subject_tenant_id: UUID = Query(...),
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> dict[str, Any]:
    """SC-004 verification harness — see contract for full behaviour.

    The probe runs the same search twice (counterfactual + with a
    synthetic public agent matching the query inserted under a
    SAVEPOINT that is rolled back before the response returns) and
    compares the result/count/suggestions/analytics-event payload
    byte-for-byte. ``parity_violation=true`` means the visibility
    filter let synthetic public-hub data leak.
    """
    settings = cast(PlatformSettings, request.app.state.settings)
    if not getattr(settings, "feature_e2e_mode", False):
        # Per constitutional rule 26 — 404, not 403, so the endpoint
        # is completely invisible in production. No body.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if subject_tenant_id == DEFAULT_TENANT_UUID:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "tenant_not_eligible",
                "message": (
                    "Parity probe is meaningful only for non-default "
                    "tenants — public visibility is always on for the "
                    "default tenant."
                ),
            },
        )
    probe = MarketplaceParityProbe(settings=settings)
    result = await probe.run(
        query=query,
        subject_tenant_id=subject_tenant_id,
        actor_user_id=_actor_id(current_user),
    )
    return {
        "query": result.query,
        "subject_tenant_id": str(result.subject_tenant_id),
        "counterfactual": result.counterfactual,
        "live": result.live,
        "parity_violation": result.parity_violation,
        "parity_violations": result.parity_violations,
    }


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
