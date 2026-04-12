from __future__ import annotations

from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.marketplace.events import emit_rating_created, emit_rating_updated
from platform.marketplace.exceptions import InvocationRequiredError, VisibilityDeniedError
from platform.marketplace.quality_service import MarketplaceQualityAggregateService
from platform.marketplace.repository import MarketplaceRepository
from platform.marketplace.schemas import (
    CreatorAnalyticsResponse,
    FailurePatternEntry,
    InvocationTrendPoint,
    RatingCreateRequest,
    RatingResponse,
    RatingsListResponse,
)
from platform.marketplace.search_service import MarketplaceSearchService
from typing import Any
from uuid import UUID, uuid4


class MarketplaceRatingService:
    def __init__(
        self,
        *,
        repository: MarketplaceRepository,
        settings: PlatformSettings,
        producer: EventProducer | None,
        clickhouse: AsyncClickHouseClient,
        search_service: MarketplaceSearchService,
        quality_service: MarketplaceQualityAggregateService,
        registry_service: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.clickhouse = clickhouse
        self.search_service = search_service
        self.quality_service = quality_service
        self.registry_service = registry_service

    async def upsert_rating(
        self,
        agent_id: UUID,
        user_id: UUID,
        request: RatingCreateRequest,
        *,
        workspace_id: UUID | None = None,
    ) -> tuple[RatingResponse, bool]:
        if not await self._has_prior_invocation(user_id, agent_id):
            raise InvocationRequiredError(agent_id)
        rating, created = await self.repository.upsert_rating(
            user_id=user_id,
            agent_id=agent_id,
            score=request.score,
            review_text=request.review_text,
        )
        await self.quality_service.update_satisfaction_aggregate(agent_id)
        correlation = CorrelationContext(
            workspace_id=workspace_id,
            correlation_id=uuid4(),
        )
        if created:
            await emit_rating_created(
                self.producer,
                agent_id=agent_id,
                user_id=user_id,
                score=request.score,
                workspace_id=workspace_id,
                correlation_ctx=correlation,
            )
        else:
            await emit_rating_updated(
                self.producer,
                agent_id=agent_id,
                user_id=user_id,
                score=request.score,
                workspace_id=workspace_id,
                correlation_ctx=correlation,
            )
        return self._rating_response(rating), created

    async def list_ratings(
        self,
        agent_id: UUID,
        *,
        score_filter: int | None,
        sort: str,
        page: int,
        page_size: int,
    ) -> RatingsListResponse:
        ratings, total, avg_score = await self.repository.get_ratings_for_agent(
            agent_id,
            score_filter=score_filter,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        return RatingsListResponse(
            ratings=[self._rating_response(rating) for rating in ratings],
            total=total,
            page=page,
            page_size=page_size,
            avg_score=avg_score,
        )

    async def get_creator_analytics(
        self,
        agent_id: UUID,
        requesting_user_id: UUID,
    ) -> CreatorAnalyticsResponse:
        owner_getter = getattr(self.registry_service, "get_agent_namespace_owner", None)
        if owner_getter is None:
            raise VisibilityDeniedError(agent_id)
        owner_id = await owner_getter(agent_id)
        if owner_id is None or owner_id != requesting_user_id:
            raise VisibilityDeniedError(agent_id)
        document = await self.search_service._fetch_document(agent_id)
        if document is None:
            raise VisibilityDeniedError(agent_id)
        agent_fqn = str(document.get("fqn") or "")
        invocation_rows = await self.clickhouse.execute_query(
            """
            SELECT
                count() AS invocation_count_total,
                countIf(timestamp >= now() - INTERVAL 30 DAY) AS invocation_count_30d
            FROM usage_events
            WHERE agent_id = {agent_id:UUID}
            """,
            {"agent_id": agent_id},
        )
        failure_rows = await self.clickhouse.execute_query(
            """
            SELECT
                error_type,
                count() AS failure_count
            FROM usage_events
            WHERE
                agent_id = {agent_id:UUID}
                AND status = 'failed'
                AND timestamp >= now() - INTERVAL 30 DAY
            GROUP BY error_type
            ORDER BY failure_count DESC, error_type ASC
            LIMIT 3
            """,
            {"agent_id": agent_id},
        )
        trend_rows = await self.clickhouse.execute_query(
            """
            SELECT
                toDate(timestamp) AS day,
                count() AS invocation_count
            FROM usage_events
            WHERE
                agent_id = {agent_id:UUID}
                AND timestamp >= now() - INTERVAL 30 DAY
            GROUP BY day
            ORDER BY day ASC
            """,
            {"agent_id": agent_id},
        )
        summary = invocation_rows[0] if invocation_rows else {}
        failure_total = sum(int(row.get("failure_count") or 0) for row in failure_rows)
        quality = await self.repository.get_or_create_quality_aggregate(agent_id)
        return CreatorAnalyticsResponse(
            agent_id=agent_id,
            agent_fqn=agent_fqn,
            invocation_count_total=int(summary.get("invocation_count_total") or 0),
            invocation_count_30d=int(summary.get("invocation_count_30d") or 0),
            avg_satisfaction=quality.satisfaction_avg if quality.satisfaction_count else None,
            satisfaction_count=quality.satisfaction_count,
            common_failure_patterns=[
                FailurePatternEntry(
                    error_type=str(row.get("error_type") or "unknown"),
                    count=int(row.get("failure_count") or 0),
                    percentage=(
                        int(row.get("failure_count") or 0) / max(failure_total, 1)
                    ),
                )
                for row in failure_rows
            ],
            invocation_trend=[
                InvocationTrendPoint(
                    date=row.get("day"),
                    count=int(row.get("invocation_count") or 0),
                )
                for row in trend_rows
            ],
        )

    async def _has_prior_invocation(self, user_id: UUID, agent_id: UUID) -> bool:
        rows = await self.clickhouse.execute_query(
            """
            SELECT count() AS invocation_count
            FROM usage_events
            WHERE user_id = {user_id:UUID} AND agent_id = {agent_id:UUID}
            """,
            {"user_id": user_id, "agent_id": agent_id},
        )
        return int((rows[0] if rows else {}).get("invocation_count") or 0) > 0

    def _rating_response(self, rating: Any) -> RatingResponse:
        return RatingResponse(
            rating_id=rating.id,
            agent_id=rating.agent_id,
            user_id=rating.user_id,
            score=int(rating.score),
            review_text=rating.review_text,
            created_at=rating.created_at,
            updated_at=rating.updated_at,
        )

