from __future__ import annotations

from datetime import UTC, datetime
from platform.marketplace.exceptions import ComparisonRangeError
from platform.marketplace.router import _actor_id, _workspace_id
from platform.marketplace.schemas import (
    AgentComparisonResponse,
    AgentComparisonRow,
    AgentListingProjection,
    AggregateRatingSchema,
    ComparisonAttribute,
    ContextualSuggestionResponse,
    CreatorAnalyticsResponse,
    FailurePatternEntry,
    InvocationTrendPoint,
    MarketplaceSearchResponse,
    QualityProfileSchema,
    RatingResponse,
    RatingsListResponse,
    RecommendationResponse,
    RecommendedAgentEntry,
    TrendingAgentEntry,
    TrendingAgentsResponse,
)
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from tests.marketplace_support import build_current_user, build_marketplace_app


def _listing(agent_id: UUID, fqn: str, *, name: str = "Agent") -> AgentListingProjection:
    return AgentListingProjection(
        agent_id=agent_id,
        fqn=fqn,
        name=name,
        description="desc",
        capabilities=["finance"],
        tags=["finance"],
        maturity_level=3,
        trust_tier="certified",
        certification_status="compliant",
        cost_tier="metered",
        quality_profile=QualityProfileSchema(has_data=False),
        aggregate_rating=AggregateRatingSchema(avg_score=4.5, review_count=3),
    )


class SearchStub:
    def __init__(self, listing: AgentListingProjection) -> None:
        self.listing = listing

    async def search(self, payload, workspace_id, user_id):
        del payload, workspace_id, user_id
        return MarketplaceSearchResponse(
            results=[self.listing],
            total=1,
            page=1,
            page_size=20,
            query="finance",
            has_results=True,
        )

    async def compare(self, ids, workspace_id):
        del workspace_id
        if len(ids) == 1:
            raise ComparisonRangeError(1)
        return AgentComparisonResponse(
            agents=[
                AgentComparisonRow(
                    agent_id=self.listing.agent_id,
                    fqn=self.listing.fqn,
                    name=self.listing.name,
                    capabilities=ComparisonAttribute(value=["finance"], differs=False),
                    maturity_level=ComparisonAttribute(value=3, differs=False),
                    trust_tier=ComparisonAttribute(value="certified", differs=False),
                    certification_status=ComparisonAttribute(value="compliant", differs=False),
                    quality_score_avg=ComparisonAttribute(value=80.0, differs=True),
                    cost_tier=ComparisonAttribute(value="metered", differs=False),
                    success_rate=ComparisonAttribute(value=0.9, differs=True),
                    user_rating_avg=ComparisonAttribute(value=4.5, differs=True),
                )
            ],
            compared_count=len(ids),
        )

    async def get_listing(self, agent_id, workspace_id):
        del workspace_id
        if agent_id != self.listing.agent_id:
            raise ComparisonRangeError(1)
        return self.listing

    @property
    def repository(self):
        class _Repo:
            async def get_or_create_quality_aggregate(self, agent_id):
                return SimpleNamespace(
                    agent_id=agent_id,
                    has_data=True,
                    success_rate=0.9,
                    quality_score_avg=80.0,
                    self_correction_rate=0.1,
                    satisfaction_avg=4.5,
                    satisfaction_count=3,
                    certification_status="compliant",
                    data_source_last_updated_at=datetime.now(UTC),
                    source_unavailable_since=None,
                )

        return _Repo()


class RecommendationStub:
    def __init__(self, listing: AgentListingProjection) -> None:
        self.listing = listing

    async def get_recommendations(self, user_id, workspace_id, *, limit):
        del user_id, workspace_id, limit
        return RecommendationResponse(
            recommendations=[
                RecommendedAgentEntry(
                    agent=self.listing,
                    score=9.0,
                    reasoning="Popular.",
                    recommendation_type="fallback",
                )
            ],
            recommendation_type="fallback",
        )

    async def get_contextual_suggestions(self, payload, *, workspace_id, user_id):
        del payload, workspace_id, user_id
        return ContextualSuggestionResponse(
            suggestions=[self.listing],
            has_results=True,
            context_type="workflow_step",
        )


class TrendingStub:
    def __init__(self, listing: AgentListingProjection) -> None:
        self.listing = listing

    async def get_trending(self, workspace_id, *, limit):
        del workspace_id, limit
        return TrendingAgentsResponse(
            agents=[
                TrendingAgentEntry(
                    rank=1,
                    agent=self.listing,
                    trending_score=9.0,
                    growth_rate=9.0,
                    invocations_this_week=9,
                    invocations_last_week=1,
                    trending_reason="9x more invocations this week",
                )
            ],
            snapshot_date=datetime.now(UTC).date(),
            total=1,
        )


