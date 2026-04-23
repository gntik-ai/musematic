from __future__ import annotations

from platform.marketplace.exceptions import VisibilityDeniedError
from platform.marketplace.schemas import MarketplaceSearchRequest
from platform.registry.models import LifecycleStatus
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from tests.marketplace_support import (
    OpenSearchClientStub,
    build_agent_document,
    build_quality_aggregate,
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
async def test_search_service_falls_back_when_semantic_search_is_unavailable() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    service = build_search_service(
        documents=[build_agent_document(agent_id=agent_id, fqn="finance-ops:visible")],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]

    async def _embed_text(_text: str) -> list[float]:
        raise httpx.ConnectError("embedding service unavailable")

    service._embed_text = _embed_text  # type: ignore[method-assign]

    response = await service.search(
        MarketplaceSearchRequest(query="visible", page=1, page_size=10),
        workspace_id,
        uuid4(),
    )

    assert [item.fqn for item in response.results] == ["finance-ops:visible"]
    assert response.total == 1


@pytest.mark.asyncio
async def test_search_service_uses_registry_fallback_for_query_results_when_index_is_stale(
) -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    service, repository, _opensearch, _qdrant, _workspaces = build_search_service(
        documents=[],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )
    service.registry_service.profiles_by_agent[agent_id] = SimpleNamespace(
        id=agent_id,
        workspace_id=workspace_id,
        fqn="finance-ops:registry-search-fallback",
        display_name="KYC Verifier",
        purpose="KYC verification agent for marketplace fallback coverage.",
        approach="Deterministic verification workflow.",
        role_types=["financial_analysis"],
        tags=["kyc", "verification"],
        maturity_level=2,
        status=LifecycleStatus.published,
    )
    repository.quality_by_agent[agent_id] = build_quality_aggregate(agent_id=agent_id)

    response = await service.search(
        MarketplaceSearchRequest(query="KYC verification", page=1, page_size=10),
        workspace_id,
        uuid4(),
    )

    assert [item.fqn for item in response.results] == ["finance-ops:registry-search-fallback"]
    assert response.total == 1


@pytest.mark.asyncio
async def test_search_service_falls_back_to_registry_profile_when_index_document_is_missing(
) -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    registry_service = SimpleNamespace(
        get_agent=lambda workspace_id_arg, agent_id_arg, requesting_agent_id=None: _get_agent(
            workspace_id_arg,
            agent_id_arg,
            requesting_agent_id,
        )
    )

    async def _get_agent(workspace_id_arg, agent_id_arg, requesting_agent_id):
        del workspace_id_arg, requesting_agent_id
        if agent_id_arg != agent_id:
            return None
        return SimpleNamespace(
            id=agent_id,
            fqn="finance-ops:registry-fallback",
            display_name="Registry Fallback",
            purpose="Registry-backed listing used when the marketplace index is stale.",
            role_types=["financial_analysis"],
            tags=["finance"],
            maturity_level=2,
            status=LifecycleStatus.published,
        )

    service, repository, _opensearch, _qdrant, _workspaces = build_search_service(
        documents=[],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )
    service.registry_service = registry_service
    repository.quality_by_agent[agent_id] = build_quality_aggregate(agent_id=agent_id)

    listing = await service.get_listing(agent_id, workspace_id)

    assert listing.agent_id == agent_id
    assert listing.fqn == "finance-ops:registry-fallback"
    assert listing.name == "Registry Fallback"


@pytest.mark.asyncio
async def test_search_service_returns_visibility_denied_when_global_registry_fallback_is_hidden(
) -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    service, repository, _opensearch, _qdrant, _workspaces = build_search_service(
        documents=[],
        visibility_by_workspace={workspace_id: ["shadow:*"]},
    )

    class _Repository:
        async def get_agent_by_id_any(self, agent_id_arg):
            if agent_id_arg != agent_id:
                return None
            return SimpleNamespace(
                id=agent_id,
                fqn="finance-ops:hidden-from-shadow",
                display_name="Hidden From Shadow",
                purpose="Hidden agent used to verify visibility semantics during fallback.",
                role_types=["financial_analysis"],
                tags=["finance"],
                maturity_level=2,
                status=LifecycleStatus.published,
            )

    service.registry_service = SimpleNamespace(
        get_agent=lambda workspace_id_arg, agent_id_arg, requesting_agent_id=None: _get_agent(
            workspace_id_arg,
            agent_id_arg,
            requesting_agent_id,
        ),
        repository=_Repository(),
    )

    async def _get_agent(workspace_id_arg, agent_id_arg, requesting_agent_id):
        del workspace_id_arg, agent_id_arg, requesting_agent_id
        return None

    repository.quality_by_agent[agent_id] = build_quality_aggregate(agent_id=agent_id)

    with pytest.raises(VisibilityDeniedError):
        await service.get_listing(agent_id, workspace_id)


@pytest.mark.asyncio
async def test_search_service_prefers_active_certification_fallback() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    service, repository, _opensearch, _qdrant, _workspaces = build_search_service(
        documents=[
            build_agent_document(
                agent_id=agent_id,
                fqn="finance-ops:visible",
                certification_status="uncertified",
            )
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )
    repository.quality_by_agent[agent_id] = build_quality_aggregate(
        agent_id=agent_id,
        certification_status="uncertified",
    )
    repository.active_certification_status_by_agent[agent_id] = "active"

    listing = await service.get_listing(agent_id, workspace_id)

    assert listing.certification_status == "active"
    assert listing.quality_profile is not None
    assert listing.quality_profile.certification_compliance == "active"


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
