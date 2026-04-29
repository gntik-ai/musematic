from __future__ import annotations

from platform.admin.rbac import require_admin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted, empty_list
from typing import Any

from fastapi import APIRouter, Depends

router = APIRouter(tags=["admin", "connectors"])


@router.get("/connectors", response_model=AdminListResponse)
async def list_connectors(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("connectors", current_user)


@router.post("/connectors/{connector_id}/enable", response_model=AdminActionResponse)
async def enable_connector(
    connector_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("enable", f"connectors/{connector_id}", affected_count=1)


@router.post("/connectors/{connector_id}/disable", response_model=AdminActionResponse)
async def disable_connector(
    connector_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("disable", f"connectors/{connector_id}", affected_count=1)


@router.post("/connectors/{connector_id}/rotate-credentials", response_model=AdminActionResponse)
async def rotate_connector_credentials(
    connector_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("rotate_credentials", f"connectors/{connector_id}", affected_count=1)


@router.post("/connectors/{connector_id}/test", response_model=AdminActionResponse)
async def check_connector_connectivity(
    connector_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("test", f"connectors/{connector_id}", affected_count=1)
