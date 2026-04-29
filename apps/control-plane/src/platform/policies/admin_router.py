from __future__ import annotations

from platform.admin.rbac import require_admin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted, empty_list
from typing import Any

from fastapi import APIRouter, Depends, Query

router = APIRouter(tags=["admin", "policies"])


@router.get("/policies", response_model=AdminListResponse)
async def list_policies(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("policies", current_user)


@router.post("/policies", response_model=AdminActionResponse)
async def create_policy(
    preview: bool = Query(default=False),
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "policies", preview=preview, affected_count=1)


@router.put("/policies/{policy_id}", response_model=AdminActionResponse)
async def update_policy(
    policy_id: str,
    preview: bool = Query(default=False),
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("update", f"policies/{policy_id}", preview=preview, affected_count=1)


@router.post("/policies/{policy_id}/attach", response_model=AdminActionResponse)
async def attach_policy(
    policy_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("attach", f"policies/{policy_id}", affected_count=1)


@router.post("/policies/{policy_id}/preview", response_model=AdminActionResponse)
async def preview_policy(
    policy_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("preview", f"policies/{policy_id}", preview=True)
