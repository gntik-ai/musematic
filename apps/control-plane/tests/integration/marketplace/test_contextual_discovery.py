from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from tests.marketplace_support import (
    QdrantClientStub,
    build_agent_document,
    build_current_user,
    build_marketplace_app,
    build_recommendation_service,
    build_search_service,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("context_type", ["workflow_step", "conversation", "fleet_config"])
async def test_marketplace_contextual_discovery_supports_all_context_types(
    context_type: str,
) -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    visible_agent = uuid4()
    hidden_agent = uuid4()
    qdrant = QdrantClientStub(
        search_results=[
            {"id": str(visible_agent), "score": 0.9, "payload": {"fqn": "finance-ops:visible"}},
            {"id": str(hidden_agent), "score": 0.8, "payload": {"fqn": "secret-ops:hidden"}},
        ]
    )
    search_service = build_search_service(
        documents=[
            build_agent_document(agent_id=visible_agent, fqn="finance-ops:visible"),
            build_agent_document(agent_id=hidden_agent, fqn="secret-ops:hidden"),
        ],
        qdrant=qdrant,
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    recommendation_service = build_recommendation_service(
        qdrant=qdrant,
        search_service=search_service,
    )[0]

    async def _embed_text(_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    recommendation_service._embed_text = _embed_text  # type: ignore[method-assign]
    app = build_marketplace_app(
        current_user=build_current_user(user_id=user_id, workspace_id=workspace_id),
        recommendation_service=recommendation_service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/marketplace/contextual-suggestions",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"context_type": context_type, "context_text": "sentiment analysis"},
        )

    assert response.status_code == 200
    assert response.json()["has_results"] is True
    assert [item["fqn"] for item in response.json()["suggestions"]] == ["finance-ops:visible"]


async def test_marketplace_contextual_discovery_returns_empty_list_for_no_match() -> None:
    workspace_id = uuid4()
    qdrant = QdrantClientStub(search_results=[])
    search_service = build_search_service(
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    recommendation_service = build_recommendation_service(
        qdrant=qdrant,
        search_service=search_service,
    )[0]

    async def _embed_text(_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    recommendation_service._embed_text = _embed_text  # type: ignore[method-assign]
    app = build_marketplace_app(
        current_user=build_current_user(workspace_id=workspace_id),
        recommendation_service=recommendation_service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/marketplace/contextual-suggestions",
            headers={"X-Workspace-ID": str(workspace_id)},
            json={"context_type": "workflow_step", "context_text": "quantum teleportation"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "suggestions": [],
        "has_results": False,
        "context_type": "workflow_step",
    }
