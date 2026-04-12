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


async def test_marketplace_compare_supports_side_by_side_and_range_validation() -> None:
    workspace_id = uuid4()
    agent_ids = [uuid4() for _ in range(5)]
    service, repository, *_ = build_search_service(
        documents=[
            build_agent_document(agent_id=agent_ids[0], fqn="finance-ops:a", maturity_level=1),
            build_agent_document(agent_id=agent_ids[1], fqn="finance-ops:b", maturity_level=3),
            build_agent_document(agent_id=agent_ids[2], fqn="finance-ops:c", maturity_level=3),
            build_agent_document(agent_id=agent_ids[3], fqn="finance-ops:d", maturity_level=4),
            build_agent_document(agent_id=agent_ids[4], fqn="finance-ops:e", maturity_level=5),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )
    for index, agent_id in enumerate(agent_ids[:3], start=1):
        repository.quality_by_agent[agent_id] = build_quality_aggregate(
            agent_id=agent_id,
            success_count=10 * index,
            execution_count=10 * index,
        )
        repository.ratings[(uuid4(), agent_id)] = build_rating(agent_id=agent_id, score=index + 2)

    app = build_marketplace_app(
        current_user=build_current_user(workspace_id=workspace_id),
        search_service=service,
    )
    headers = {"X-Workspace-ID": str(workspace_id)}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        compared = await client.get(
            "/api/v1/marketplace/compare",
            headers=headers,
            params={"agent_ids": ",".join(str(agent_id) for agent_id in agent_ids[:3])},
        )
        too_few = await client.get(
            "/api/v1/marketplace/compare",
            headers=headers,
            params={"agent_ids": str(agent_ids[0])},
        )
        too_many = await client.get(
            "/api/v1/marketplace/compare",
            headers=headers,
            params={"agent_ids": ",".join(str(agent_id) for agent_id in agent_ids)},
        )

    assert compared.status_code == 200
    assert compared.json()["compared_count"] == 3
    assert compared.json()["agents"][0]["maturity_level"]["differs"] is True
    assert compared.json()["agents"][0]["trust_tier"]["differs"] is False
    assert too_few.status_code == 400
    assert too_many.status_code == 400

