from __future__ import annotations

from platform.marketplace.schemas import MarketplaceSearchRequest
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.marketplace_support import (
    OpenSearchClientStub,
    build_agent_document,
    build_search_service,
)


@pytest.mark.asyncio
async def test_search_service_helper_methods_cover_visibility_fetch_and_embedding(
    monkeypatch,
) -> None:
    workspace_id = uuid4()
    visible_agent = uuid4()
    hidden_agent = uuid4()
    opensearch = OpenSearchClientStub(
        handler=lambda index, body: {
            "hits": {
                "hits": [
                    {
                        "_id": str(visible_agent),
                        "_score": 2.0,
                        "_source": {"fqn": "finance-ops:visible"},
                    },
                    {
                        "_id": str(hidden_agent),
                        "_score": 1.0,
                        "_source": {"fqn": "secret-ops:hidden"},
                    },
                    {"_id": None, "_score": 1.0, "_source": {}},
                ]
            }
        }
        if body.get("size") == 50
        else {"hits": {"hits": []}}
    )
    service = build_search_service(
        opensearch=opensearch,
        documents=[
            build_agent_document(agent_id=visible_agent, fqn="finance-ops:visible"),
            build_agent_document(agent_id=hidden_agent, fqn="secret-ops:hidden"),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]

    opensearch_hits = await service._query_opensearch(
        MarketplaceSearchRequest(query="visible"),
        ["finance-ops:*"],
    )
    empty_docs = await service._assemble_listings([])
    fetched = await service._fetch_documents([])
    direct_patterns = await service._get_visibility_patterns(workspace_id)
    wildcard_patterns = await build_search_service()[0]._get_visibility_patterns(workspace_id)

    assert [item["agent_id"] for item in opensearch_hits] == [str(visible_agent)]
    assert empty_docs == []
    assert fetched == {}
    assert direct_patterns == ["finance-ops:*"]
    assert wildcard_patterns == ["*"]
    assert service._matches_facets(
        {
            "tags": ["finance"],
            "capabilities": ["financial_analysis"],
            "maturity_level": 3,
            "trust_tier": "certified",
            "certification_status": "compliant",
            "cost_tier": "metered",
        },
        MarketplaceSearchRequest(
            query="",
            tags=["finance"],
            capabilities=["financial_analysis"],
            maturity_level_min=2,
            maturity_level_max=4,
            trust_tier=["certified"],
            certification_status=["compliant"],
            cost_tier=["metered"],
        ),
    )
    assert service._matches_facets(
        {"tags": ["ops"], "maturity_level": 0},
        MarketplaceSearchRequest(query="", tags=["finance"]),
    ) is False
    assert service._extract_agent_id({"_id": str(visible_agent)}) == visible_agent
    assert service._is_visible("finance-ops:visible", ["finance-ops:*"]) is True
    assert service._is_visible(None, ["finance-ops:*"]) is False

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
        "platform.marketplace.search_service.httpx.AsyncClient",
        lambda timeout: _Client({"vector": [0.1, 0.2]}),
    )
    assert await service._embed_text("visible") == [0.1, 0.2]

    monkeypatch.setattr(
        "platform.marketplace.search_service.httpx.AsyncClient",
        lambda timeout: _Client({"data": [{"embedding": [0.3, 0.4]}]}),
    )
    assert await service._embed_text("visible") == [0.3, 0.4]

    monkeypatch.setattr(
        "platform.marketplace.search_service.httpx.AsyncClient",
        lambda timeout: _Client({"embedding": None}),
    )
    with pytest.raises(ValueError, match="Embedding response did not contain a vector"):
        await service._embed_text("visible")


@pytest.mark.asyncio
async def test_search_service_visibility_resolution_fallback_methods() -> None:
    workspace_id = uuid4()

    class _WorkspaceGrantStub:
        async def get_workspace_visibility_grant(self, workspace_id_arg):
            del workspace_id_arg
            return SimpleNamespace(visibility_agents=["shared:*"])

    class _VisibilityGrantStub:
        async def get_visibility_grant(self, workspace_id_arg):
            del workspace_id_arg
            return None

    service_with_grant = build_search_service()[0]
    service_with_grant.workspaces_service = _WorkspaceGrantStub()
    service_with_none = build_search_service()[0]
    service_with_none.workspaces_service = _VisibilityGrantStub()

    assert await service_with_grant._get_visibility_patterns(workspace_id) == ["shared:*"]
    assert await service_with_none._get_visibility_patterns(workspace_id) == ["*"]
