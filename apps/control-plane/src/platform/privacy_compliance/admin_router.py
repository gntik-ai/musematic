from __future__ import annotations

from platform.admin.rbac import require_admin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted, empty_list
from typing import Any

from fastapi import APIRouter, Depends, Query

router = APIRouter(tags=["admin", "privacy-compliance"])


@router.get("/privacy/dsr", response_model=AdminListResponse)
async def list_dsr_requests(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("dsr-requests", current_user)


@router.post("/privacy/dsr/{request_id}/approve", response_model=AdminActionResponse)
async def approve_dsr_request(
    request_id: str,
    preview: bool = Query(default=False),
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("approve", f"dsr-requests/{request_id}", preview=preview, affected_count=1)


@router.post("/privacy/dsr/{request_id}/deny", response_model=AdminActionResponse)
async def deny_dsr_request(
    request_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("deny", f"dsr-requests/{request_id}", affected_count=1)


@router.get("/privacy/dlp", response_model=AdminListResponse)
async def list_dlp_rules(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("dlp-rules", current_user)


@router.post("/privacy/dlp", response_model=AdminActionResponse)
async def create_dlp_rule(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "dlp-rules", affected_count=1)


@router.get("/privacy/pia", response_model=AdminListResponse)
async def list_pia_reviews(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("pia-reviews", current_user)


@router.post("/privacy/pia/{review_id}/approve", response_model=AdminActionResponse)
async def approve_pia_review(
    review_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("approve", f"pia-reviews/{review_id}", affected_count=1)


@router.get("/privacy/consent", response_model=AdminListResponse)
async def list_consent_records(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("consent-records", current_user)


@router.post("/privacy/consent/{record_id}/revoke", response_model=AdminActionResponse)
async def revoke_consent_record(
    record_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("revoke", f"consent-records/{record_id}", affected_count=1)
