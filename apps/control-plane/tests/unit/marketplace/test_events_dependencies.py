from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.registry import event_registry
from platform.marketplace.dependencies import (
    build_quality_service,
    build_rating_service,
    build_recommendation_service,
    build_search_service,
    build_trending_service,
    get_quality_service,
    get_rating_service,
    get_recommendation_service,
    get_search_service,
    get_trending_service,
)
from platform.marketplace.events import (
    MarketplaceEventType,
    emit_rating_created,
    emit_rating_updated,
    emit_trending_updated,
    register_marketplace_event_types,
)
from platform.marketplace.schemas import (
    ContextualSuggestionRequest,
    MarketplaceSearchRequest,
    RatingCreateRequest,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from tests.auth_support import RecordingProducer
from tests.marketplace_support import (
    ClickHouseClientStub,
    FakeAsyncRedisClient,
    InMemoryMarketplaceRepository,
    OpenSearchClientStub,
    QdrantClientStub,
    RegistryServiceStub,
    WorkspacesServiceStub,
    build_marketplace_settings,
)


@pytest.mark.asyncio
async def test_marketplace_events_register_and_emit_payloads() -> None:
    producer = RecordingProducer()
    agent_id = uuid4()
    user_id = uuid4()
    register_marketplace_event_types()

    await emit_rating_created(producer, agent_id=agent_id, user_id=user_id, score=4)
    await emit_rating_updated(producer, agent_id=agent_id, user_id=user_id, score=5)
    await emit_trending_updated(
        producer,
        snapshot_date=datetime.now(UTC).date(),
        top_agent_fqns=["finance-ops:agent"],
    )

    assert event_registry.is_registered(MarketplaceEventType.rating_created.value) is True
    assert [event["event_type"] for event in producer.events] == [
        MarketplaceEventType.rating_created.value,
        MarketplaceEventType.rating_updated.value,
        MarketplaceEventType.trending_updated.value,
    ]


@pytest.mark.asyncio
async def test_marketplace_dependency_builders_and_getters_return_services() -> None:
    settings = build_marketplace_settings()
    session = object()
    opensearch = OpenSearchClientStub()
    qdrant = QdrantClientStub()
    clickhouse = ClickHouseClientStub()
    redis_client = FakeAsyncRedisClient()
    workspaces = WorkspacesServiceStub()
    registry = RegistryServiceStub()
    repository = InMemoryMarketplaceRepository()
    producer = RecordingProducer()

    search_service = build_search_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        opensearch=opensearch,  # type: ignore[arg-type]
        qdrant=qdrant,  # type: ignore[arg-type]
        workspaces_service=workspaces,  # type: ignore[arg-type]
    )
    quality_service = build_quality_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        producer=producer,  # type: ignore[arg-type]
    )
    rating_service = build_rating_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        producer=producer,  # type: ignore[arg-type]
        clickhouse=clickhouse,  # type: ignore[arg-type]
        search_service=search_service,
        quality_service=quality_service,
        registry_service=registry,  # type: ignore[arg-type]
    )
    recommendation_service = build_recommendation_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        clickhouse=clickhouse,  # type: ignore[arg-type]
        qdrant=qdrant,  # type: ignore[arg-type]
        redis_client=redis_client,  # type: ignore[arg-type]
        search_service=search_service,
        workspaces_service=workspaces,  # type: ignore[arg-type]
    )
    trending_service = build_trending_service(
        session=session,  # type: ignore[arg-type]
        redis_client=redis_client,  # type: ignore[arg-type]
        search_service=search_service,
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={
                    "kafka": producer,
                    "opensearch": opensearch,
                    "qdrant": qdrant,
                    "clickhouse": clickhouse,
                    "redis": redis_client,
                },
            )
        )
    )

    assert search_service.repository.__class__.__name__ == "MarketplaceRepository"
    assert quality_service.repository.__class__.__name__ == "MarketplaceRepository"
    assert rating_service.registry_service is registry
    assert recommendation_service.redis_client is redis_client
    assert trending_service.redis_client is redis_client

    got_search = await get_search_service(request, session=session, workspaces_service=workspaces)
    got_quality = await get_quality_service(request, session=session)
    got_rating = await get_rating_service(
        request,
        session=session,
        workspaces_service=workspaces,
        registry_service=registry,
    )
    got_recommendation = await get_recommendation_service(
        request,
        session=session,
        workspaces_service=workspaces,
    )
    got_trending = await get_trending_service(
        request,
        session=session,
        workspaces_service=workspaces,
    )

    assert got_search.opensearch is opensearch
    assert got_quality.producer is producer
    assert got_rating.registry_service is registry
    assert got_recommendation.qdrant is qdrant
    assert got_trending.redis_client is redis_client
    del repository


def test_marketplace_schemas_normalize_inputs_and_validate_context() -> None:
    request = MarketplaceSearchRequest(query=" finance ")
    rating = RatingCreateRequest(score=5, review_text=" great ")
    suggestion = ContextualSuggestionRequest(
        context_type="workflow_step",
        context_text="  route approvals  ",
    )

    assert request.query == "finance"
    assert rating.review_text == "great"
    assert suggestion.context_text == "route approvals"

    with pytest.raises(ValidationError, match="context_text"):
        ContextualSuggestionRequest(context_type="workflow_step", context_text=" ")
