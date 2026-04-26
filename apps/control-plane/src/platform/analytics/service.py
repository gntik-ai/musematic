from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from platform.analytics.events import (
    BudgetThresholdCrossedPayload,
    ForecastUpdatedPayload,
    RecommendationGeneratedPayload,
    publish_budget_threshold_crossed,
    publish_forecast_updated,
    publish_recommendation_generated,
)
from platform.analytics.exceptions import AnalyticsError, WorkspaceAuthorizationError
from platform.analytics.forecast import ForecastEngine
from platform.analytics.recommendation import RecommendationEngine
from platform.analytics.repository import AnalyticsRepository, CostModelRepository
from platform.analytics.schemas import (
    AgentCostQuality,
    CostIntelligenceParams,
    CostIntelligenceResponse,
    ForecastParams,
    Granularity,
    KpiDataPoint,
    KpiSeries,
    RecommendationsParams,
    RecommendationsResponse,
    ResourcePrediction,
    UsageQueryParams,
    UsageResponse,
    UsageRollupItem,
)
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from typing import Any, cast
from uuid import UUID, uuid4

LOGGER = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(
        self,
        *,
        repo: AnalyticsRepository,
        cost_model_repo: CostModelRepository,
        workspaces_service: Any | None,
        settings: PlatformSettings,
        kafka_producer: EventProducer | None,
        recommendation_engine: RecommendationEngine,
        forecast_engine: ForecastEngine,
        cost_governance_service: Any | None = None,
    ) -> None:
        self.repo = repo
        self.cost_model_repo = cost_model_repo
        self.workspaces_service = workspaces_service
        self.settings = settings
        self.kafka_producer = kafka_producer
        self.recommendation_engine = recommendation_engine
        self.forecast_engine = forecast_engine
        self.cost_governance_service = cost_governance_service

    async def get_usage(self, params: UsageQueryParams, user_id: UUID) -> UsageResponse:
        self._validate_window(params.start_time, params.end_time)
        await self._assert_workspace_access(params.workspace_id, user_id)
        rows, total = await self.repo.query_usage_rollups(
            params.workspace_id,
            params.granularity,
            params.start_time,
            params.end_time,
            params.agent_fqn,
            params.model_id,
            params.limit,
            params.offset,
        )
        items = [UsageRollupItem.model_validate(row) for row in rows]
        return UsageResponse(
            items=items,
            total=total,
            workspace_id=params.workspace_id,
            granularity=params.granularity,
            start_time=params.start_time,
            end_time=params.end_time,
        )

    async def get_cost_intelligence(
        self,
        params: CostIntelligenceParams,
        user_id: UUID,
    ) -> CostIntelligenceResponse:
        self._validate_window(params.start_time, params.end_time)
        await self._assert_workspace_access(params.workspace_id, user_id)
        rows = await self.repo.query_cost_quality_join(
            params.workspace_id,
            params.start_time,
            params.end_time,
        )
        agents = self._rank_cost_quality(rows)
        return CostIntelligenceResponse(
            workspace_id=params.workspace_id,
            period_start=params.start_time,
            period_end=params.end_time,
            agents=agents,
        )

    async def get_recommendations(
        self,
        params: RecommendationsParams,
        user_id: UUID,
    ) -> RecommendationsResponse:
        await self._assert_workspace_access(params.workspace_id, user_id)
        metrics = await self.repo.query_agent_metrics(params.workspace_id)
        baselines = await self.repo.query_fleet_baselines(params.workspace_id)
        recommendations = self.recommendation_engine.generate(metrics, baselines)
        generated_at = datetime.now(UTC)
        if recommendations:
            await publish_recommendation_generated(
                self.kafka_producer,
                RecommendationGeneratedPayload(
                    workspace_id=params.workspace_id,
                    recommendation_count=len(recommendations),
                    generated_at=generated_at,
                ),
                CorrelationContext(
                    workspace_id=params.workspace_id,
                    correlation_id=uuid4(),
                ),
            )
        return RecommendationsResponse(
            workspace_id=params.workspace_id,
            recommendations=recommendations,
            generated_at=generated_at,
        )

    async def get_forecast(self, params: ForecastParams, user_id: UUID) -> ResourcePrediction:
        if params.horizon_days not in {7, 30, 90}:
            raise AnalyticsError(
                "INVALID_PARAMETERS",
                "horizon_days must be one of 7, 30, or 90",
            )
        await self._assert_workspace_access(params.workspace_id, user_id)
        daily_rows = await self.repo.query_daily_cost_series(params.workspace_id, 90)
        daily_costs = [float(row["cost_usd"]) for row in daily_rows]
        start_date = daily_rows[0]["day"].date() if daily_rows else datetime.now(UTC).date()
        prediction = self.forecast_engine.forecast(
            daily_costs,
            params.horizon_days,
            workspace_id=params.workspace_id,
            start_date=start_date,
        )
        await publish_forecast_updated(
            self.kafka_producer,
            ForecastUpdatedPayload(
                workspace_id=params.workspace_id,
                horizon_days=params.horizon_days,
                trend_direction=prediction.trend_direction,
                total_projected_expected=prediction.total_projected_expected,
                generated_at=prediction.generated_at,
            ),
            CorrelationContext(
                workspace_id=params.workspace_id,
                correlation_id=uuid4(),
            ),
        )
        return prediction

    async def get_kpi_series(
        self,
        workspace_id: UUID,
        granularity: Granularity,
        start_time: datetime,
        end_time: datetime,
        user_id: UUID,
    ) -> KpiSeries:
        self._validate_window(start_time, end_time)
        await self._assert_workspace_access(workspace_id, user_id)
        rows = await self.repo.query_kpi_series(workspace_id, granularity, start_time, end_time)
        return KpiSeries(
            workspace_id=workspace_id,
            granularity=granularity,
            start_time=start_time,
            end_time=end_time,
            items=[KpiDataPoint.model_validate(row) for row in rows],
        )

    async def get_workspace_cost_summary(
        self,
        workspace_id: UUID,
        days_back: int = 30,
    ) -> dict[str, Any]:
        if self.cost_governance_service is not None:
            LOGGER.info(
                "Delegating workspace cost summary to cost governance",
                extra={"workspace_id": str(workspace_id), "days_back": days_back},
            )
            summary = await self.cost_governance_service.get_workspace_cost_summary(
                workspace_id,
                period_start=datetime.now(UTC) - timedelta(days=days_back),
            )
            return {
                "total_cost_usd": summary["total_cost_usd"],
                "period_start": summary["period_start"],
                "period_end": summary["period_end"],
                "execution_count": summary["execution_count"],
                "avg_daily_cost_usd": summary["avg_daily_cost_usd"],
            }
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=days_back)
        rows = await self.repo.query_kpi_series(
            workspace_id,
            Granularity.DAILY,
            start_time,
            end_time,
        )
        total_cost = sum(float(row["total_cost_usd"]) for row in rows)
        execution_count = sum(int(row["execution_count"]) for row in rows)
        avg_daily_cost = total_cost / max(len(rows), 1)
        return {
            "total_cost_usd": round(total_cost, 4),
            "period_start": start_time,
            "period_end": end_time,
            "execution_count": execution_count,
            "avg_daily_cost_usd": round(avg_daily_cost, 4),
        }

    async def check_budget_thresholds(self, days_back: int = 30) -> list[UUID]:
        if self.cost_governance_service is not None:
            LOGGER.info(
                "Delegating budget threshold checks to cost governance",
                extra={"days_back": days_back},
            )
            return cast(list[UUID], await self.cost_governance_service.evaluate_thresholds())
        threshold = float(self.settings.ANALYTICS_BUDGET_THRESHOLD_USD)
        if threshold <= 0:
            return []
        crossed: list[UUID] = []
        for workspace_id in await self.repo.list_workspace_ids():
            summary = await self.get_workspace_cost_summary(workspace_id, days_back)
            total_cost = float(summary["total_cost_usd"])
            if total_cost < threshold:
                continue
            crossed.append(workspace_id)
            await publish_budget_threshold_crossed(
                self.kafka_producer,
                BudgetThresholdCrossedPayload(
                    workspace_id=workspace_id,
                    threshold_usd=threshold,
                    total_cost_usd=total_cost,
                    period_start=summary["period_start"],
                    period_end=summary["period_end"],
                    execution_count=int(summary["execution_count"]),
                ),
                CorrelationContext(
                    workspace_id=workspace_id,
                    correlation_id=uuid4(),
                ),
            )
        return crossed

    async def _assert_workspace_access(self, workspace_id: UUID, user_id: UUID) -> None:
        if self.workspaces_service is None:
            raise AnalyticsError("WORKSPACE_ACCESS_DENIED", "Workspace service unavailable")
        workspace_ids = await self.workspaces_service.get_user_workspace_ids(user_id)
        if workspace_id not in set(workspace_ids):
            raise WorkspaceAuthorizationError(workspace_id)

    def _validate_window(self, start_time: datetime, end_time: datetime) -> None:
        if start_time > end_time:
            raise AnalyticsError(
                "INVALID_PARAMETERS",
                "start_time must be less than or equal to end_time",
            )

    def _rank_cost_quality(self, rows: list[dict[str, Any]]) -> list[AgentCostQuality]:
        ranked: list[dict[str, Any]] = []
        for row in rows:
            avg_quality = row.get("avg_quality_score")
            quality_value = None if avg_quality is None else float(avg_quality)
            total_cost = float(row.get("total_cost_usd") or 0.0)
            if quality_value is None or quality_value == 0.0:
                cost_per_quality = None
            else:
                cost_per_quality = total_cost / quality_value
            ranked.append(
                {
                    "agent_fqn": row["agent_fqn"],
                    "model_id": row["model_id"],
                    "provider": row["provider"],
                    "total_cost_usd": round(total_cost, 4),
                    "avg_quality_score": None if quality_value is None else round(quality_value, 4),
                    "cost_per_quality": None
                    if cost_per_quality is None
                    else round(cost_per_quality, 4),
                    "execution_count": int(row.get("execution_count") or 0),
                }
            )

        ranked.sort(
            key=lambda item: (
                item["cost_per_quality"] is None,
                item["cost_per_quality"] or 0.0,
                item["agent_fqn"],
                item["model_id"],
            )
        )
        return [
            AgentCostQuality(
                **item,
                efficiency_rank=index,
            )
            for index, item in enumerate(ranked, start=1)
        ]
