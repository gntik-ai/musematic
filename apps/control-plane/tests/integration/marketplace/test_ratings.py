from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from tests.marketplace_support import (
    ClickHouseClientStub,
    InMemoryMarketplaceRepository,
    build_agent_document,
    build_current_user,
    build_marketplace_app,
    build_quality_service,
    build_rating_service,
    build_search_service,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_marketplace_ratings_support_create_update_filter_and_invocation_gate() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    agent_id = uuid4()
    repository = InMemoryMarketplaceRepository()
    search_service = build_search_service(
        repository=repository,
        documents=[build_agent_document(agent_id=agent_id, fqn="finance-ops:rated")],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    quality_service = build_quality_service(repository=repository)[0]
    allowed_clickhouse = ClickHouseClientStub(
        responses=[[{"invocation_count": 1}], [{"invocation_count": 1}]]
    )
    denied_clickhouse = ClickHouseClientStub(responses=[[{"invocation_count": 0}]])
    rating_service = build_rating_service(
        repository=repository,
        clickhouse=allowed_clickhouse,
        search_service=search_service,
        quality_service=quality_service,
    )[0]
    denied_service = build_rating_service(
        repository=repository,
        clickhouse=denied_clickhouse,
        search_service=search_service,
        quality_service=quality_service,
    )[0]
    allowed_app = build_marketplace_app(
        current_user=build_current_user(user_id=user_id, workspace_id=workspace_id),
        rating_service=rating_service,
    )
    denied_app = build_marketplace_app(
        current_user=build_current_user(user_id=user_id, workspace_id=workspace_id),
        rating_service=denied_service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=allowed_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            f"/api/v1/marketplace/agents/{agent_id}/ratings",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"score": 5, "review_text": "great"},
        )
        updated = await client.post(
            f"/api/v1/marketplace/agents/{agent_id}/ratings",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"score": 4, "review_text": "updated"},
        )
        await repository.upsert_rating(
            user_id=uuid4(),
            agent_id=agent_id,
            score=5,
            review_text="other",
        )
        await quality_service.update_satisfaction_aggregate(agent_id)
        filtered = await client.get(
            f"/api/v1/marketplace/agents/{agent_id}/ratings",
            params={"score": 5},
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=denied_app),
        base_url="http://testserver",
    ) as client:
        denied = await client.post(
            f"/api/v1/marketplace/agents/{agent_id}/ratings",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"score": 5, "review_text": "blocked"},
        )

    assert created.status_code == 201
    assert updated.status_code == 200
    assert repository.quality_by_agent[agent_id].satisfaction_count == 2
    assert filtered.status_code == 200
    assert [item["score"] for item in filtered.json()["ratings"]] == [5]
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "INVOCATION_REQUIRED"
