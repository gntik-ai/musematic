from __future__ import annotations

from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.marketplace.quality_service import MarketplaceQualityAggregateService
from platform.marketplace.rating_service import MarketplaceRatingService
from platform.marketplace.recommendation_service import MarketplaceRecommendationService
from platform.marketplace.repository import MarketplaceRepository
from platform.marketplace.search_service import MarketplaceSearchService
from platform.marketplace.trending_service import MarketplaceTrendingService
from platform.registry.dependencies import get_registry_service
from platform.registry.service import RegistryService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_opensearch(request: Request) -> AsyncOpenSearchClient:
    return cast(AsyncOpenSearchClient, request.app.state.clients["opensearch"])


def _get_qdrant(request: Request) -> AsyncQdrantClient:
    return cast(AsyncQdrantClient, request.app.state.clients["qdrant"])


def _get_clickhouse(request: Request) -> AsyncClickHouseClient:
    return cast(AsyncClickHouseClient, request.app.state.clients["clickhouse"])


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def build_search_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    opensearch: AsyncOpenSearchClient,
    qdrant: AsyncQdrantClient,
    workspaces_service: WorkspacesService | None,
    registry_service: RegistryService | None = None,
) -> MarketplaceSearchService:
    return MarketplaceSearchService(
        repository=MarketplaceRepository(session),
        settings=settings,
        opensearch=opensearch,
        qdrant=qdrant,
        workspaces_service=workspaces_service,
        registry_service=registry_service,
    )


async def get_search_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
    registry_service: RegistryService = Depends(get_registry_service),
) -> MarketplaceSearchService:
    return build_search_service(
        session=session,
        settings=_get_settings(request),
        opensearch=_get_opensearch(request),
        qdrant=_get_qdrant(request),
        workspaces_service=workspaces_service,
        registry_service=registry_service,
    )


def build_quality_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> MarketplaceQualityAggregateService:
    return MarketplaceQualityAggregateService(
        repository=MarketplaceRepository(session),
        settings=settings,
        producer=producer,
    )


async def get_quality_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> MarketplaceQualityAggregateService:
    return build_quality_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )


def build_rating_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    clickhouse: AsyncClickHouseClient,
    search_service: MarketplaceSearchService,
    quality_service: MarketplaceQualityAggregateService,
    registry_service: RegistryService | None,
) -> MarketplaceRatingService:
    repository = MarketplaceRepository(session)
    return MarketplaceRatingService(
        repository=repository,
        settings=settings,
        producer=producer,
        clickhouse=clickhouse,
        search_service=search_service,
        quality_service=quality_service,
        registry_service=registry_service,
    )


async def get_rating_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
    registry_service: RegistryService = Depends(get_registry_service),
) -> MarketplaceRatingService:
    search_service = build_search_service(
        session=session,
        settings=_get_settings(request),
        opensearch=_get_opensearch(request),
        qdrant=_get_qdrant(request),
        workspaces_service=workspaces_service,
        registry_service=registry_service,
    )
    quality_service = build_quality_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )
    return build_rating_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        clickhouse=_get_clickhouse(request),
        search_service=search_service,
        quality_service=quality_service,
        registry_service=registry_service,
    )


def build_recommendation_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    clickhouse: AsyncClickHouseClient,
    qdrant: AsyncQdrantClient,
    redis_client: AsyncRedisClient,
    search_service: MarketplaceSearchService,
    workspaces_service: WorkspacesService | None,
) -> MarketplaceRecommendationService:
    return MarketplaceRecommendationService(
        repository=MarketplaceRepository(session),
        settings=settings,
        clickhouse=clickhouse,
        qdrant=qdrant,
        redis_client=redis_client,
        search_service=search_service,
        workspaces_service=workspaces_service,
    )


async def get_recommendation_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
    registry_service: RegistryService = Depends(get_registry_service),
) -> MarketplaceRecommendationService:
    search_service = build_search_service(
        session=session,
        settings=_get_settings(request),
        opensearch=_get_opensearch(request),
        qdrant=_get_qdrant(request),
        workspaces_service=workspaces_service,
        registry_service=registry_service,
    )
    return build_recommendation_service(
        session=session,
        settings=_get_settings(request),
        clickhouse=_get_clickhouse(request),
        qdrant=_get_qdrant(request),
        redis_client=_get_redis(request),
        search_service=search_service,
        workspaces_service=workspaces_service,
    )


def build_trending_service(
    *,
    session: AsyncSession,
    redis_client: AsyncRedisClient,
    search_service: MarketplaceSearchService,
) -> MarketplaceTrendingService:
    return MarketplaceTrendingService(
        repository=MarketplaceRepository(session),
        redis_client=redis_client,
        search_service=search_service,
    )


async def get_trending_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
    registry_service: RegistryService = Depends(get_registry_service),
) -> MarketplaceTrendingService:
    search_service = build_search_service(
        session=session,
        settings=_get_settings(request),
        opensearch=_get_opensearch(request),
        qdrant=_get_qdrant(request),
        workspaces_service=workspaces_service,
        registry_service=registry_service,
    )
    return build_trending_service(
        session=session,
        redis_client=_get_redis(request),
        search_service=search_service,
    )
