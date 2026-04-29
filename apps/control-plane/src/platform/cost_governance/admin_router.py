from __future__ import annotations

from platform.admin.rbac import require_admin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted, empty_list
from typing import Any

from fastapi import APIRouter, Depends

router = APIRouter(tags=["admin", "cost-governance"])


@router.get("/costs/overview", response_model=AdminListResponse)
async def get_cost_overview(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("cost-overview", current_user)


@router.get("/costs/budgets", response_model=AdminListResponse)
async def list_budgets(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("budgets", current_user)


@router.post("/costs/budgets", response_model=AdminActionResponse)
async def create_budget(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "budgets", affected_count=1)


@router.get("/costs/chargeback", response_model=AdminListResponse)
async def list_chargeback_reports(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("chargeback-reports", current_user)


@router.post("/costs/chargeback/export", response_model=AdminActionResponse)
async def export_chargeback_report(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("export", "chargeback-reports", affected_count=1)


@router.get("/costs/anomalies", response_model=AdminListResponse)
async def list_cost_anomalies(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("cost-anomalies", current_user)


@router.post("/costs/anomalies/{anomaly_id}/acknowledge", response_model=AdminActionResponse)
async def acknowledge_cost_anomaly(
    anomaly_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("acknowledge", f"cost-anomalies/{anomaly_id}", affected_count=1)


@router.get("/costs/forecasts", response_model=AdminListResponse)
async def list_cost_forecasts(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("cost-forecasts", current_user)


@router.get("/costs/rates", response_model=AdminListResponse)
async def list_cost_rates(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("cost-rates", current_user)


@router.put("/costs/rates/{rate_id}", response_model=AdminActionResponse)
async def update_cost_rate(
    rate_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("update", f"cost-rates/{rate_id}", affected_count=1)
