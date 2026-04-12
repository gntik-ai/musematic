from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.marketplace.jobs import run_trending_computation
from uuid import uuid4

import pytest
from tests.auth_support import RecordingProducer
from tests.marketplace_support import (
    ClickHouseClientStub,
    InMemoryMarketplaceRepository,
    build_agent_document,
    build_fake_redis,
    build_search_service,
    build_trending_service,
    build_trending_snapshot,
)


@pytest.mark.asyncio
async def test_run_trending_computation_filters_threshold_ranks_and_caches() -> None:
    agent_fast = uuid4()
    agent_flat = uuid4()
    agent_low = uuid4()
    repository = InMemoryMarketplaceRepository()
    clickhouse = ClickHouseClientStub(
        responses=[
            [
                {
                    "agent_id": agent_fast,
                    "agent_fqn": "finance-ops:fast",
                    "invocations_this_week": 10,
                    "invocations_last_week": 1,
                    "satisfaction_delta": 0.4,
                },
                {
                    "agent_id": agent_flat,
                    "agent_fqn": "finance-ops:flat",
                    "invocations_this_week": 8,
                    "invocations_last_week": 8,
                    "satisfaction_delta": 0.1,
                },
                {
                    "agent_id": agent_low,
                    "agent_fqn": "finance-ops:low",
                    "invocations_this_week": 4,
                    "invocations_last_week": 1,
                    "satisfaction_delta": 0.9,
                },
            ]
        ]
    )
    memory, redis_client = build_fake_redis()
    producer = RecordingProducer()

    await run_trending_computation(
        repository=repository,
        clickhouse=clickhouse,
        redis_client=redis_client,
        producer=producer,
    )

    snapshot_date = max(repository.trending_by_date)
    ranked = repository.trending_by_date[snapshot_date]
    cached = json.loads(memory.strings["marketplace:trending:latest"].decode("utf-8"))

    assert [item.agent_fqn for item in ranked] == ["finance-ops:fast", "finance-ops:flat"]
    assert ranked[0].rank == 1
    assert ranked[0].trending_reason == "10x more invocations this week"
    assert cached["agents"][0]["agent_fqn"] == "finance-ops:fast"
    assert producer.events[0]["event_type"] == "marketplace.trending.updated"


@pytest.mark.asyncio
async def test_trending_service_prefers_cache_and_applies_visibility_filter() -> None:
    workspace_id = uuid4()
    visible_agent = uuid4()
    hidden_agent = uuid4()
    memory, redis_client = build_fake_redis()
    redis_payload = {
        "snapshot_date": datetime.now(UTC).date().isoformat(),
        "agents": [
            {
                "rank": 1,
                "agent_id": str(visible_agent),
                "agent_fqn": "finance-ops:visible",
                "trending_score": 9.0,
                "growth_rate": 9.0,
                "invocations_this_week": 9,
                "invocations_last_week": 1,
                "trending_reason": "9x more invocations this week",
                "satisfaction_delta": 0.5,
            },
            {
                "rank": 2,
                "agent_id": str(hidden_agent),
                "agent_fqn": "secret-ops:hidden",
                "trending_score": 8.0,
                "growth_rate": 8.0,
                "invocations_this_week": 8,
                "invocations_last_week": 1,
                "trending_reason": "8x more invocations this week",
                "satisfaction_delta": None,
            },
        ],
    }
    memory.strings["marketplace:trending:latest"] = json.dumps(redis_payload).encode("utf-8")
    search_service = build_search_service(
        documents=[
            build_agent_document(
                agent_id=visible_agent,
                fqn="finance-ops:visible",
                name="Visible Agent",
            ),
            build_agent_document(
                agent_id=hidden_agent,
                fqn="secret-ops:hidden",
                name="Hidden Agent",
            ),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    service = build_trending_service(
        repository=InMemoryMarketplaceRepository(),
        redis_client=redis_client,
        search_service=search_service,
    )[0]

    response = await service.get_trending(workspace_id, limit=10)

    assert response.total == 1
    assert response.agents[0].agent.fqn == "finance-ops:visible"
    assert response.snapshot_date == datetime.now(UTC).date()


@pytest.mark.asyncio
async def test_trending_service_falls_back_to_repository_snapshot() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    expected_snapshot = datetime.now(UTC).date()
    repository = InMemoryMarketplaceRepository(
        trending_by_date={
            expected_snapshot: [
                build_trending_snapshot(
                    snapshot_date=expected_snapshot,
                    agent_id=agent_id,
                    agent_fqn="finance-ops:fallback",
                )
            ]
        }
    )
    search_service = build_search_service(
        documents=[
            build_agent_document(
                agent_id=agent_id,
                fqn="finance-ops:fallback",
                name="Fallback Agent",
            )
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    service = build_trending_service(repository=repository, search_service=search_service)[0]

    response = await service.get_trending(workspace_id)

    assert response.total == 1
    assert response.agents[0].agent.name == "Fallback Agent"
