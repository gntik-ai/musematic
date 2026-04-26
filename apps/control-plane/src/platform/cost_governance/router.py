from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import NotFoundError
from platform.cost_governance.dependencies import (
    get_anomaly_service,
    get_budget_service,
    get_chargeback_service,
    get_cost_attribution_service,
    get_forecast_service,
)
from platform.cost_governance.schemas import (
    AnomalyAcknowledgeRequest,
    AnomalyState,
    BudgetAlertResponse,
    BudgetPeriodType,
    ChargebackExportRequest,
    ChargebackReportRequest,
    ChargebackReportResponse,
    CostAnomalyResponse,
    CostAttributionRecord,
    CostForecastResponse,
    OverrideIssueRequest,
    OverrideIssueResponse,
    WorkspaceBudgetCreateRequest,
    WorkspaceBudgetResponse,
)
from platform.cost_governance.services.anomaly_service import AnomalyService
from platform.cost_governance.services.attribution_service import AttributionService
from platform.cost_governance.services.budget_service import BudgetService
from platform.cost_governance.services.chargeback_service import ChargebackService
from platform.cost_governance.services.forecast_service import ForecastService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.models import WorkspaceRole
from platform.workspaces.service import WorkspacesService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

router = APIRouter(prefix="/api/v1/costs")


def _requester_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


async def _require_member(
    workspaces_service: WorkspacesService,
    workspace_id: UUID,
    user_id: UUID,
) -> None:
    await workspaces_service.get_workspace(workspace_id, user_id)


async def _require_admin(
    workspaces_service: WorkspacesService,
    workspace_id: UUID,
    user_id: UUID,
) -> None:
    await workspaces_service._require_membership(workspace_id, user_id, WorkspaceRole.admin)


