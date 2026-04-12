from __future__ import annotations

from platform.marketplace.schemas import MarketplaceSearchRequest
from uuid import uuid4

from tests.marketplace_support import build_search_service


def test_rrf_merge_orders_overlap_before_single_source_results() -> None:
    service = build_search_service()[0]
    agent_overlap = str(uuid4())
    agent_keyword_only = str(uuid4())
    agent_semantic_only = str(uuid4())

    merged = service._rrf_merge(
        [
            {"agent_id": agent_overlap, "rank": 1, "score": 9.0},
            {"agent_id": agent_keyword_only, "rank": 2, "score": 7.0},
        ],
        [
            {"agent_id": agent_overlap, "rank": 3, "score": 0.8},
            {"agent_id": agent_semantic_only, "rank": 1, "score": 0.9},
        ],
    )

    assert [item["agent_id"] for item in merged] == [
        agent_overlap,
        agent_semantic_only,
        agent_keyword_only,
    ]
    assert merged[0]["score"] == (1 / 61) + (1 / 63)
    assert merged[1]["score"] == 1 / 61
    assert merged[2]["score"] == 1 / 62


def test_build_opensearch_query_includes_facets_and_visibility_filters() -> None:
    service = build_search_service()[0]
    request = MarketplaceSearchRequest(
        query=" analyze financial reports ",
        tags=["finance"],
        capabilities=["financial_analysis"],
        maturity_level_min=2,
        maturity_level_max=4,
        trust_tier=["certified"],
        certification_status=["compliant"],
        cost_tier=["metered"],
    )

    query = service._build_opensearch_query(request, ["finance-ops:*", "shared:*"])

    assert query["bool"]["must"][0]["multi_match"]["query"] == "analyze financial reports"
    assert {"terms": {"tags": ["finance"]}} in query["bool"]["filter"]
    assert {"terms": {"capabilities": ["financial_analysis"]}} in query["bool"]["filter"]
    assert {"range": {"maturity_level": {"gte": 2, "lte": 4}}} in query["bool"]["filter"]
    assert {"terms": {"trust_tier": ["certified"]}} in query["bool"]["filter"]
    assert {"terms": {"certification_status": ["compliant"]}} in query["bool"]["filter"]
    assert {"terms": {"cost_tier": ["metered"]}} in query["bool"]["filter"]
    visibility_filter = query["bool"]["filter"][-1]
    assert visibility_filter["bool"]["minimum_should_match"] == 1
    assert visibility_filter["bool"]["should"][0]["wildcard"]["fqn"]["value"] == "finance-ops:*"


def test_comparison_attribute_detects_differences_across_lists() -> None:
    service = build_search_service()[0]

    same = service._comparison_attribute([["finance"], ["finance"]], 0)
    different = service._comparison_attribute([["finance"], ["ops"]], 1)

    assert same.differs is False
    assert different.differs is True
