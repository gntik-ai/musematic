from __future__ import annotations

from platform.analytics.forecast import ForecastEngine
from platform.analytics.recommendation import RecommendationEngine
from platform.analytics.repository import AnalyticsRepository, CostModelRepository
from platform.analytics.service import AnalyticsService
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_clickhouse(request: Request) -> AsyncClickHouseClient:
    return cast(AsyncClickHouseClient, request.app.state.clients["clickhouse"])


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def get_analytics_repository(request: Request) -> AnalyticsRepository:
    existing = getattr(request.app.state, "analytics_repository", None)
    if isinstance(existing, AnalyticsRepository):
        return existing
    repository = AnalyticsRepository(_get_clickhouse(request))
    request.app.state.analytics_repository = repository
    return repository


def build_analytics_service(
    *,
    repository: AnalyticsRepository,
    cost_model_repository: CostModelRepository,
    workspaces_service: WorkspacesService,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> AnalyticsService:
    return AnalyticsService(
        repo=repository,
        cost_model_repo=cost_model_repository,
        workspaces_service=workspaces_service,
        settings=settings,
        kafka_producer=producer,
        recommendation_engine=RecommendationEngine(),
        forecast_engine=ForecastEngine(),
    )


async def get_analytics_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    repository: AnalyticsRepository = Depends(get_analytics_repository),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> AnalyticsService:
    return build_analytics_service(
        repository=repository,
        cost_model_repository=CostModelRepository(session),
        workspaces_service=workspaces_service,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )
