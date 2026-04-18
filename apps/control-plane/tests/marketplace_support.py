from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from fnmatch import fnmatch
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.marketplace.dependencies import (
    get_quality_service,
    get_rating_service,
    get_recommendation_service,
    get_search_service,
    get_trending_service,
)
from platform.marketplace.models import (
    MarketplaceAgentRating,
    MarketplaceQualityAggregate,
    MarketplaceRecommendation,
    MarketplaceTrendingSnapshot,
)
from platform.marketplace.quality_service import MarketplaceQualityAggregateService
from platform.marketplace.rating_service import MarketplaceRatingService
from platform.marketplace.recommendation_service import MarketplaceRecommendationService
from platform.marketplace.router import router as marketplace_router
from platform.marketplace.search_service import MarketplaceSearchService
from platform.marketplace.trending_service import MarketplaceTrendingService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI

from tests.auth_support import FakeAsyncRedisClient, MemoryRedis, RecordingProducer


def build_marketplace_settings(**overrides: Any) -> PlatformSettings:
    values: dict[str, Any] = {
        "AUTH_JWT_SECRET_KEY": "marketplace-secret",
        "AUTH_JWT_ALGORITHM": "HS256",
        "REGISTRY_EMBEDDING_API_URL": "http://embeddings.test/v1",
        "REGISTRY_SEARCH_INDEX": "marketplace-agents",
        "REGISTRY_EMBEDDINGS_COLLECTION": "agent-embeddings",
        "MEMORY_RRF_K": 60,
    }
    values.update(overrides)
    return PlatformSettings(**values)


def stamp(model: Any, *, created_at: datetime | None = None) -> Any:
    now = created_at or datetime.now(UTC)
    if getattr(model, "id", None) is None:
        model.id = uuid4()
    if getattr(model, "created_at", None) is None:
        model.created_at = now
    if getattr(model, "updated_at", None) is None:
        model.updated_at = now
    return model


def build_agent_document(
    *,
    agent_id: UUID | None = None,
    fqn: str = "finance-ops:report-analyzer",
    name: str = "Report Analyzer",
    description: str = "Analyze financial reports and statements.",
    capabilities: list[str] | None = None,
    tags: list[str] | None = None,
    maturity_level: int = 3,
    trust_tier: str = "certified",
    certification_status: str = "compliant",
    cost_tier: str = "metered",
    invocation_count_30d: int = 100,
) -> dict[str, Any]:
    resolved_agent_id = agent_id or uuid4()
    return {
        "_id": str(resolved_agent_id),
        "agent_profile_id": str(resolved_agent_id),
        "fqn": fqn,
        "display_name": name,
        "name": name,
        "description": description,
        "purpose": description,
        "capabilities": list(capabilities or ["financial_analysis"]),
        "role_types": list(capabilities or ["financial_analysis"]),
        "tags": list(tags or ["finance"]),
        "maturity_level": maturity_level,
        "trust_tier": trust_tier,
        "certification_status": certification_status,
        "cost_tier": cost_tier,
        "invocation_count_30d": invocation_count_30d,
    }


def build_quality_aggregate(
    *,
    agent_id: UUID | None = None,
    has_data: bool = True,
    execution_count: int = 100,
    success_count: int = 95,
    failure_count: int = 5,
    self_correction_count: int = 10,
    quality_score_sum: Decimal = Decimal("8000"),
    quality_score_count: int = 100,
    satisfaction_sum: Decimal = Decimal("43"),
    satisfaction_count: int = 10,
    certification_status: str = "compliant",
    updated_at: datetime | None = None,
    source_unavailable_since: datetime | None = None,
) -> MarketplaceQualityAggregate:
    aggregate = MarketplaceQualityAggregate(
        agent_id=agent_id or uuid4(),
        has_data=has_data,
        execution_count=execution_count,
        success_count=success_count,
        failure_count=failure_count,
        self_correction_count=self_correction_count,
        quality_score_sum=quality_score_sum,
        quality_score_count=quality_score_count,
        satisfaction_sum=satisfaction_sum,
        satisfaction_count=satisfaction_count,
        certification_status=certification_status,
        data_source_last_updated_at=updated_at,
        source_unavailable_since=source_unavailable_since,
    )
    return stamp(aggregate)


def build_rating(
    *,
    rating_id: UUID | None = None,
    agent_id: UUID | None = None,
    user_id: UUID | None = None,
    score: int = 4,
    review_text: str | None = "Helpful on finance tasks.",
) -> MarketplaceAgentRating:
    rating = MarketplaceAgentRating(
        id=rating_id or uuid4(),
        agent_id=agent_id or uuid4(),
        user_id=user_id or uuid4(),
        score=score,
        review_text=review_text,
    )
    return stamp(rating)


def build_trending_snapshot(
    *,
    snapshot_id: UUID | None = None,
    snapshot_date: date | None = None,
    agent_id: UUID | None = None,
    agent_fqn: str = "finance-ops:report-analyzer",
    trending_score: Decimal = Decimal("10"),
    growth_rate: Decimal = Decimal("10"),
    invocations_this_week: int = 10,
    invocations_last_week: int = 1,
    trending_reason: str = "10x more invocations this week",
    satisfaction_delta: Decimal | None = Decimal("0.4"),
    rank: int = 1,
) -> MarketplaceTrendingSnapshot:
    snapshot = MarketplaceTrendingSnapshot(
        id=snapshot_id or uuid4(),
        snapshot_date=snapshot_date or datetime.now(UTC).date(),
        agent_id=agent_id or uuid4(),
        agent_fqn=agent_fqn,
        trending_score=trending_score,
        growth_rate=growth_rate,
        invocations_this_week=invocations_this_week,
        invocations_last_week=invocations_last_week,
        trending_reason=trending_reason,
        satisfaction_delta=satisfaction_delta,
        rank=rank,
    )
    return stamp(snapshot)


class OpenSearchClientStub:
    def __init__(
        self,
        documents: list[dict[str, Any]] | None = None,
        *,
        handler: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
        | Callable[[str, dict[str, Any]], dict[str, Any]]
        | None = None,
    ) -> None:
        self.documents = [dict(document) for document in documents or []]
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    async def _ensure_client(self) -> OpenSearchClientStub:
        return self

    async def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"index": index, "body": body})
        if self.handler is not None:
            result = self.handler(index, body)
            if hasattr(result, "__await__"):
                return await result
            return result

        query = body.get("query", {})
        if "terms" in query and "agent_profile_id" in query["terms"]:
            agent_ids = {str(item) for item in query["terms"]["agent_profile_id"]}
            docs = [
                {"_id": document["agent_profile_id"], "_source": dict(document)}
                for document in self.documents
                if str(document["agent_profile_id"]) in agent_ids
            ]
            return {"hits": {"hits": docs}}

        docs = [dict(document) for document in self.documents]
        docs = [document for document in docs if _matches_query(document, query)]
        docs = _apply_sort(docs, body.get("sort") or [])
        size = int(body.get("size") or len(docs))
        return {
            "hits": {
                "hits": [
                    {
                        "_id": document["agent_profile_id"],
                        "_score": _keyword_score(document, query),
                        "_source": document,
                    }
                    for document in docs[:size]
                ]
            }
        }


