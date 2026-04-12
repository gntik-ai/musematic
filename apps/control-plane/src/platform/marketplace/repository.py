from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from platform.marketplace.models import (
    MarketplaceAgentRating,
    MarketplaceQualityAggregate,
    MarketplaceRecommendation,
    MarketplaceTrendingSnapshot,
)
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class MarketplaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_rating(
        self,
        *,
        user_id: UUID,
        agent_id: UUID,
        score: int,
        review_text: str | None,
    ) -> tuple[MarketplaceAgentRating, bool]:
        existing = await self._get_rating(user_id=user_id, agent_id=agent_id)
        if existing is None:
            rating = MarketplaceAgentRating(
                user_id=user_id,
                agent_id=agent_id,
                score=score,
                review_text=review_text,
            )
            self.session.add(rating)
            await self.session.flush()
            return rating, True

        existing.score = score
        existing.review_text = review_text
        await self.session.flush()
        return existing, False

    async def get_or_create_quality_aggregate(
        self,
        agent_id: UUID,
    ) -> MarketplaceQualityAggregate:
        aggregate = await self.get_quality_aggregate(agent_id)
        if aggregate is not None:
            return aggregate
        aggregate = MarketplaceQualityAggregate(agent_id=agent_id, has_data=False)
        self.session.add(aggregate)
        await self.session.flush()
        return aggregate

    async def get_quality_aggregate(
        self,
        agent_id: UUID,
    ) -> MarketplaceQualityAggregate | None:
        result = await self.session.execute(
            select(MarketplaceQualityAggregate).where(
                MarketplaceQualityAggregate.agent_id == agent_id
            )
        )
        return result.scalar_one_or_none()

    async def get_quality_aggregates(
        self,
        agent_ids: Sequence[UUID],
    ) -> dict[UUID, MarketplaceQualityAggregate]:
        if not agent_ids:
            return {}
        result = await self.session.execute(
            select(MarketplaceQualityAggregate).where(
                MarketplaceQualityAggregate.agent_id.in_(list(agent_ids))
            )
        )
        items = list(result.scalars().all())
        return {item.agent_id: item for item in items}

    async def update_quality_aggregate(
        self,
        aggregate: MarketplaceQualityAggregate,
        **fields: Any,
    ) -> MarketplaceQualityAggregate:
        for key, value in fields.items():
            setattr(aggregate, key, value)
        await self.session.flush()
        return aggregate

    async def bulk_replace_recommendations(
        self,
        *,
        user_id: UUID,
        recommendations: list[dict[str, Any]],
    ) -> list[MarketplaceRecommendation]:
        await self.session.execute(
            delete(MarketplaceRecommendation).where(MarketplaceRecommendation.user_id == user_id)
        )
        rows = [
            MarketplaceRecommendation(
                user_id=user_id,
                agent_id=row["agent_id"],
                agent_fqn=row["agent_fqn"],
                recommendation_type=row["recommendation_type"],
                score=row["score"],
                reasoning=row.get("reasoning"),
                expires_at=row["expires_at"],
            )
            for row in recommendations
        ]
        self.session.add_all(rows)
        await self.session.flush()
        return rows

    async def get_recommendations_for_user(
        self,
        user_id: UUID,
        *,
        now: datetime | None = None,
    ) -> list[MarketplaceRecommendation]:
        cutoff = now or datetime.now(UTC)
        result = await self.session.execute(
            select(MarketplaceRecommendation)
            .where(
                MarketplaceRecommendation.user_id == user_id,
                MarketplaceRecommendation.expires_at > cutoff,
            )
            .order_by(
                MarketplaceRecommendation.score.desc(),
                MarketplaceRecommendation.updated_at.desc(),
            )
        )
        return list(result.scalars().all())

    async def insert_trending_snapshot(
        self,
        *,
        snapshot_date: date,
        entries: list[dict[str, Any]],
    ) -> list[MarketplaceTrendingSnapshot]:
        await self.session.execute(
            delete(MarketplaceTrendingSnapshot).where(
                MarketplaceTrendingSnapshot.snapshot_date == snapshot_date
            )
        )
        rows = [
            MarketplaceTrendingSnapshot(
                snapshot_date=snapshot_date,
                agent_id=entry["agent_id"],
                agent_fqn=entry["agent_fqn"],
                trending_score=entry["trending_score"],
                growth_rate=entry["growth_rate"],
                invocations_this_week=entry["invocations_this_week"],
                invocations_last_week=entry["invocations_last_week"],
                trending_reason=entry["trending_reason"],
                satisfaction_delta=entry.get("satisfaction_delta"),
                rank=entry["rank"],
            )
            for entry in entries
        ]
        self.session.add_all(rows)
        await self.session.flush()
        return rows

    async def get_latest_trending_snapshot(
        self,
        *,
        limit: int = 20,
    ) -> tuple[date | None, list[MarketplaceTrendingSnapshot]]:
        snapshot_date = await self.session.scalar(
            select(func.max(MarketplaceTrendingSnapshot.snapshot_date))
        )
        if snapshot_date is None:
            return None, []
        result = await self.session.execute(
            select(MarketplaceTrendingSnapshot)
            .where(MarketplaceTrendingSnapshot.snapshot_date == snapshot_date)
            .order_by(MarketplaceTrendingSnapshot.rank.asc())
            .limit(limit)
        )
        return snapshot_date, list(result.scalars().all())

    async def get_ratings_for_agent(
        self,
        agent_id: UUID,
        *,
        score_filter: int | None = None,
        sort: str = "recent",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MarketplaceAgentRating], int, float | None]:
        filters = [MarketplaceAgentRating.agent_id == agent_id]
        if score_filter is not None:
            filters.append(MarketplaceAgentRating.score == score_filter)
        total = await self.session.scalar(
            select(func.count())
            .select_from(MarketplaceAgentRating)
            .where(*filters)
        )
        avg_score = await self.session.scalar(
            select(func.avg(MarketplaceAgentRating.score))
            .where(MarketplaceAgentRating.agent_id == agent_id)
        )
        query = select(MarketplaceAgentRating).where(*filters)
        if sort == "highest":
            query = query.order_by(
                MarketplaceAgentRating.score.desc(),
                MarketplaceAgentRating.updated_at.desc(),
            )
        elif sort == "lowest":
            query = query.order_by(
                MarketplaceAgentRating.score.asc(),
                MarketplaceAgentRating.updated_at.desc(),
            )
        else:
            query = query.order_by(MarketplaceAgentRating.updated_at.desc())
        result = await self.session.execute(
            query.offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0), _maybe_float(avg_score)

    async def get_rating_summary(self, agent_id: UUID) -> dict[str, float | int | None]:
        avg_score = await self.session.scalar(
            select(func.avg(MarketplaceAgentRating.score)).where(
                MarketplaceAgentRating.agent_id == agent_id
            )
        )
        count = await self.session.scalar(
            select(func.count())
            .select_from(MarketplaceAgentRating)
            .where(MarketplaceAgentRating.agent_id == agent_id)
        )
        return {
            "avg_score": _maybe_float(avg_score),
            "review_count": int(count or 0),
        }

    async def get_rating_summaries(
        self,
        agent_ids: Sequence[UUID],
    ) -> dict[UUID, dict[str, float | int | None]]:
        if not agent_ids:
            return {}
        result = await self.session.execute(
            select(
                MarketplaceAgentRating.agent_id,
                func.avg(MarketplaceAgentRating.score),
                func.count(),
            )
            .where(MarketplaceAgentRating.agent_id.in_(list(agent_ids)))
            .group_by(MarketplaceAgentRating.agent_id)
        )
        summaries: dict[UUID, dict[str, float | int | None]] = {}
        for agent_id, avg_score, review_count in result.all():
            summaries[agent_id] = {
                "avg_score": _maybe_float(avg_score),
                "review_count": int(review_count or 0),
            }
        return summaries

    async def get_rating_totals(self, agent_id: UUID) -> tuple[float, int]:
        result = await self.session.execute(
            select(
                func.coalesce(func.sum(MarketplaceAgentRating.score), 0),
                func.count(),
            ).where(MarketplaceAgentRating.agent_id == agent_id)
        )
        total_score, count = result.one()
        return float(total_score or 0), int(count or 0)

    async def _get_rating(
        self,
        *,
        user_id: UUID,
        agent_id: UUID,
    ) -> MarketplaceAgentRating | None:
        result = await self.session.execute(
            select(MarketplaceAgentRating).where(
                MarketplaceAgentRating.user_id == user_id,
                MarketplaceAgentRating.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
