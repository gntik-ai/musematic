from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from tests.marketplace_support import (
    ClickHouseClientStub,
    InMemoryMarketplaceRepository,
    RegistryServiceStub,
    build_agent_document,
    build_current_user,
    build_marketplace_app,
    build_quality_aggregate,
    build_rating_service,
    build_search_service,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_marketplace_creator_analytics_enforces_namespace_ownership() -> None:
    workspace_id = uuid4()
    owner_id = uuid4()
    other_user_id = uuid4()
    agent_id = uuid4()
    repository = InMemoryMarketplaceRepository()
    repository.quality_by_agent[agent_id] = build_quality_aggregate(
        agent_id=agent_id,
        satisfaction_sum=4,
        satisfaction_count=1,
    )
    search_service = build_search_service(
        repository=repository,
        documents=[build_agent_document(agent_id=agent_id, fqn="finance-ops:analytics")],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    rating_service = build_rating_service(
        repository=repository,
        clickhouse=ClickHouseClientStub(
            responses=[
                [{"invocation_count_total": 10, "invocation_count_30d": 5}],
                [{"error_type": "timeout", "failure_count": 2}],
                [{"day": "2026-04-10", "invocation_count": 3}],
            ]
        ),
        search_service=search_service,
        registry_service=RegistryServiceStub(owners_by_agent={agent_id: owner_id}),
    )[0]
    owner_app = build_marketplace_app(
        current_user=build_current_user(user_id=owner_id, workspace_id=workspace_id),
        rating_service=rating_service,
    )
    denied_app = build_marketplace_app(
        current_user=build_current_user(user_id=other_user_id, workspace_id=workspace_id),
        rating_service=rating_service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner_app),
        base_url="http://testserver",
    ) as client:
        allowed = await client.get(f"/api/v1/marketplace/analytics/{agent_id}")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=denied_app),
        base_url="http://testserver",
    ) as client:
        denied = await client.get(f"/api/v1/marketplace/analytics/{agent_id}")

    assert allowed.status_code == 200
    assert allowed.json()["invocation_count_total"] == 10
    assert allowed.json()["common_failure_patterns"][0]["error_type"] == "timeout"
    assert denied.status_code == 403