class QdrantPointStub:
    def __init__(self, *, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self.id = point_id
        self.vector = vector
        self.payload = payload


class QdrantClientStub:
    def __init__(
        self,
        *,
        search_results: list[dict[str, Any]] | None = None,
        handler: Callable[[str, list[float], int, Any | None], list[dict[str, Any]]] | None = None,
        vectors_by_id: dict[str, list[float]] | None = None,
        payloads_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.search_results = [dict(item) for item in search_results or []]
        self.handler = handler
        self.vectors_by_id = dict(vectors_by_id or {})
        self.payloads_by_id = dict(payloads_by_id or {})
        self.search_calls: list[dict[str, Any]] = []
        self.retrieve_calls: list[dict[str, Any]] = []

    async def search_vectors(
        self,
        collection: str,
        query_vector: list[float],
        limit: int,
        query_filter: Any | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        resolved_filter = kwargs.get("filter", query_filter)
        self.search_calls.append(
            {
                "collection": collection,
                "query_vector": list(query_vector),
                "limit": limit,
                "filter": resolved_filter,
            }
        )
        if self.handler is not None:
            return self.handler(collection, query_vector, limit, resolved_filter)[:limit]
        return self.search_results[:limit]

    async def _ensure_client(self) -> QdrantClientStub:
        return self

    async def retrieve(
        self,
        *,
        collection_name: str,
        ids: list[str],
        with_vectors: bool,
        with_payload: bool,
    ) -> list[QdrantPointStub]:
        self.retrieve_calls.append(
            {
                "collection_name": collection_name,
                "ids": list(ids),
                "with_vectors": with_vectors,
                "with_payload": with_payload,
            }
        )
        return [
            QdrantPointStub(
                point_id=point_id,
                vector=list(self.vectors_by_id.get(point_id, [])),
                payload=dict(self.payloads_by_id.get(point_id, {})),
            )
            for point_id in ids
        ]


class ClickHouseClientStub:
    def __init__(
        self,
        *,
        handler: Callable[[str, dict[str, Any] | None], list[dict[str, Any]]] | None = None,
        responses: list[list[dict[str, Any]]] | None = None,
    ) -> None:
        self.handler = handler
        self.responses = [list(item) for item in responses or []]
        self.calls: list[dict[str, Any]] = []

    async def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append({"sql": sql, "params": params})
        if self.handler is not None:
            return self.handler(sql, params)
        if self.responses:
            return self.responses.pop(0)
        return []


@dataclass
class WorkspacesServiceStub:
    visibility_by_workspace: dict[UUID, list[str]] = field(default_factory=dict)

    async def get_visibility_config(self, workspace_id: UUID) -> SimpleNamespace:
        return SimpleNamespace(
            visibility_agents=list(self.visibility_by_workspace.get(workspace_id, ["*"])),
            visibility_tools=[],
        )


@dataclass
class RegistryServiceStub:
    owners_by_agent: dict[UUID, UUID] = field(default_factory=dict)
    visibility_by_agent: dict[UUID, tuple[list[str], list[str]]] = field(default_factory=dict)

    async def get_agent_namespace_owner(self, agent_id: UUID) -> UUID | None:
        return self.owners_by_agent.get(agent_id)

    async def resolve_effective_visibility(
        self,
        agent_id: UUID,
        workspace_id: UUID,
    ) -> SimpleNamespace:
        del workspace_id
        agent_patterns, tool_patterns = self.visibility_by_agent.get(agent_id, ([], []))
        return SimpleNamespace(
            agent_patterns=list(agent_patterns),
            tool_patterns=list(tool_patterns),
        )


@dataclass
class InMemoryMarketplaceRepository:
    ratings: dict[tuple[UUID, UUID], MarketplaceAgentRating] = field(default_factory=dict)
    quality_by_agent: dict[UUID, MarketplaceQualityAggregate] = field(default_factory=dict)
    recommendations_by_user: dict[UUID, list[MarketplaceRecommendation]] = field(
        default_factory=dict
    )
    trending_by_date: dict[date, list[MarketplaceTrendingSnapshot]] = field(default_factory=dict)

    async def upsert_rating(
        self,
        *,
        user_id: UUID,
        agent_id: UUID,
        score: int,
        review_text: str | None,
    ) -> tuple[MarketplaceAgentRating, bool]:
        key = (user_id, agent_id)
        existing = self.ratings.get(key)
        if existing is None:
            created = build_rating(
                user_id=user_id,
                agent_id=agent_id,
                score=score,
                review_text=review_text,
            )
            self.ratings[key] = created
            return created, True
        existing.score = score
        existing.review_text = review_text
        existing.updated_at = datetime.now(UTC)
        return existing, False

    async def get_or_create_quality_aggregate(
        self,
        agent_id: UUID,
    ) -> MarketplaceQualityAggregate:
        if agent_id not in self.quality_by_agent:
            self.quality_by_agent[agent_id] = build_quality_aggregate(
                agent_id=agent_id,
                has_data=False,
                execution_count=0,
                success_count=0,
                failure_count=0,
                self_correction_count=0,
                quality_score_sum=Decimal("0"),
                quality_score_count=0,
                satisfaction_sum=Decimal("0"),
                satisfaction_count=0,
                certification_status="uncertified",
                updated_at=None,
            )
        return self.quality_by_agent[agent_id]

    async def get_quality_aggregate(
        self,
        agent_id: UUID,
    ) -> MarketplaceQualityAggregate | None:
        return self.quality_by_agent.get(agent_id)

    async def get_quality_aggregates(
        self,
        agent_ids: list[UUID],
    ) -> dict[UUID, MarketplaceQualityAggregate]:
        return {
            agent_id: aggregate
            for agent_id, aggregate in self.quality_by_agent.items()
            if agent_id in set(agent_ids)
        }

    async def update_quality_aggregate(
        self,
        aggregate: MarketplaceQualityAggregate,
        **fields: Any,
    ) -> MarketplaceQualityAggregate:
        for key, value in fields.items():
            setattr(aggregate, key, value)
        aggregate.updated_at = datetime.now(UTC)
        self.quality_by_agent[aggregate.agent_id] = aggregate
        return aggregate

    async def bulk_replace_recommendations(
        self,
        *,
        user_id: UUID,
        recommendations: list[dict[str, Any]],
    ) -> list[MarketplaceRecommendation]:
        rows: list[MarketplaceRecommendation] = []
        for recommendation in recommendations:
            row = MarketplaceRecommendation(
                id=uuid4(),
                user_id=user_id,
                agent_id=recommendation["agent_id"],
                agent_fqn=recommendation["agent_fqn"],
                recommendation_type=str(recommendation["recommendation_type"]),
                score=Decimal(str(recommendation["score"])),
                reasoning=recommendation.get("reasoning"),
                expires_at=recommendation["expires_at"],
            )
            rows.append(stamp(row))
        self.recommendations_by_user[user_id] = rows
        return rows

    async def get_recommendations_for_user(
        self,
        user_id: UUID,
        *,
        now: datetime | None = None,
    ) -> list[MarketplaceRecommendation]:
        cutoff = now or datetime.now(UTC)
        rows = self.recommendations_by_user.get(user_id, [])
        return [row for row in rows if row.expires_at > cutoff]

    async def insert_trending_snapshot(
        self,
        *,
        snapshot_date: date,
        entries: list[dict[str, Any]],
    ) -> list[MarketplaceTrendingSnapshot]:
        rows: list[MarketplaceTrendingSnapshot] = []
        for entry in entries:
            rows.append(
                build_trending_snapshot(
                    snapshot_date=snapshot_date,
                    agent_id=entry["agent_id"],
                    agent_fqn=entry["agent_fqn"],
                    trending_score=Decimal(str(entry["trending_score"])),
                    growth_rate=Decimal(str(entry["growth_rate"])),
                    invocations_this_week=int(entry["invocations_this_week"]),
                    invocations_last_week=int(entry["invocations_last_week"]),
                    trending_reason=str(entry["trending_reason"]),
                    satisfaction_delta=(
                        Decimal(str(entry["satisfaction_delta"]))
                        if entry.get("satisfaction_delta") is not None
                        else None
                    ),
                    rank=int(entry["rank"]),
                )
            )
        self.trending_by_date[snapshot_date] = rows
        return rows

    async def get_latest_trending_snapshot(
        self,
        *,
        limit: int = 20,
    ) -> tuple[date | None, list[MarketplaceTrendingSnapshot]]:
        if not self.trending_by_date:
            return None, []
        latest_date = max(self.trending_by_date)
        return latest_date, list(self.trending_by_date[latest_date][:limit])

    async def get_ratings_for_agent(
        self,
        agent_id: UUID,
        *,
        score_filter: int | None = None,
        sort: str = "recent",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MarketplaceAgentRating], int, float | None]:
        rows = [row for row in self.ratings.values() if row.agent_id == agent_id]
        if score_filter is not None:
            rows = [row for row in rows if row.score == score_filter]
        if sort == "highest":
            rows.sort(key=lambda item: (-item.score, item.updated_at), reverse=False)
        elif sort == "lowest":
            rows.sort(key=lambda item: (item.score, -item.updated_at.timestamp()))
        else:
            rows.sort(key=lambda item: item.updated_at, reverse=True)
        total = len(rows)
        avg_score = (
            sum(row.score for row in rows) / len(rows)
            if rows
            else None
        )
        start = (page - 1) * page_size
        end = start + page_size
        return rows[start:end], total, avg_score

    async def get_rating_summary(self, agent_id: UUID) -> dict[str, float | int | None]:
        rows = [row for row in self.ratings.values() if row.agent_id == agent_id]
        avg_score = (
            sum(row.score for row in rows) / len(rows)
            if rows
            else None
        )
        return {"avg_score": avg_score, "review_count": len(rows)}

    async def get_rating_summaries(
        self,
        agent_ids: list[UUID],
    ) -> dict[UUID, dict[str, float | int | None]]:
        return {
            agent_id: await self.get_rating_summary(agent_id)
            for agent_id in agent_ids
        }

    async def get_rating_totals(self, agent_id: UUID) -> tuple[float, int]:
        rows = [row for row in self.ratings.values() if row.agent_id == agent_id]
        return float(sum(row.score for row in rows)), len(rows)


def build_search_service(
    *,
    repository: InMemoryMarketplaceRepository | None = None,
    documents: list[dict[str, Any]] | None = None,
    qdrant_results: list[dict[str, Any]] | None = None,
    visibility_by_workspace: dict[UUID, list[str]] | None = None,
    settings: PlatformSettings | None = None,
    opensearch: OpenSearchClientStub | None = None,
    qdrant: QdrantClientStub | None = None,
    registry_service: RegistryServiceStub | None = None,
) -> tuple[
    MarketplaceSearchService,
    InMemoryMarketplaceRepository,
    OpenSearchClientStub,
    QdrantClientStub,
    WorkspacesServiceStub,
]:
    resolved_repository = repository or InMemoryMarketplaceRepository()
    resolved_opensearch = opensearch or OpenSearchClientStub(documents or [])
    resolved_qdrant = qdrant or QdrantClientStub(search_results=qdrant_results or [])
    resolved_workspaces = WorkspacesServiceStub(visibility_by_workspace or {})
    resolved_registry = registry_service or RegistryServiceStub()
    service = MarketplaceSearchService(
        repository=resolved_repository,
        settings=settings or build_marketplace_settings(),
        opensearch=resolved_opensearch,
        qdrant=resolved_qdrant,
        workspaces_service=resolved_workspaces,
        registry_service=resolved_registry,
    )
    return (
        service,
        resolved_repository,
        resolved_opensearch,
        resolved_qdrant,
        resolved_workspaces,
    )


def build_quality_service(
    *,
    repository: InMemoryMarketplaceRepository | None = None,
    producer: RecordingProducer | None = None,
    settings: PlatformSettings | None = None,
) -> tuple[MarketplaceQualityAggregateService, InMemoryMarketplaceRepository, RecordingProducer]:
    resolved_repository = repository or InMemoryMarketplaceRepository()
    resolved_producer = producer or RecordingProducer()
    service = MarketplaceQualityAggregateService(
        repository=resolved_repository,
        settings=settings or build_marketplace_settings(),
        producer=resolved_producer,
    )
    return service, resolved_repository, resolved_producer


def build_rating_service(
    *,
    repository: InMemoryMarketplaceRepository | None = None,
    clickhouse: ClickHouseClientStub | None = None,
    search_service: MarketplaceSearchService | None = None,
    quality_service: MarketplaceQualityAggregateService | None = None,
    registry_service: RegistryServiceStub | None = None,
    producer: RecordingProducer | None = None,
    settings: PlatformSettings | None = None,
) -> tuple[
    MarketplaceRatingService,
    InMemoryMarketplaceRepository,
    ClickHouseClientStub,
    MarketplaceSearchService,
    MarketplaceQualityAggregateService,
    RegistryServiceStub,
    RecordingProducer,
]:
    resolved_repository = repository or InMemoryMarketplaceRepository()
    resolved_settings = settings or build_marketplace_settings()
    resolved_search = search_service or build_search_service(
        repository=resolved_repository,
        settings=resolved_settings,
    )[0]
    resolved_quality = quality_service or build_quality_service(
        repository=resolved_repository,
        settings=resolved_settings,
    )[0]
    resolved_clickhouse = clickhouse or ClickHouseClientStub()
    resolved_registry = registry_service or RegistryServiceStub()
    resolved_producer = producer or RecordingProducer()
    service = MarketplaceRatingService(
        repository=resolved_repository,
        settings=resolved_settings,
        producer=resolved_producer,
        clickhouse=resolved_clickhouse,
        search_service=resolved_search,
        quality_service=resolved_quality,
        registry_service=resolved_registry,
    )
    return (
        service,
        resolved_repository,
        resolved_clickhouse,
        resolved_search,
        resolved_quality,
        resolved_registry,
        resolved_producer,
    )


def build_recommendation_service(
    *,
    repository: InMemoryMarketplaceRepository | None = None,
    clickhouse: ClickHouseClientStub | None = None,
    qdrant: QdrantClientStub | None = None,
    search_service: MarketplaceSearchService | None = None,
    visibility_by_workspace: dict[UUID, list[str]] | None = None,
    redis_client: FakeAsyncRedisClient | None = None,
    settings: PlatformSettings | None = None,
) -> tuple[
    MarketplaceRecommendationService,
    InMemoryMarketplaceRepository,
    ClickHouseClientStub,
    QdrantClientStub,
    FakeAsyncRedisClient,
    MarketplaceSearchService,
]:
    resolved_repository = repository or InMemoryMarketplaceRepository()
    resolved_settings = settings or build_marketplace_settings()
    resolved_search = search_service or build_search_service(
        repository=resolved_repository,
        visibility_by_workspace=visibility_by_workspace,
        settings=resolved_settings,
    )[0]
    resolved_clickhouse = clickhouse or ClickHouseClientStub()
    resolved_qdrant = qdrant or QdrantClientStub()
    resolved_redis = redis_client or FakeAsyncRedisClient()
    service = MarketplaceRecommendationService(
        repository=resolved_repository,
        settings=resolved_settings,
        clickhouse=resolved_clickhouse,
        qdrant=resolved_qdrant,
        redis_client=resolved_redis,
        search_service=resolved_search,
        workspaces_service=WorkspacesServiceStub(visibility_by_workspace or {}),
    )
    return (
        service,
        resolved_repository,
        resolved_clickhouse,
        resolved_qdrant,
        resolved_redis,
        resolved_search,
    )


def build_trending_service(
    *,
    repository: InMemoryMarketplaceRepository | None = None,
    redis_client: FakeAsyncRedisClient | None = None,
    search_service: MarketplaceSearchService | None = None,
) -> tuple[
    MarketplaceTrendingService,
    InMemoryMarketplaceRepository,
    FakeAsyncRedisClient,
    MarketplaceSearchService,
]:
    resolved_repository = repository or InMemoryMarketplaceRepository()
    resolved_search = search_service or build_search_service(repository=resolved_repository)[0]
    resolved_redis = redis_client or FakeAsyncRedisClient()
    service = MarketplaceTrendingService(
        repository=resolved_repository,
        redis_client=resolved_redis,
        search_service=resolved_search,
    )
    return service, resolved_repository, resolved_redis, resolved_search


def build_marketplace_app(
    *,
    current_user: dict[str, Any] | None = None,
    search_service: MarketplaceSearchService | None = None,
    quality_service: MarketplaceQualityAggregateService | None = None,
    rating_service: MarketplaceRatingService | None = None,
    recommendation_service: MarketplaceRecommendationService | None = None,
    trending_service: MarketplaceTrendingService | None = None,
    settings: PlatformSettings | None = None,
) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings or build_marketplace_settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(marketplace_router)

    async def _current_user() -> dict[str, Any]:
        return current_user or {"sub": str(uuid4()), "workspace_id": str(uuid4())}

    app.dependency_overrides[get_current_user] = _current_user
    if search_service is not None:
        async def _search_service() -> MarketplaceSearchService:
            return search_service

        app.dependency_overrides[get_search_service] = _search_service
    if quality_service is not None:
        async def _quality_service() -> MarketplaceQualityAggregateService:
            return quality_service

        app.dependency_overrides[get_quality_service] = _quality_service
    if rating_service is not None:
        async def _rating_service() -> MarketplaceRatingService:
            return rating_service

        app.dependency_overrides[get_rating_service] = _rating_service
    if recommendation_service is not None:
        async def _recommendation_service() -> MarketplaceRecommendationService:
            return recommendation_service

        app.dependency_overrides[get_recommendation_service] = _recommendation_service
    if trending_service is not None:
        async def _trending_service() -> MarketplaceTrendingService:
            return trending_service

        app.dependency_overrides[get_trending_service] = _trending_service
    return app


def build_current_user(
    *,
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
) -> dict[str, str]:
    return {
        "sub": str(user_id or uuid4()),
        "workspace_id": str(workspace_id or uuid4()),
    }


def build_fake_redis() -> tuple[MemoryRedis, FakeAsyncRedisClient]:
    memory = MemoryRedis()
    return memory, FakeAsyncRedisClient(memory)


def _matches_query(document: dict[str, Any], query: dict[str, Any]) -> bool:
    if "bool" not in query:
        return True
    payload = query["bool"]
    must = payload.get("must", [])
    filters = payload.get("filter", [])
    for item in must:
        if "match_all" in item:
            continue
        multi_match = item.get("multi_match")
        if multi_match is None:
            continue
        value = str(multi_match.get("query") or "").lower()
        if value and value not in _document_text(document):
            return False
    return all(_matches_filter(document, filter_item) for filter_item in filters)


def _matches_filter(document: dict[str, Any], filter_item: dict[str, Any]) -> bool:
    if "terms" in filter_item:
        field, values = next(iter(filter_item["terms"].items()))
        field_value = document.get(field)
        if isinstance(field_value, list):
            return bool(set(field_value).intersection(set(values)))
        return field_value in set(values)
    if "range" in filter_item:
        field, bounds = next(iter(filter_item["range"].items()))
        value = document.get(field)
        if value is None:
            return False
        if "gte" in bounds and value < bounds["gte"]:
            return False
        if "lte" in bounds and value > bounds["lte"]:
            return False
        return True
    if "bool" in filter_item:
        should = filter_item["bool"].get("should", [])
        minimum = int(filter_item["bool"].get("minimum_should_match") or 1)
        matches = 0
        for item in should:
            wildcard = item.get("wildcard", {})
            field, payload = next(iter(wildcard.items()))
            value = str(document.get(field) or "")
            pattern = str(payload.get("value") or "")
            if fnmatch(value, pattern):
                matches += 1
        return matches >= minimum
    return True


def _apply_sort(
    documents: list[dict[str, Any]],
    sort_spec: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not sort_spec:
        return sorted(
            documents,
            key=lambda item: (
                -_keyword_score(item, {"bool": {"must": [{"match_all": {}}]}}),
                item["fqn"],
            ),
        )

    def _sort_value(item: dict[str, Any], field: str, order: str) -> Any:
        field_name = field.replace(".keyword", "")
        value = item.get(field_name)
        if order == "desc" and isinstance(value, (int, float)):
            return -value
        return value

    return sorted(
        documents,
        key=lambda item: tuple(
            _sort_value(item, next(iter(spec)), next(iter(spec.values()))["order"])
            for spec in sort_spec
        ),
    )


def _keyword_score(document: dict[str, Any], query: dict[str, Any]) -> float:
    if "bool" not in query:
        return 0.0
    must = query["bool"].get("must", [])
    search_terms: list[str] = []
    for item in must:
        multi_match = item.get("multi_match")
        if multi_match is None:
            continue
        search_terms.extend(re.findall(r"\w+", str(multi_match.get("query") or "").lower()))
    if not search_terms:
        return float(document.get("invocation_count_30d") or 0.0)
    text = _document_text(document)
    return float(sum(1 for term in search_terms if term in text))


def _document_text(document: dict[str, Any]) -> str:
    values = [
        str(document.get("display_name") or ""),
        str(document.get("name") or ""),
        str(document.get("description") or ""),
        str(document.get("purpose") or ""),
        " ".join(str(item) for item in document.get("capabilities") or []),
        " ".join(str(item) for item in document.get("tags") or []),
        str(document.get("fqn") or ""),
    ]
    return " ".join(values).lower()
