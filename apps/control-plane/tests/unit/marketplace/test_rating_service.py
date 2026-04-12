from __future__ import annotations

from datetime import UTC, datetime
from platform.marketplace.exceptions import InvocationRequiredError, VisibilityDeniedError
from platform.marketplace.schemas import RatingCreateRequest
from uuid import uuid4

import pytest
from tests.marketplace_support import (
    ClickHouseClientStub,
    InMemoryMarketplaceRepository,
    RegistryServiceStub,
    build_agent_document,
    build_quality_aggregate,
    build_rating,
    build_rating_service,
    build_search_service,
)


@pytest.mark.asyncio
async def test_rating_service_upsert_creates_updates_and_emits_events() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    agent_id = uuid4()
    clickhouse = ClickHouseClientStub(
        responses=[[{"invocation_count": 1}], [{"invocation_count": 1}]]
    )
    repository = InMemoryMarketplaceRepository()
    search_service = build_search_service(
        repository=repository,
        documents=[build_agent_document(agent_id=agent_id, fqn="finance-ops:rated")],
    )[0]
    (
        service,
        repository,
        _clickhouse,
        _search_service,
        _quality_service,
        _registry,
        producer,
    ) = build_rating_service(
        repository=repository,
        clickhouse=clickhouse,
        search_service=search_service,
    )

    created, created_flag = await service.upsert_rating(
        agent_id,
        user_id,
        RatingCreateRequest(score=4, review_text=" useful "),
        workspace_id=workspace_id,
    )
    updated, updated_flag = await service.upsert_rating(
        agent_id,
        user_id,
        RatingCreateRequest(score=5, review_text=" excellent "),
        workspace_id=workspace_id,
    )

    assert created_flag is True
    assert updated_flag is False
    assert created.score == 4
    assert updated.score == 5
    assert producer.events[0]["event_type"] == "marketplace.rating.created"
    assert producer.events[1]["event_type"] == "marketplace.rating.updated"
    quality = await repository.get_or_create_quality_aggregate(agent_id)
    assert quality.satisfaction_count == 1
    assert quality.satisfaction_avg == 5.0


@pytest.mark.asyncio
async def test_rating_service_list_ratings_and_invocation_gate() -> None:
    agent_id = uuid4()
    user_id = uuid4()
    clickhouse = ClickHouseClientStub(responses=[[{"invocation_count": 0}]])
    repository = InMemoryMarketplaceRepository()
    service = build_rating_service(repository=repository, clickhouse=clickhouse)[0]

    with pytest.raises(InvocationRequiredError):
        await service.upsert_rating(agent_id, user_id, RatingCreateRequest(score=3))

    repository.ratings[(uuid4(), agent_id)] = build_rating(agent_id=agent_id, score=5)
    repository.ratings[(uuid4(), agent_id)] = build_rating(agent_id=agent_id, score=3)
    listed = await service.list_ratings(
        agent_id,
        score_filter=None,
        sort="highest",
        page=1,
        page_size=10,
    )

    assert listed.total == 2
    assert listed.avg_score == 4.0
    assert listed.ratings[0].score == 5


@pytest.mark.asyncio
async def test_rating_service_creator_analytics_requires_owner_and_returns_metrics() -> None:
    requester_id = uuid4()
    outsider_id = uuid4()
    agent_id = uuid4()
    repository = InMemoryMarketplaceRepository(
        quality_by_agent={
            agent_id: build_quality_aggregate(
                agent_id=agent_id,
                satisfaction_sum=build_quality_aggregate().satisfaction_sum,
                satisfaction_count=10,
            )
        }
    )
    clickhouse = ClickHouseClientStub(
        responses=[
            [{"invocation_count_total": 100, "invocation_count_30d": 40}],
            [{"error_type": "timeout", "failure_count": 3}],
            [{"day": datetime.now(UTC).date(), "invocation_count": 4}],
        ]
    )
    registry = RegistryServiceStub(owners_by_agent={agent_id: requester_id})
    search_service = build_search_service(
        repository=repository,
        documents=[build_agent_document(agent_id=agent_id, fqn="finance-ops:creator-agent")],
    )[0]
    service = build_rating_service(
        repository=repository,
        clickhouse=clickhouse,
        search_service=search_service,
        registry_service=registry,
    )[0]

    analytics = await service.get_creator_analytics(agent_id, requester_id)

    assert analytics.agent_fqn == "finance-ops:creator-agent"
    assert analytics.invocation_count_total == 100
    assert analytics.common_failure_patterns[0].error_type == "timeout"
    assert analytics.invocation_trend[0].count == 4

    with pytest.raises(VisibilityDeniedError):
        await service.get_creator_analytics(agent_id, outsider_id)
    with pytest.raises(VisibilityDeniedError):
        await build_rating_service(
            repository=repository,
            clickhouse=clickhouse,
            search_service=build_search_service(repository=repository, documents=[])[0],
            registry_service=registry,
        )[0].get_creator_analytics(agent_id, requester_id)
