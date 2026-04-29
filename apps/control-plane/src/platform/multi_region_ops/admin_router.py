from __future__ import annotations

from platform.admin.rbac import require_admin, require_superadmin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted, empty_list
from platform.admin.two_person_auth_service import TwoPersonAuthService
from platform.common.dependencies import get_db
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["admin", "multi-region-ops"])


@router.get("/regions", response_model=AdminListResponse)
async def list_regions(
    current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminListResponse:
    return empty_list("regions", current_user)


@router.get("/regions/replication-lag", response_model=AdminListResponse)
async def list_replication_lag(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("replication-lag", current_user)


@router.post("/regions/failover/execute", response_model=AdminActionResponse)
async def execute_failover(
    request: Request,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
    two_person_auth_token: str | None = Header(default=None, alias="X-Two-Person-Auth-Token"),
) -> AdminActionResponse:
    if not two_person_auth_token:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "two_person_auth_required",
                "message": "2PA token required for failover execution",
                "suggested_action": "Request and approve a 2PA failover action first.",
            },
        )
    service = TwoPersonAuthService(session, request.app.state.settings)
    valid = await service.validate_token(
        two_person_auth_token,
        action="multi_region_ops.failover.execute",
    )
    if not valid:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "two_person_auth_invalid",
                "message": "2PA request expired or invalid",
                "suggested_action": "Create a fresh 2PA request before retrying failover.",
            },
        )
    return accepted("execute_failover", "regions", affected_count=1)


@router.post("/regions/failback", response_model=AdminActionResponse)
async def initiate_failback(
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("failback", "regions", affected_count=1)


@router.get("/maintenance", response_model=AdminListResponse)
async def list_maintenance_windows(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("maintenance-windows", current_user)


@router.post("/maintenance", response_model=AdminActionResponse)
async def create_maintenance_window(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "maintenance-windows", affected_count=1)