@router.get(
    "/executions/{execution_id}",
    tags=["cost-governance-attributions"],
)
async def get_execution_cost(
    execution_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    attribution_service: AttributionService = Depends(get_cost_attribution_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> dict[str, Any]:
    result = await attribution_service.get_execution_cost(execution_id)
    if result is None:
        raise NotFoundError("COST_ATTRIBUTION_NOT_FOUND", "Cost attribution not found")
    attribution = result["attribution"]
    await _require_member(workspaces_service, attribution.workspace_id, _requester_id(current_user))
    return {
        "attribution": CostAttributionRecord.model_validate(attribution),
        "corrections": [
            CostAttributionRecord.model_validate(row) for row in result["corrections"]
        ],
        "totals": result["totals"],
    }


@router.get(
    "/workspaces/{workspace_id}/attributions",
    tags=["cost-governance-attributions"],
)
async def list_workspace_attributions(
    workspace_id: UUID,
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    cursor: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    agent_id: UUID | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    group_by: list[str] | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    attribution_service: AttributionService = Depends(get_cost_attribution_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> dict[str, Any]:
    await _require_member(workspaces_service, workspace_id, _requester_id(current_user))
    if group_by:
        start = since or datetime.min.replace(tzinfo=UTC)
        end = until or datetime.max.replace(tzinfo=UTC)
        rows = await attribution_service.repository.aggregate_attributions(
            workspace_id,
            group_by,
            start,
            end,
        )
        return {"items": rows, "group_by": group_by}
    raw_rows = await attribution_service.repository.get_workspace_attributions(
        workspace_id,
        since,
        until,
        cursor,
        limit,
        agent_id=agent_id,
        user_id=user_id,
    )
    return {"items": [CostAttributionRecord.model_validate(row) for row in raw_rows]}


@router.post(
    "/workspaces/{workspace_id}/budgets",
    response_model=WorkspaceBudgetResponse,
    tags=["cost-governance-budgets"],
)
async def configure_budget(
    workspace_id: UUID,
    request: WorkspaceBudgetCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> WorkspaceBudgetResponse:
    requester = _requester_id(current_user)
    await _require_admin(workspaces_service, workspace_id, requester)
    budget = await budget_service.configure(
        workspace_id=workspace_id,
        period_type=request.period_type.value,
        budget_cents=request.budget_cents,
        soft_alert_thresholds=request.soft_alert_thresholds,
        hard_cap_enabled=request.hard_cap_enabled,
        admin_override_enabled=request.admin_override_enabled,
        actor_id=requester,
        currency=request.currency,
    )
    return WorkspaceBudgetResponse.model_validate(budget)


@router.get(
    "/workspaces/{workspace_id}/budgets",
    response_model=list[WorkspaceBudgetResponse],
    tags=["cost-governance-budgets"],
)
async def list_budgets(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> list[WorkspaceBudgetResponse]:
    await _require_member(workspaces_service, workspace_id, _requester_id(current_user))
    rows = await budget_service.repository.list_budgets(workspace_id)
    return [WorkspaceBudgetResponse.model_validate(row) for row in rows]


@router.delete(
    "/workspaces/{workspace_id}/budgets/{period_type}",
    status_code=204,
    tags=["cost-governance-budgets"],
)
async def delete_budget(
    workspace_id: UUID,
    period_type: BudgetPeriodType,
    current_user: dict[str, Any] = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> Response:
    await _require_admin(workspaces_service, workspace_id, _requester_id(current_user))
    budget = await budget_service.repository.get_active_budget(workspace_id, period_type.value)
    if budget is None:
        raise NotFoundError("BUDGET_NOT_CONFIGURED", "Workspace budget not configured")
    await budget_service.repository.delete_budget(budget.id)
    return Response(status_code=204)


@router.get(
    "/workspaces/{workspace_id}/alerts",
    response_model=list[BudgetAlertResponse],
    tags=["cost-governance-budgets"],
)
async def list_budget_alerts(
    workspace_id: UUID,
    cursor: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> list[BudgetAlertResponse]:
    await _require_member(workspaces_service, workspace_id, _requester_id(current_user))
    rows = await budget_service.repository.list_alerts(workspace_id, cursor=cursor, limit=limit)
    return [BudgetAlertResponse.model_validate(row) for row in rows]


@router.post(
    "/workspaces/{workspace_id}/budget/override",
    response_model=OverrideIssueResponse,
    tags=["cost-governance-budgets"],
)
async def issue_budget_override(
    workspace_id: UUID,
    request: OverrideIssueRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    budget_service: BudgetService = Depends(get_budget_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> OverrideIssueResponse:
    requester = _requester_id(current_user)
    await _require_admin(workspaces_service, workspace_id, requester)
    return await budget_service.issue_override(workspace_id, requester, request.reason)


@router.post(
    "/reports/chargeback",
    response_model=ChargebackReportResponse,
    tags=["cost-governance-reports"],
)
async def generate_chargeback_report(
    request: ChargebackReportRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    chargeback_service: ChargebackService = Depends(get_chargeback_service),
) -> ChargebackReportResponse:
    return await chargeback_service.generate_report(
        requester=_requester_id(current_user),
        dimensions=request.dimensions,
        group_by=request.group_by,
        since=request.since,
        until=request.until,
        workspace_filter=request.workspace_filter,
    )


@router.post(
    "/reports/chargeback/export",
    tags=["cost-governance-reports"],
)
async def export_chargeback_report(
    request: ChargebackExportRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    chargeback_service: ChargebackService = Depends(get_chargeback_service),
) -> Response:
    report = await chargeback_service.generate_report(
        requester=_requester_id(current_user),
        dimensions=request.dimensions,
        group_by=request.group_by,
        since=request.since,
        until=request.until,
        workspace_filter=request.workspace_filter,
    )
    export = chargeback_service.export_report(report, request.format)
    return Response(
        content=export.content,
        media_type=export.content_type,
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )


@router.get(
    "/workspaces/{workspace_id}/forecast",
    response_model=CostForecastResponse,
    tags=["cost-governance-forecasts"],
)
async def get_forecast(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    forecast_service: ForecastService = Depends(get_forecast_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> CostForecastResponse:
    await _require_member(workspaces_service, workspace_id, _requester_id(current_user))
    latest = await forecast_service.get_latest_forecast(workspace_id)
    if latest is None:
        raise NotFoundError("COST_FORECAST_NOT_FOUND", "Cost forecast not found")
    return latest


@router.get(
    "/workspaces/{workspace_id}/anomalies",
    response_model=list[CostAnomalyResponse],
    tags=["cost-governance-anomalies"],
)
async def list_anomalies(
    workspace_id: UUID,
    state: AnomalyState | None = Query(default=None),
    cursor: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
    anomaly_service: AnomalyService = Depends(get_anomaly_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> list[CostAnomalyResponse]:
    await _require_member(workspaces_service, workspace_id, _requester_id(current_user))
    return await anomaly_service.list_anomalies(
        workspace_id,
        None if state is None else state.value,
        limit,
        cursor,
    )


@router.post(
    "/anomalies/{anomaly_id}/acknowledge",
    response_model=CostAnomalyResponse,
    tags=["cost-governance-anomalies"],
)
async def acknowledge_anomaly(
    anomaly_id: UUID,
    request: AnomalyAcknowledgeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    anomaly_service: AnomalyService = Depends(get_anomaly_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> CostAnomalyResponse:
    anomaly = await anomaly_service.repository.get_anomaly(anomaly_id)
    if anomaly is None:
        raise NotFoundError("COST_ANOMALY_NOT_FOUND", "Cost anomaly not found")
    requester = _requester_id(current_user)
    await _require_admin(workspaces_service, anomaly.workspace_id, requester)
    response = await anomaly_service.acknowledge(anomaly_id, requester, notes=request.notes)
    if response is None:
        raise NotFoundError("COST_ANOMALY_NOT_FOUND", "Cost anomaly not found")
    return response


@router.post(
    "/anomalies/{anomaly_id}/resolve",
    response_model=CostAnomalyResponse,
    tags=["cost-governance-anomalies"],
)
async def resolve_anomaly(
    anomaly_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    anomaly_service: AnomalyService = Depends(get_anomaly_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> CostAnomalyResponse:
    anomaly = await anomaly_service.repository.get_anomaly(anomaly_id)
    if anomaly is None:
        raise NotFoundError("COST_ANOMALY_NOT_FOUND", "Cost anomaly not found")
    await _require_admin(workspaces_service, anomaly.workspace_id, _requester_id(current_user))
    response = await anomaly_service.resolve(anomaly_id)
    if response is None:
        raise NotFoundError("COST_ANOMALY_NOT_FOUND", "Cost anomaly not found")
    return response
