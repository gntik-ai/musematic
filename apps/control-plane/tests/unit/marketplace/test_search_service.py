from __future__ import annotations

from platform.marketplace.exceptions import (
    AgentNotFoundError,
    ComparisonRangeError,
    VisibilityDeniedError,
)
from platform.marketplace.schemas import MarketplaceSearchRequest
from uuid import uuid4

import pytest
from tests.marketplace_support import (
    QdrantClientStub,
    build_agent_document,
    build_quality_aggregate,
    build_rating,
    build_search_service,
)


@pytest.mark.asyncio
async def test_search_service_merges_keyword_and_semantic_results_with_visibility() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    report_agent = uuid4()
    semantic_agent = uuid4()
    hidden_agent = uuid4()
    repository = build_search_service()[1]
    repository.quality_by_agent[report_agent] = build_quality_aggregate(agent_id=report_agent)
    repository.ratings[(uuid4(), report_agent)] = build_rating(agent_id=report_agent, score=5)
    repository.quality_by_agent[semantic_agent] = build_quality_aggregate(
        agent_id=semantic_agent,
        success_count=20,
        execution_count=25,
    )
    qdrant = QdrantClientStub(
        search_results=[
            {
                "id": str(semantic_agent),
                "score": 0.92,
                "payload": {"fqn": "finance-ops:ap-handler", "capabilities": ["accounts_payable"]},
            },
            {
                "id": str(report_agent),
                "score": 0.4,
                "payload": {
                    "fqn": "finance-ops:report-analyzer",
                    "capabilities": ["financial_analysis"],
                },
            },
            {
                "id": str(hidden_agent),
                "score": 0.99,
                "payload": {"fqn": "secret-ops:hidden"},
            },
        ]
    )
    service, repository, _opensearch, _qdrant, _workspaces = build_search_service(
        repository=repository,
        documents=[
            build_agent_document(
                agent_id=report_agent,
                fqn="finance-ops:report-analyzer",
                description="Analyze financial reports and statements.",
                capabilities=["financial_analysis"],
                invocation_count_30d=50,
            ),
            build_agent_document(
                agent_id=semantic_agent,
                fqn="finance-ops:ap-handler",
                description="Automated accounts payable handler.",
                capabilities=["accounts_payable"],
                invocation_count_30d=20,
            ),
            build_agent_document(
                agent_id=hidden_agent,
                fqn="secret-ops:hidden",
                description="Classified agent",
                invocation_count_30d=999,
            ),
        ],
        qdrant=qdrant,
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )

    async def _embed_text(_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    service._embed_text = _embed_text  # type: ignore[method-assign]
    response = await service.search(
        MarketplaceSearchRequest(query="analyze financial reports", page=1, page_size=10),
        workspace_id,
        user_id,
    )

    assert [item.fqn for item in response.results] == [
        "finance-ops:report-analyzer",
        "finance-ops:ap-handler",
    ]
    assert response.total == 2
    assert response.has_results is True
    assert response.results[0].aggregate_rating is not None
    assert response.results[0].aggregate_rating.avg_score == 5.0


@pytest.mark.asyncio
async def test_search_service_browse_mode_applies_sort_and_facet_filters() -> None:
    workspace_id = uuid4()
    service, repository, _opensearch, _qdrant, _workspaces = build_search_service(
        documents=[
            build_agent_document(
                fqn="finance-ops:senior",
                maturity_level=3,
                invocation_count_30d=100,
            ),
            build_agent_document(
                fqn="finance-ops:junior",
                maturity_level=1,
                invocation_count_30d=200,
            ),
            build_agent_document(
                fqn="hr-tools:screen",
                maturity_level=3,
                invocation_count_30d=50,
            ),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*", "hr-tools:*"]},
    )
    for _document in _opensearch.documents:
        repository.quality_by_agent[uuid4()] = build_quality_aggregate()

    response = await service.search(
        MarketplaceSearchRequest(query="", maturity_level_min=2, page=1, page_size=10),
        workspace_id,
        uuid4(),
    )

    assert [item.fqn for item in response.results] == ["finance-ops:senior", "hr-tools:screen"]


@pytest.mark.asyncio
async def test_search_service_get_listing_and_compare_handle_errors_and_diffs() -> None:
    workspace_id = uuid4()
    agent_one = uuid4()
    agent_two = uuid4()
    hidden_agent = uuid4()
    service, repository, _opensearch, _qdrant, _workspaces = build_search_service(
        documents=[
            build_agent_document(agent_id=agent_one, fqn="finance-ops:one", maturity_level=1),
            build_agent_document(agent_id=agent_two, fqn="finance-ops:two", maturity_level=3),
            build_agent_document(agent_id=hidden_agent, fqn="secret-ops:hidden"),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )
    repository.quality_by_agent[agent_one] = build_quality_aggregate(agent_id=agent_one)
    repository.quality_by_agent[agent_two] = build_quality_aggregate(
        agent_id=agent_two,
        success_count=40,
        execution_count=50,
    )
    repository.ratings[(uuid4(), agent_one)] = build_rating(agent_id=agent_one, score=4)
    repository.ratings[(uuid4(), agent_two)] = build_rating(agent_id=agent_two, score=5)

    listing = await service.get_listing(agent_one, workspace_id)
    comparison = await service.compare([agent_one, agent_two], workspace_id)

    assert listing.fqn == "finance-ops:one"
    assert comparison.compared_count == 2
    assert comparison.agents[0].maturity_level.differs is True
    assert comparison.agents[0].trust_tier.differs is False

    with pytest.raises(ComparisonRangeError):
        await service.compare([agent_one], workspace_id)
    with pytest.raises(VisibilityDeniedError):
        await service.get_listing(hidden_agent, workspace_id)
    with pytest.raises(AgentNotFoundError):
        await service.get_listing(uuid4(), workspace_id)
