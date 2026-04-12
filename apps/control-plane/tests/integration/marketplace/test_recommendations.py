from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from tests.marketplace_support import (
    ClickHouseClientStub,
    InMemoryMarketplaceRepository,
    build_agent_document,
    build_current_user,
    build_marketplace_app,
    build_recommendation_service,
    build_search_service,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_marketplace_recommendations_support_personalized_and_fallback_modes() -> None:
    workspace_id = uuid4()
    personalized_user = uuid4()
    new_user = uuid4()
    recommended_agent = uuid4()
    fallback_agent = uuid4()
    repository = InMemoryMarketplaceRepository()
    await repository.bulk_replace_recommendations(
        user_id=personalized_user,
        recommendations=[
            {
                "agent_id": recommended_agent,
                "agent_fqn": "finance-ops:recommended",
                "recommendation_type": "collaborative",
                "score": 9.5,
                "reasoning": "Similar users invoked this agent.",
                "expires_at": datetime.now(UTC) + timedelta(hours=6),
            }
        ],
    )
    search_service = build_search_service(
        repository=repository,
        documents=[
            build_agent_document(agent_id=recommended_agent, fqn="finance-ops:recommended"),
            build_agent_document(
                agent_id=fallback_agent,
                fqn="finance-ops:fallback",
                invocation_count_30d=999,
            ),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]

    personalized_service = build_recommendation_service(
        repository=repository,
        clickhouse=ClickHouseClientStub(responses=[[]]),
        search_service=search_service,
    )[0]
    fallback_service = build_recommendation_service(
        repository=repository,
        clickhouse=ClickHouseClientStub(responses=[[]]),
        search_service=search_service,
    )[0]

    async def _no_content_based(**kwargs):
        del kwargs
        return []

    personalized_service._get_content_based = _no_content_based  # type: ignore[method-assign]
    fallback_service._get_content_based = _no_content_based  # type: ignore[method-assign]

    personalized_app = build_marketplace_app(
        current_user=build_current_user(
            user_id=personalized_user,
            workspace_id=workspace_id,
        ),
        recommendation_service=personalized_service,
    )
    fallback_app = build_marketplace_app(
        current_user=build_current_user(user_id=new_user, workspace_id=workspace_id),
        recommendation_service=fallback_service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=personalized_app),
        base_url="http://testserver",
    ) as personalized_client:
        personalized = await personalized_client.get(
            "/api/v1/marketplace/recommendations",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fallback_app),
        base_url="http://testserver",
    ) as fallback_client:
        fallback = await fallback_client.get(
            "/api/v1/marketplace/recommendations",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert personalized.status_code == 200
    assert personalized.json()["recommendations"][0]["agent"]["fqn"] == "finance-ops:recommended"
    assert fallback.status_code == 200
    assert fallback.json()["recommendation_type"] == "fallback"
    assert fallback.json()["recommendations"][0]["agent"]["fqn"] == "finance-ops:fallback"

