from __future__ import annotations

from platform.marketplace.jobs import _cosine_similarity, run_cf_recommendations
from platform.marketplace.models import RecommendationType
from uuid import uuid4

import pytest
from tests.marketplace_support import (
    ClickHouseClientStub,
    InMemoryMarketplaceRepository,
    build_recommendation_service,
)


def test_cosine_similarity_handles_overlap_and_zero_norms() -> None:
    left_agent = uuid4()
    right_agent = uuid4()

    assert _cosine_similarity({left_agent: 2.0}, {left_agent: 1.0}) == 1.0
    assert _cosine_similarity({left_agent: 2.0}, {right_agent: 1.0}) == 0.0
    assert _cosine_similarity({}, {right_agent: 1.0}) == 0.0


@pytest.mark.asyncio
async def test_cf_recommendations_exclude_used_agents_and_rank_by_similarity() -> None:
    user_a = uuid4()
    user_b = uuid4()
    user_c = uuid4()
    agent_a = uuid4()
    agent_b = uuid4()
    agent_c = uuid4()
    clickhouse = ClickHouseClientStub(
        responses=[
            [
                {
                    "user_id": user_a,
                    "agent_id": agent_a,
                    "agent_fqn": "finance-ops:used",
                    "invocation_count": 10,
                },
                {
                    "user_id": user_b,
                    "agent_id": agent_a,
                    "agent_fqn": "finance-ops:used",
                    "invocation_count": 9,
                },
                {
                    "user_id": user_b,
                    "agent_id": agent_b,
                    "agent_fqn": "finance-ops:tax-optimizer",
                    "invocation_count": 5,
                },
                {
                    "user_id": user_c,
                    "agent_id": agent_a,
                    "agent_fqn": "finance-ops:used",
                    "invocation_count": 2,
                },
                {
                    "user_id": user_c,
                    "agent_id": agent_c,
                    "agent_fqn": "ops:runner",
                    "invocation_count": 1,
                },
            ]
        ]
    )
    repository = InMemoryMarketplaceRepository()
    service = build_recommendation_service(repository=repository, clickhouse=clickhouse)[0]

    await run_cf_recommendations(service=service, repository=repository)

    created = repository.recommendations_by_user[user_a]
    assert len(created) == 2
    assert created[0].agent_id == agent_b
    assert created[0].recommendation_type == RecommendationType.collaborative.value
    assert all(item.agent_id != agent_a for item in created)
    assert float(created[0].score) > float(created[1].score)
