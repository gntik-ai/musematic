from __future__ import annotations

import json
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.marketplace.exceptions import MarketplaceError
from platform.marketplace.models import RecommendationType
from platform.marketplace.repository import MarketplaceRepository
from platform.marketplace.schemas import (
    ContextualSuggestionRequest,
    ContextualSuggestionResponse,
    MarketplaceSearchRequest,
    RecommendationResponse,
    RecommendedAgentEntry,
)
from platform.marketplace.search_service import MarketplaceSearchService
from statistics import fmean
from typing import Any
from uuid import UUID

import httpx


class MarketplaceRecommendationService:
    def __init__(
        self,
        *,
        repository: MarketplaceRepository,
        settings: PlatformSettings,
        clickhouse: AsyncClickHouseClient,
        qdrant: AsyncQdrantClient,
        redis_client: AsyncRedisClient,
        search_service: MarketplaceSearchService,
        workspaces_service: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.clickhouse = clickhouse
        self.qdrant = qdrant
        self.redis_client = redis_client
        self.search_service = search_service
        self.workspaces_service = workspaces_service

    async def get_recommendations(
        self,
        user_id: UUID,
        workspace_id: UUID,
        *,
        limit: int = 10,
    ) -> RecommendationResponse:
        used_agent_ids = await self._get_used_agent_ids(user_id)
        collaborative = [
            row
            for row in await self.repository.get_recommendations_for_user(user_id)
            if row.agent_id not in used_agent_ids
        ]
        entries: list[RecommendedAgentEntry] = []
        for row in collaborative[:limit]:
            entry = await self._build_recommended_entry(
                agent_id=row.agent_id,
                workspace_id=workspace_id,
                score=float(row.score),
                reasoning=row.reasoning,
                recommendation_type=row.recommendation_type,
            )
            if entry is not None:
                entries.append(entry)
        if len(entries) < min(limit, 2):
            content_rows = await self._get_content_based(
                user_id=user_id,
                workspace_id=workspace_id,
                exclude_agent_ids={*used_agent_ids, *(entry.agent.agent_id for entry in entries)},
            )
            for content_row in content_rows:
                entry = await self._build_recommended_entry(
                    agent_id=content_row["agent_id"],
                    workspace_id=workspace_id,
                    score=content_row["score"],
                    reasoning=content_row.get("reasoning"),
                    recommendation_type=RecommendationType.content_based.value,
                )
                if entry is not None:
                    entries.append(entry)
                if len(entries) >= limit:
                    break
        recommendation_type = "personalized"
        if len(entries) < min(limit, 2):
            fallback_docs, _ = await self.search_service._browse_documents(
                self.search_service_request(),
                await self.search_service._get_visibility_patterns(workspace_id),
            )
            for doc in fallback_docs:
                agent_id = self.search_service._extract_agent_id(doc)
                if agent_id in used_agent_ids or any(
                    item.agent.agent_id == agent_id for item in entries
                ):
                    continue
                entry = await self._build_recommended_entry(
                    agent_id=agent_id,
                    workspace_id=workspace_id,
                    score=float(doc.get("invocation_count_30d") or 0.0),
                    reasoning="Popular in your workspace visibility scope.",
                    recommendation_type=RecommendationType.popularity_fallback.value,
                )
                if entry is not None:
                    entries.append(entry)
                if len(entries) >= limit:
                    break
            recommendation_type = "fallback"
        return RecommendationResponse(
            recommendations=entries[:limit],
            recommendation_type=recommendation_type,
        )

    async def get_contextual_suggestions(
        self,
        request: ContextualSuggestionRequest,
        *,
        workspace_id: UUID,
        user_id: UUID,
    ) -> ContextualSuggestionResponse:
        del user_id
        if request.context_type not in {"workflow_step", "conversation", "fleet_config"}:
            raise MarketplaceError(
                "MARKETPLACE_CONTEXT_TYPE_INVALID",
                "Unknown marketplace context type.",
                {"context_type": request.context_type},
            )
        vector = await self._embed_text(request.context_text)
        visibility_patterns = await self.search_service._get_visibility_patterns(workspace_id)
        rows = await self.qdrant.search_vectors(
            self.settings.registry.embeddings_collection,
            query_vector=vector,
            limit=request.max_results,
            filter=None,
        )
        suggestions = []
        for row in rows:
            payload = row.get("payload", {})
            if not self.search_service._is_visible(payload.get("fqn"), visibility_patterns):
                continue
            document = await self.search_service._fetch_document(UUID(str(row["id"])))
            if document is None:
                continue
            suggestions.append(await self.search_service._assemble_listing(document))
        return ContextualSuggestionResponse(
            suggestions=suggestions,
            has_results=bool(suggestions),
            context_type=request.context_type,
        )

    async def _get_content_based(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        exclude_agent_ids: set[UUID],
    ) -> list[dict[str, Any]]:
        cache_key = f"rec:content:{user_id}"
        cached = await self.redis_client.get(cache_key)
        if cached is not None:
            decoded = json.loads(cached.decode("utf-8"))
            return [
                {
                    "agent_id": UUID(item["agent_id"]),
                    "score": float(item["score"]),
                    "reasoning": item.get("reasoning"),
                }
                for item in decoded
                if UUID(item["agent_id"]) not in exclude_agent_ids
            ]
        history_rows = await self.clickhouse.execute_query(
            """
            SELECT agent_id
            FROM usage_events
            WHERE user_id = {user_id:UUID}
            GROUP BY agent_id
            ORDER BY max(timestamp) DESC
            LIMIT 10
            """,
            {"user_id": user_id},
        )
        point_ids = [str(row["agent_id"]) for row in history_rows if row.get("agent_id")]
        if not point_ids:
            return []
        raw_client = await self.qdrant._ensure_client()
        retrieved = await raw_client.retrieve(
            collection_name=self.settings.registry.embeddings_collection,
            ids=point_ids,
            with_vectors=True,
            with_payload=True,
        )
        vectors = [list(item.vector) for item in retrieved if getattr(item, "vector", None)]
        if not vectors:
            return []
        centroid = [fmean(values) for values in zip(*vectors, strict=False)]
        visibility_patterns = await self.search_service._get_visibility_patterns(workspace_id)
        results = await self.qdrant.search_vectors(
            self.settings.registry.embeddings_collection,
            query_vector=centroid,
            limit=10,
            filter=None,
        )
        filtered: list[dict[str, Any]] = []
        for row in results:
            agent_id = UUID(str(row["id"]))
            if agent_id in exclude_agent_ids:
                continue
            payload = row.get("payload", {})
            if not self.search_service._is_visible(payload.get("fqn"), visibility_patterns):
                continue
            filtered.append(
                {
                    "agent_id": agent_id,
                    "score": float(row.get("score") or 0.0),
                    "reasoning": "Similar to agents you used recently.",
                }
            )
        await self.redis_client.set(
            cache_key,
            json.dumps(
                [
                    {
                        "agent_id": str(item["agent_id"]),
                        "score": item["score"],
                        "reasoning": item.get("reasoning"),
                    }
                    for item in filtered
                ]
            ).encode("utf-8"),
            ttl=6 * 60 * 60,
        )
        return filtered

    async def _get_used_agent_ids(self, user_id: UUID) -> set[UUID]:
        rows = await self.clickhouse.execute_query(
            """
            SELECT DISTINCT agent_id
            FROM usage_events
            WHERE user_id = {user_id:UUID}
            """,
            {"user_id": user_id},
        )
        return {UUID(str(row["agent_id"])) for row in rows if row.get("agent_id")}

    async def _embed_text(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.settings.registry.embedding_api_url,
                json={"input": text},
            )
            response.raise_for_status()
            payload = response.json()
        vector = payload.get("embedding")
        if isinstance(vector, list):
            return [float(item) for item in vector]
        data = payload.get("data")
        if isinstance(data, list) and data:
            embedding = data[0].get("embedding")
            if isinstance(embedding, list):
                return [float(item) for item in embedding]
        raise ValueError("Embedding response did not contain a vector.")

    async def _build_recommended_entry(
        self,
        *,
        agent_id: UUID,
        workspace_id: UUID,
        score: float,
        reasoning: str | None,
        recommendation_type: str,
    ) -> RecommendedAgentEntry | None:
        try:
            listing = await self.search_service.get_listing(agent_id, workspace_id)
        except Exception:
            return None
        return RecommendedAgentEntry(
            agent=listing,
            score=score,
            reasoning=reasoning,
            recommendation_type=recommendation_type,
        )

    @staticmethod
    def search_service_request() -> MarketplaceSearchRequest:
        return MarketplaceSearchRequest(query="", page=1, page_size=20)
