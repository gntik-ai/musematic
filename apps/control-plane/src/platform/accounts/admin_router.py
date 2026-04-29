from __future__ import annotations

from platform.admin.rbac import require_admin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted, empty_list
from typing import Any

from fastapi import APIRouter, Depends

router = APIRouter(tags=["admin", "accounts"])


@router.get("/api-keys/service-accounts", response_model=AdminListResponse)
async def list_service_account_api_keys(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("service-account-api-keys", current_user)


@router.post("/api-keys/service-accounts/{api_key_id}/rotate", response_model=AdminActionResponse)
async def rotate_service_account_api_key(
    api_key_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("rotate", f"service-account-api-keys/{api_key_id}", affected_count=1)


@router.delete("/api-keys/service-accounts/{api_key_id}", response_model=AdminActionResponse)
async def revoke_service_account_api_key(
    api_key_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("revoke", f"service-account-api-keys/{api_key_id}", affected_count=1)
