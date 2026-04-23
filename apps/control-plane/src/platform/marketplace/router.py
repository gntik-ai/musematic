from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.marketplace.dependencies import (
    get_quality_service,
    get_rating_service,
    get_recommendation_service,
    get_search_service,
    get_trending_service,
)
from platform.marketplace.quality_service import MarketplaceQualityAggregateService
from platform.marketplace.rating_service import MarketplaceRatingService
from platform.marketplace.recommendation_service import MarketplaceRecommendationService
from platform.marketplace.schemas import (
    AgentComparisonResponse,
    AgentListingProjection,
    ContextualSuggestionRequest,
    ContextualSuggestionResponse,
    CreatorAnalyticsResponse,
    MarketplaceSearchRequest,
    MarketplaceSearchResponse,
    QualityProfileSchema,
    RatingCreateRequest,
    RatingResponse,
    RatingsListResponse,
    RecommendationResponse,
    TrendingAgentsResponse,
)
from platform.marketplace.search_service import MarketplaceSearchService
from platform.marketplace.trending_service import MarketplaceTrendingService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter(prefix="/api/v1/marketplace", tags=["marketplace"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _requesting_agent_id(current_user: dict[str, Any]) -> UUID | None:
    agent_id = current_user.get("agent_profile_id") or current_user.get("agent_id")
    return UUID(str(agent_id)) if agent_id is not None else None


def _workspace_id(request: Request, current_user: dict[str, Any]) -> UUID:
    header_value = request.headers.get("X-Workspace-ID")
    if header_value:
        return UUID(header_value)
    claim_value = current_user.get("workspace_id")
    return UUID(str(claim_value))


@router.post("/search", response_model=MarketplaceSearchResponse)
async def search_marketplace(
    payload: MarketplaceSearchRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    search_service: MarketplaceSearchService = Depends(get_search_service),
) -> MarketplaceSearchResponse:
    workspace_id = _workspace_id(request, current_user)
    return await search_service.search(
        payload,
        workspace_id,
        _actor_id(current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )


@router.get("/compare", response_model=AgentComparisonResponse)
async def compare_agents(
    request: Request,
    agent_ids: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    search_service: MarketplaceSearchService = Depends(get_search_service),
) -> AgentComparisonResponse:
    ids = [UUID(item.strip()) for item in agent_ids.split(",") if item.strip()]
    return await search_service.compare(
        ids,
        _workspace_id(request, current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )


@router.get("/recommendations", response_model=RecommendationResponse)
async def get_recommendations(
    request: Request,
    limit: int = Query(default=10, ge=1, le=20),
    current_user: dict[str, Any] = Depends(get_current_user),
    recommendation_service: MarketplaceRecommendationService = Depends(get_recommendation_service),
) -> RecommendationResponse:
    workspace_id = _workspace_id(request, current_user)
    return await recommendation_service.get_recommendations(
        _actor_id(current_user),
        workspace_id,
        limit=limit,
        requesting_agent_id=_requesting_agent_id(current_user),
    )


@router.post("/contextual-suggestions", response_model=ContextualSuggestionResponse)
async def get_contextual_suggestions(
    payload: ContextualSuggestionRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    recommendation_service: MarketplaceRecommendationService = Depends(get_recommendation_service),
) -> ContextualSuggestionResponse:
    return await recommendation_service.get_contextual_suggestions(
        payload,
        workspace_id=_workspace_id(request, current_user),
        user_id=_actor_id(current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )


@router.get("/trending", response_model=TrendingAgentsResponse)
async def get_trending(
    request: Request,
    limit: int = Query(default=10, ge=1, le=20),
    current_user: dict[str, Any] = Depends(get_current_user),
    trending_service: MarketplaceTrendingService = Depends(get_trending_service),
) -> TrendingAgentsResponse:
    return await trending_service.get_trending(
        _workspace_id(request, current_user),
        limit=limit,
    )


@router.get("/agents/{agent_id}", response_model=AgentListingProjection)
async def get_agent_listing(
    agent_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    search_service: MarketplaceSearchService = Depends(get_search_service),
) -> AgentListingProjection:
    return await search_service.get_listing(
        agent_id,
        _workspace_id(request, current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )


@router.get("/agents/{agent_id}/quality", response_model=QualityProfileSchema)
async def get_quality_profile(
    agent_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    search_service: MarketplaceSearchService = Depends(get_search_service),
    quality_service: MarketplaceQualityAggregateService = Depends(get_quality_service),
) -> QualityProfileSchema:
    del quality_service
    await search_service.get_listing(
        agent_id,
        _workspace_id(request, current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )
    aggregate = await search_service.repository.get_or_create_quality_aggregate(agent_id)
    return QualityProfileSchema(
        agent_id=agent_id,
        has_data=aggregate.has_data,
        success_rate=aggregate.success_rate if aggregate.has_data else None,
        quality_score_avg=aggregate.quality_score_avg if aggregate.has_data else None,
        self_correction_rate=aggregate.self_correction_rate if aggregate.has_data else None,
        satisfaction_avg=aggregate.satisfaction_avg if aggregate.has_data else None,
        satisfaction_count=aggregate.satisfaction_count,
        certification_compliance=aggregate.certification_status,
        last_updated_at=aggregate.data_source_last_updated_at,
        source_unavailable=aggregate.source_unavailable_since is not None,
    )


@router.post("/agents/{agent_id}/ratings", response_model=RatingResponse)
async def create_or_update_rating(
    agent_id: UUID,
    payload: RatingCreateRequest,
    request: Request,
    response: Response,
    current_user: dict[str, Any] = Depends(get_current_user),
    rating_service: MarketplaceRatingService = Depends(get_rating_service),
) -> RatingResponse:
    rating, created = await rating_service.upsert_rating(
        agent_id,
        _actor_id(current_user),
        payload,
        workspace_id=_workspace_id(request, current_user),
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return rating


@router.get("/agents/{agent_id}/ratings", response_model=RatingsListResponse)
async def list_ratings(
    agent_id: UUID,
    score: int | None = Query(default=None, ge=1, le=5),
    sort: str = Query(default="recent", pattern="^(recent|highest|lowest)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    rating_service: MarketplaceRatingService = Depends(get_rating_service),
) -> RatingsListResponse:
    return await rating_service.list_ratings(
        agent_id,
        score_filter=score,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/analytics/{agent_id}", response_model=CreatorAnalyticsResponse)
async def get_creator_analytics(
    agent_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    rating_service: MarketplaceRatingService = Depends(get_rating_service),
) -> CreatorAnalyticsResponse:
    return await rating_service.get_creator_analytics(agent_id, _actor_id(current_user))


@router.get("/agents/{namespace}/{name}", response_model=AgentListingProjection)
async def get_agent_listing_by_fqn(
    namespace: str,
    name: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    search_service: MarketplaceSearchService = Depends(get_search_service),
) -> AgentListingProjection:
    return await search_service.get_listing_by_fqn(
        namespace,
        name,
        _workspace_id(request, current_user),
        actor_id=_actor_id(current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )
