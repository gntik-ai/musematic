from __future__ import annotations

from platform.marketplace.jobs import run_trending_computation
from uuid import uuid4

import httpx
import pytest
from tests.auth_support import RecordingProducer
from tests.marketplace_support import (
    ClickHouseClientStub,
    InMemoryMarketplaceRepository,
    build_agent_document,
    build_current_user,
    build_fake_redis,
    build_marketplace_app,
    build_search_service,
    build_trending_service,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_marketplace_trending_returns_ranked_visible_snapshot() -> None:
    workspace_id = uuid4()
    visible_agent = uuid4()
    hidden_agent = uuid4()
    repository = InMemoryMarketplaceRepository()
    clickhouse = ClickHouseClientStub(
        responses=[
            [
                {
                    "agent_id": visible_agent,
                    "agent_fqn": "finance-ops:fast",
                    "invocations_this_week": 50,
                    "invocations_last_week": 5,
                    "satisfaction_delta": 0.4,
                },
                {
                    "agent_id": hidden_agent,
                    "agent_fqn": "secret-ops:hidden",
                    "invocations_this_week": 60,
                    "invocations_last_week": 6,
                    "satisfaction_delta": 0.1,
                },
            ]
        ]
    )
    _memory, redis_client = build_fake_redis()
    await run_trending_computation(
        repository=repository,
        clickhouse=clickhouse,
        redis_client=redis_client,
        producer=RecordingProducer(),
    )
    search_service = build_search_service(
        repository=repository,
        documents=[
            build_agent_document(agent_id=visible_agent, fqn="finance-ops:fast"),
            build_agent_document(agent_id=hidden_agent, fqn="secret-ops:hidden"),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    trending_service = build_trending_service(
        repository=repository,
        redis_client=redis_client,
        search_service=search_service,
    )[0]
    app = build_marketplace_app(
        current_user=build_current_user(workspace_id=workspace_id),
        trending_service=trending_service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/marketplace/trending",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert response.status_code == 200
    assert [item["agent"]["fqn"] for item in response.json()["agents"]] == ["finance-ops:fast"]
    assert response.json()["agents"][0]["trending_reason"] == "10x more invocations this week"
