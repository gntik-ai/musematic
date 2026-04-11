from __future__ import annotations

from datetime import datetime
from platform.analytics.dependencies import get_analytics_service
from platform.analytics.schemas import (
    CostIntelligenceParams,
    CostIntelligenceResponse,
    ForecastParams,
    Granularity,
    KpiSeries,
    RecommendationsParams,
    RecommendationsResponse,
    ResourcePrediction,
    UsageQueryParams,
    UsageResponse,
)
from platform.analytics.service import AnalyticsService
from platform.common.dependencies import get_current_user
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _requester_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    workspace_id: UUID,
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    granularity: Granularity = Query(default=Granularity.DAILY),
    agent_fqn: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> UsageResponse:
    return await analytics_service.get_usage(
        UsageQueryParams(
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            granularity=granularity,
            agent_fqn=agent_fqn,
            model_id=model_id,
            limit=limit,
            offset=offset,
        ),
        _requester_id(current_user),
    )


@router.get("/cost-intelligence", response_model=CostIntelligenceResponse)
async def get_cost_intelligence(
    workspace_id: UUID,
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> CostIntelligenceResponse:
    return await analytics_service.get_cost_intelligence(
        CostIntelligenceParams(
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
        ),
        _requester_id(current_user),
    )


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> RecommendationsResponse:
    return await analytics_service.get_recommendations(
        RecommendationsParams(workspace_id=workspace_id),
        _requester_id(current_user),
    )


@router.get("/cost-forecast", response_model=ResourcePrediction)
async def get_cost_forecast(
    workspace_id: UUID,
    horizon_days: int = Query(default=30, ge=7, le=90),
    current_user: dict[str, Any] = Depends(get_current_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> ResourcePrediction:
    return await analytics_service.get_forecast(
        ForecastParams(
            workspace_id=workspace_id,
            horizon_days=horizon_days,
        ),
        _requester_id(current_user),
    )


@router.get("/kpi", response_model=KpiSeries)
async def get_kpi(
    workspace_id: UUID,
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    granularity: Granularity = Query(default=Granularity.DAILY),
    current_user: dict[str, Any] = Depends(get_current_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> KpiSeries:
    return await analytics_service.get_kpi_series(
        workspace_id=workspace_id,
        granularity=granularity,
        start_time=start_time,
        end_time=end_time,
        user_id=_requester_id(current_user),
    )
