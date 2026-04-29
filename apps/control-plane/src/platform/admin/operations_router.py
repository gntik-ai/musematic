from __future__ import annotations

from platform.admin.rbac import require_admin
from platform.admin.responses import AdminListResponse, empty_list
from typing import Any

from fastapi import APIRouter, Depends

router = APIRouter(tags=["admin", "operations"])


@router.get("/queues", response_model=AdminListResponse)
async def list_queues(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("queues", current_user)


@router.get("/warm-pool", response_model=AdminListResponse)
async def list_warm_pool(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("warm-pool", current_user)


@router.get("/executions", response_model=AdminListResponse)
async def list_executions(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("executions", current_user)


@router.get("/observability/dashboards", response_model=AdminListResponse)
async def list_observability_dashboards(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("observability-dashboards", current_user)


@router.get("/observability/alerts", response_model=AdminListResponse)
async def list_observability_alerts(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("observability-alerts", current_user)


@router.get("/observability/log-retention", response_model=AdminListResponse)
async def get_log_retention(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("log-retention", current_user)


@router.get("/observability/registry", response_model=AdminListResponse)
async def list_observability_registry(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("observability-registry", current_user)
