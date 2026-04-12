from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from tests.marketplace_support import (
    build_agent_document,
    build_current_user,
    build_marketplace_app,
    build_quality_aggregate,
    build_rating,
    build_search_service,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_marketplace_search_supports_keyword_semantic_visibility_and_browse() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    keyword_agent = uuid4()
    semantic_agent = uuid4()
    hidden_agent = uuid4()
    service, repository, _opensearch, qdrant, _workspaces = build_search_service(
        documents=[
            build_agent_document(
                agent_id=keyword_agent,
                fqn="finance-ops:keyword",
                description="Analyze financial reports and statements.",
                capabilities=["financial_analysis"],
                maturity_level=3,
                invocation_count_30d=50,
            ),
            build_agent_document(
                agent_id=semantic_agent,
                fqn="finance-ops:semantic",
                description="Handles reconciliations and finance routing.",
                capabilities=["reconciliation"],
                maturity_level=2,
                invocation_count_30d=20,
            ),
            build_agent_document(
                agent_id=hidden_agent,
                fqn="secret-ops:hidden",
                description="Hidden semantic result.",
                maturity_level=5,
                invocation_count_30d=999,
            ),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )
    repository.quality_by_agent[keyword_agent] = build_quality_aggregate(agent_id=keyword_agent)
    repository.ratings[(uuid4(), keyword_agent)] = build_rating(agent_id=keyword_agent, score=5)
    qdrant.search_results = [
        {"id": str(semantic_agent), "score": 0.9, "payload": {"fqn": "finance-ops:semantic"}},
        {"id": str(hidden_agent), "score": 0.8, "payload": {"fqn": "secret-ops:hidden"}},
    ]

    async def _embed_text(_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    service._embed_text = _embed_text  # type: ignore[method-assign]
    app = build_marketplace_app(
        current_user=build_current_user(user_id=user_id, workspace_id=workspace_id),
        search_service=service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        searched = await client.post(
            "/api/v1/marketplace/search",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"query": "analyze financial reports"},
        )
        filtered = await client.post(
            "/api/v1/marketplace/search",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"query": "", "maturity_level_min": 3},
        )
        browsed = await client.post(
            "/api/v1/marketplace/search",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"query": ""},
        )

    assert searched.status_code == 200
    assert {item["fqn"] for item in searched.json()["results"]} == {
        "finance-ops:keyword",
        "finance-ops:semantic",
    }
    assert all(item["fqn"] != "secret-ops:hidden" for item in searched.json()["results"])
    assert [item["fqn"] for item in filtered.json()["results"]] == ["finance-ops:keyword"]
    assert browsed.json()["results"][0]["fqn"] == "finance-ops:keyword"
