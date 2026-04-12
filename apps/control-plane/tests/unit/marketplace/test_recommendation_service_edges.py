from __future__ import annotations

from platform.marketplace.schemas import RecommendedAgentEntry
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.marketplace_support import (
    ClickHouseClientStub,
    QdrantClientStub,
    build_agent_document,
    build_recommendation_service,
    build_search_service,
)


@pytest.mark.asyncio
async def test_recommendation_service_prefers_content_based_results_before_fallback() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    first_agent = uuid4()
    second_agent = uuid4()
    search_service = build_search_service(
        documents=[
            build_agent_document(
                agent_id=first_agent,
                fqn="finance-ops:first",
                invocation_count_30d=100,
            ),
            build_agent_document(
                agent_id=second_agent,
                fqn="finance-ops:second",
                invocation_count_30d=90,
            ),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    service = build_recommendation_service(
        clickhouse=ClickHouseClientStub(responses=[[]]),
        search_service=search_service,
    )[0]

    async def _content_based(**kwargs):
        del kwargs
        return [
            {"agent_id": first_agent, "score": 9.0, "reasoning": "similar"},
            {"agent_id": second_agent, "score": 8.0, "reasoning": "backup"},
        ]

    service._get_content_based = _content_based  # type: ignore[method-assign]
    response = await service.get_recommendations(user_id, workspace_id, limit=1)

    assert response.recommendation_type == "personalized"
    assert [entry.agent.fqn for entry in response.recommendations] == ["finance-ops:first"]


@pytest.mark.asyncio
async def test_recommendation_service_fallback_skips_used_agents_and_drops_invalid_entries(
) -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    used_agent = uuid4()
    broken_agent = uuid4()
    good_agent = uuid4()
    search_service = build_search_service(
        documents=[
            build_agent_document(
                agent_id=used_agent,
                fqn="finance-ops:used",
                invocation_count_30d=300,
            ),
            build_agent_document(
                agent_id=broken_agent,
                fqn="finance-ops:broken",
                invocation_count_30d=200,
            ),
            build_agent_document(
                agent_id=good_agent,
                fqn="finance-ops:good",
                invocation_count_30d=100,
            ),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    service = build_recommendation_service(
        clickhouse=ClickHouseClientStub(responses=[[{"agent_id": used_agent}]]),
        search_service=search_service,
    )[0]

    async def _no_content_based(**kwargs):
        del kwargs
        return []

    async def _build_entry(
        *,
        agent_id,
        workspace_id,
        score,
        reasoning,
        recommendation_type,
    ):
        if agent_id == broken_agent:
            return None
        listing = await search_service.get_listing(agent_id, workspace_id)
        return RecommendedAgentEntry(
            agent=listing,
            score=score,
            reasoning=reasoning,
            recommendation_type=recommendation_type,
        )

    service._get_content_based = _no_content_based  # type: ignore[method-assign]
    service._build_recommended_entry = _build_entry  # type: ignore[method-assign]
    response = await service.get_recommendations(user_id, workspace_id, limit=1)

    assert response.recommendation_type == "fallback"
    assert [entry.agent.fqn for entry in response.recommendations] == ["finance-ops:good"]


@pytest.mark.asyncio
async def test_recommendation_service_contextual_and_content_edge_cases(monkeypatch) -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    visible_agent = uuid4()
    hidden_agent = uuid4()
    missing_agent = uuid4()
    qdrant = QdrantClientStub(
        search_results=[
            {"id": str(hidden_agent), "score": 0.9, "payload": {"fqn": "secret-ops:hidden"}},
            {"id": str(missing_agent), "score": 0.8, "payload": {"fqn": "finance-ops:missing"}},
            {"id": str(visible_agent), "score": 0.7, "payload": {"fqn": "finance-ops:visible"}},
        ],
        vectors_by_id={},
        payloads_by_id={},
    )
    search_service = build_search_service(
        documents=[build_agent_document(agent_id=visible_agent, fqn="finance-ops:visible")],
        qdrant=qdrant,
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    service = build_recommendation_service(
        clickhouse=ClickHouseClientStub(responses=[[], [{"agent_id": visible_agent}], []]),
        qdrant=qdrant,
        search_service=search_service,
    )[0]

    async def _embed_text(_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    service._embed_text = _embed_text  # type: ignore[method-assign]
    contextual = await service.get_contextual_suggestions(
        SimpleNamespace(
            context_type="workflow_step",
            context_text="finance routing",
            max_results=5,
        ),
        workspace_id=workspace_id,
        user_id=user_id,
    )
    no_history = await service._get_content_based(
        user_id=user_id,
        workspace_id=workspace_id,
        exclude_agent_ids=set(),
    )
    no_vectors = await service._get_content_based(
        user_id=user_id,
        workspace_id=workspace_id,
        exclude_agent_ids=set(),
    )

    assert [item.fqn for item in contextual.suggestions] == ["finance-ops:visible"]
    assert no_history == []
    assert no_vectors == []

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
        lambda timeout: _Client({"embedding": [0.4, 0.5]}),
    )
    embed_service = build_recommendation_service(
        clickhouse=ClickHouseClientStub(responses=[[]]),
        qdrant=qdrant,
        search_service=search_service,
    )[0]
    assert await embed_service._embed_text("finance") == [0.4, 0.5]

    monkeypatch.setattr(
        "platform.marketplace.recommendation_service.httpx.AsyncClient",
        lambda timeout: _Client({"data": []}),
    )
    with pytest.raises(ValueError, match="Embedding response did not contain a vector"):
        await embed_service._embed_text("finance")

    async def _raise(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("boom")

    search_service.get_listing = _raise  # type: ignore[method-assign]
    assert (
        await service._build_recommended_entry(
            agent_id=visible_agent,
            workspace_id=workspace_id,
            score=1.0,
            reasoning=None,
            recommendation_type="fallback",
        )
        is None
    )
