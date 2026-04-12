from __future__ import annotations

import json
from platform.common.clients.redis import AsyncRedisClient
from platform.marketplace.repository import MarketplaceRepository
from platform.marketplace.schemas import TrendingAgentEntry, TrendingAgentsResponse
from platform.marketplace.search_service import MarketplaceSearchService
from uuid import UUID


class MarketplaceTrendingService:
    def __init__(
        self,
        *,
        repository: MarketplaceRepository,
        redis_client: AsyncRedisClient,
        search_service: MarketplaceSearchService,
    ) -> None:
        self.repository = repository
        self.redis_client = redis_client
        self.search_service = search_service

    async def get_trending(
        self,
        workspace_id: UUID,
        *,
        limit: int = 20,
    ) -> TrendingAgentsResponse:
        cached = await self.redis_client.get("marketplace:trending:latest")
        if cached is not None:
            payload = json.loads(cached.decode("utf-8"))
            cached_agents: list[TrendingAgentEntry] = []
            for item in payload.get("agents", [])[:limit]:
                try:
                    listing = await self.search_service.get_listing(
                        UUID(item["agent_id"]),
                        workspace_id,
                    )
                except Exception:
                    continue
                cached_agents.append(
                    TrendingAgentEntry(
                        rank=int(item["rank"]),
                        agent=listing,
                        trending_score=float(item["trending_score"]),
                        growth_rate=float(item["growth_rate"]),
                        invocations_this_week=int(item["invocations_this_week"]),
                        invocations_last_week=int(item["invocations_last_week"]),
                        trending_reason=str(item["trending_reason"]),
                        satisfaction_delta=(
                            float(item["satisfaction_delta"])
                            if item.get("satisfaction_delta") is not None
                            else None
                        ),
                    )
                )
            return TrendingAgentsResponse(
                agents=cached_agents,
                snapshot_date=payload.get("snapshot_date"),
                total=len(cached_agents),
            )
        snapshot_date, rows = await self.repository.get_latest_trending_snapshot(limit=limit)
        response_agents: list[TrendingAgentEntry] = []
        for row in rows:
            try:
                listing = await self.search_service.get_listing(row.agent_id, workspace_id)
            except Exception:
                continue
            response_agents.append(
                TrendingAgentEntry(
                    rank=row.rank,
                    agent=listing,
                    trending_score=float(row.trending_score),
                    growth_rate=float(row.growth_rate),
                    invocations_this_week=row.invocations_this_week,
                    invocations_last_week=row.invocations_last_week,
                    trending_reason=row.trending_reason,
                    satisfaction_delta=(
                        float(row.satisfaction_delta)
                        if row.satisfaction_delta is not None
                        else None
                    ),
                )
            )
        return TrendingAgentsResponse(
            agents=response_agents,
            snapshot_date=snapshot_date,
            total=len(response_agents),
        )
