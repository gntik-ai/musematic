from __future__ import annotations

from platform.marketplace.repository import MarketplaceRepository, _maybe_float
from platform.marketplace.schemas import MarketplaceSearchRequest
from uuid import uuid4

import pytest
from tests.marketplace_support import build_search_service
from tests.unit.marketplace.test_repository import ScalarsResult, SessionStub


@pytest.mark.asyncio
async def test_repository_edge_branches_cover_empty_results_and_sort_modes() -> None:
    agent_id = uuid4()
    session = SessionStub(
        execute_results=[
            ScalarsResult([]),
            ScalarsResult([]),
            ScalarsResult([]),
        ],
        scalar_results=[None, 0, None, 0, None],
    )
    repository = MarketplaceRepository(session)  # type: ignore[arg-type]

    assert await repository.get_quality_aggregates([]) == {}
    assert await repository.get_latest_trending_snapshot(limit=5) == (None, [])

    highest_rows, highest_total, highest_avg = await repository.get_ratings_for_agent(
        agent_id,
        score_filter=5,
        sort="highest",
        page=1,
        page_size=10,
    )
    lowest_rows, lowest_total, lowest_avg = await repository.get_ratings_for_agent(
        agent_id,
        score_filter=1,
        sort="lowest",
        page=1,
        page_size=10,
    )

    assert highest_rows == []
    assert highest_total == 0
    assert highest_avg is None
    assert lowest_rows == []
    assert lowest_total == 0
    assert lowest_avg is None
    assert await repository.get_rating_summaries([]) == {}
    assert _maybe_float(None) is None


@pytest.mark.asyncio
async def test_search_service_edge_branches_cover_visibility_and_facet_rejections() -> None:
    workspace_id = uuid4()
    service = build_search_service()[0]
    service.workspaces_service = None
    assert await service._get_visibility_patterns(workspace_id) == ["*"]

    service.workspaces_service = object()
    assert await service._get_visibility_patterns(workspace_id) == ["*"]
    assert service._is_visible("finance-ops:anything", ["*"]) is True

    payload = {
        "tags": ["finance"],
        "capabilities": ["ops"],
        "maturity_level": 1,
        "trust_tier": "unverified",
        "certification_status": "uncertified",
        "cost_tier": "free",
    }

    assert (
        service._matches_facets(
            payload,
            MarketplaceSearchRequest(query="", capabilities=["finance"]),
        )
        is False
    )
    assert (
        service._matches_facets(
            payload,
            MarketplaceSearchRequest(query="", maturity_level_min=2),
        )
        is False
    )
    assert (
        service._matches_facets(
            payload,
            MarketplaceSearchRequest(query="", maturity_level_max=0),
        )
        is False
    )
    assert (
        service._matches_facets(
            payload,
            MarketplaceSearchRequest(query="", trust_tier=["certified"]),
        )
        is False
    )
    assert (
        service._matches_facets(
            payload,
            MarketplaceSearchRequest(query="", certification_status=["compliant"]),
        )
        is False
    )
    assert (
        service._matches_facets(
            payload,
            MarketplaceSearchRequest(query="", cost_tier=["metered"]),
        )
        is False
    )
