from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.marketplace.exceptions import MarketplaceError
from platform.marketplace.models import RecommendationType
from platform.marketplace.schemas import ContextualSuggestionRequest
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.marketplace_support import (
    ClickHouseClientStub,
    InMemoryMarketplaceRepository,
    QdrantClientStub,
    build_agent_document,
    build_fake_redis,
    build_recommendation_service,
    build_search_service,
)


@pytest.mark.asyncio
async def test_recommendation_service_returns_personalized_and_fallback_results() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    recommended_agent = uuid4()
    fallback_agent = uuid4()
    repository = InMemoryMarketplaceRepository()
    await repository.bulk_replace_recommendations(
        user_id=user_id,
        recommendations=[
            {
                "agent_id": recommended_agent,
                "agent_fqn": "finance-ops:tax-optimizer",
                "recommendation_type": RecommendationType.collaborative.value,
                "score": 9.2,
                "reasoning": "Similar users also invoked this agent.",
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            }
        ],
    )
    search_service = build_search_service(
        repository=repository,
        documents=[
            build_agent_document(agent_id=recommended_agent, fqn="finance-ops:tax-optimizer"),
            build_agent_document(
                agent_id=fallback_agent,
                fqn="finance-ops:popular",
                invocation_count_30d=999,
            ),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    clickhouse = ClickHouseClientStub(responses=[[], []])
    service = build_recommendation_service(
        repository=repository,
        clickhouse=clickhouse,
        search_service=search_service,
    )[0]

    async def _no_content_based(**kwargs):
        del kwargs
        return []

    service._get_content_based = _no_content_based  # type: ignore[method-assign]
    personalized = await service.get_recommendations(user_id, workspace_id, limit=5)

    assert personalized.recommendation_type == "fallback"
    assert [entry.agent.fqn for entry in personalized.recommendations] == [
        "finance-ops:tax-optimizer",
        "finance-ops:popular",
    ]


@pytest.mark.asyncio
async def test_recommendation_service_content_based_path_caches_and_filters_visibility() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    used_agent = uuid4()
    visible_agent = uuid4()
    hidden_agent = uuid4()
    memory, redis_client = build_fake_redis()
    qdrant = QdrantClientStub(
        search_results=[
            {
                "id": str(visible_agent),
                "score": 0.9,
                "payload": {"fqn": "finance-ops:visible"},
            },
            {
                "id": str(hidden_agent),
                "score": 0.8,
                "payload": {"fqn": "secret-ops:hidden"},
            },
        ],
        vectors_by_id={str(used_agent): [1.0, 2.0, 3.0]},
        payloads_by_id={str(used_agent): {"fqn": "finance-ops:used"}},
    )
    clickhouse = ClickHouseClientStub(
        responses=[[{"agent_id": used_agent}], [{"agent_id": used_agent}]]
    )
    search_service = build_search_service(
        documents=[
            build_agent_document(agent_id=visible_agent, fqn="finance-ops:visible"),
            build_agent_document(agent_id=hidden_agent, fqn="secret-ops:hidden"),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    service = build_recommendation_service(
        clickhouse=clickhouse,
        qdrant=qdrant,
        redis_client=redis_client,
        search_service=search_service,
    )[0]

    content_rows = await service._get_content_based(
        user_id=user_id,
        workspace_id=workspace_id,
        exclude_agent_ids={used_agent},
    )
    cached_rows = await service._get_content_based(
        user_id=user_id,
        workspace_id=workspace_id,
        exclude_agent_ids={used_agent},
    )

    assert content_rows == cached_rows
    assert [item["agent_id"] for item in content_rows] == [visible_agent]
    cached = json.loads(memory.strings[f"rec:content:{user_id}"].decode("utf-8"))
    assert cached[0]["agent_id"] == str(visible_agent)


@pytest.mark.asyncio
async def test_recommendation_service_contextual_suggestions_and_embed_helpers(monkeypatch) -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    visible_agent = uuid4()
    missing_agent = uuid4()
    qdrant = QdrantClientStub(
        search_results=[
            {
                "id": str(visible_agent),
                "score": 0.8,
                "payload": {"fqn": "finance-ops:visible"},
            },
            {
                "id": str(missing_agent),
                "score": 0.7,
                "payload": {"fqn": "finance-ops:missing"},
            },
        ]
    )
    search_service = build_search_service(
        documents=[build_agent_document(agent_id=visible_agent, fqn="finance-ops:visible")],
        qdrant=qdrant,
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    service = build_recommendation_service(qdrant=qdrant, search_service=search_service)[0]

    async def _embed_text(_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    service._embed_text = _embed_text  # type: ignore[method-assign]
    response = await service.get_contextual_suggestions(
        ContextualSuggestionRequest(
            context_type="workflow_step",
            context_text="route finance approvals",
            max_results=5,
        ),
        workspace_id=workspace_id,
        user_id=user_id,
    )

    assert response.has_results is True
    assert [item.fqn for item in response.suggestions] == ["finance-ops:visible"]

    with pytest.raises(MarketplaceError):
        await service.get_contextual_suggestions(
            SimpleNamespace(
                context_type="unknown",
                context_text="bad",
                max_results=5,
            ),
            workspace_id=workspace_id,
            user_id=user_id,
        )

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, payload):
            self.payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def post(self, url: str, json: dict[str, object]):
            del url, json
            return _Response(self.payload)

    monkeypatch.setattr(
        "platform.marketplace.recommendation_service.httpx.AsyncClient",
        lambda timeout: _Client({"data": [{"embedding": [0.4, 0.5]}]}),
    )
    embed_service = build_recommendation_service(qdrant=qdrant, search_service=search_service)[0]
    assert await embed_service._embed_text("finance") == [0.4, 0.5]