class RatingStub:
    def __init__(self, listing: AgentListingProjection) -> None:
        self.listing = listing

    async def upsert_rating(self, agent_id, user_id, payload, *, workspace_id=None):
        del workspace_id
        return (
            RatingResponse(
                rating_id=uuid4(),
                agent_id=agent_id,
                user_id=user_id,
                score=payload.score,
                review_text=payload.review_text,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            True,
        )

    async def list_ratings(self, agent_id, *, score_filter, sort, page, page_size):
        del agent_id, score_filter, sort
        return RatingsListResponse(
            ratings=[
                RatingResponse(
                    rating_id=uuid4(),
                    agent_id=self.listing.agent_id,
                    user_id=uuid4(),
                    score=5,
                    review_text="great",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ],
            total=1,
            page=page,
            page_size=page_size,
            avg_score=5.0,
        )

    async def get_creator_analytics(self, agent_id, requesting_user_id):
        del agent_id, requesting_user_id
        return CreatorAnalyticsResponse(
            agent_id=self.listing.agent_id,
            agent_fqn=self.listing.fqn,
            invocation_count_total=10,
            invocation_count_30d=5,
            avg_satisfaction=4.5,
            satisfaction_count=3,
            common_failure_patterns=[
                FailurePatternEntry(error_type="timeout", count=1, percentage=1.0)
            ],
            invocation_trend=[
                InvocationTrendPoint(date=datetime.now(UTC).date(), count=2)
            ],
        )


def test_marketplace_router_helper_functions_use_header_and_claims() -> None:
    workspace_id = uuid4()
    user = build_current_user(user_id=uuid4(), workspace_id=workspace_id)
    request = SimpleNamespace(headers={"X-Workspace-ID": str(workspace_id)})

    assert _actor_id(user) == UUID(user["sub"])
    assert _workspace_id(request, user) == workspace_id
    assert _workspace_id(SimpleNamespace(headers={}), user) == workspace_id


@pytest.mark.asyncio
async def test_marketplace_router_endpoints_delegate_to_services() -> None:
    workspace_id = uuid4()
    user = build_current_user(workspace_id=workspace_id)
    listing = _listing(uuid4(), "finance-ops:router-agent", name="Router Agent")
    search = SearchStub(listing)
    app = build_marketplace_app(
        current_user=user,
        search_service=search,
        quality_service=SimpleNamespace(),
        rating_service=RatingStub(listing),
        recommendation_service=RecommendationStub(listing),
        trending_service=TrendingStub(listing),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        search_response = await client.post(
            "/api/v1/marketplace/search",
            json={"query": "finance"},
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        compare_response = await client.get(
            "/api/v1/marketplace/compare",
            params={"agent_ids": f"{listing.agent_id},{uuid4()}"},
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        recommendations = await client.get(
            "/api/v1/marketplace/recommendations",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        contextual = await client.post(
            "/api/v1/marketplace/contextual-suggestions",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"context_type": "workflow_step", "context_text": "route finance"},
        )
        trending = await client.get(
            "/api/v1/marketplace/trending",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        listing_response = await client.get(
            f"/api/v1/marketplace/agents/{listing.agent_id}",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        quality = await client.get(
            f"/api/v1/marketplace/agents/{listing.agent_id}/quality",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        created_rating = await client.post(
            f"/api/v1/marketplace/agents/{listing.agent_id}/ratings",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"score": 5, "review_text": "great"},
        )
        ratings = await client.get(
            f"/api/v1/marketplace/agents/{listing.agent_id}/ratings",
        )
        analytics = await client.get(f"/api/v1/marketplace/analytics/{listing.agent_id}")

    assert search_response.status_code == 200
    assert compare_response.status_code == 200
    assert recommendations.status_code == 200
    assert contextual.status_code == 200
    assert trending.status_code == 200
    assert listing_response.status_code == 200
    assert quality.status_code == 200
    assert created_rating.status_code == 201
    assert ratings.status_code == 200
    assert analytics.status_code == 200


@pytest.mark.asyncio
async def test_marketplace_router_surfaces_service_errors() -> None:
    workspace_id = uuid4()
    user = build_current_user(workspace_id=workspace_id)
    listing = _listing(uuid4(), "finance-ops:router-agent", name="Router Agent")
    app = build_marketplace_app(
        current_user=user,
        search_service=SearchStub(listing),
        quality_service=SimpleNamespace(),
        rating_service=RatingStub(listing),
        recommendation_service=RecommendationStub(listing),
        trending_service=TrendingStub(listing),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/marketplace/compare",
            params={"agent_ids": str(listing.agent_id)},
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "COMPARISON_RANGE_INVALID"
