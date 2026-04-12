from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from tests.marketplace_support import (
    InMemoryMarketplaceRepository,
    build_agent_document,
    build_current_user,
    build_marketplace_app,
    build_quality_aggregate,
    build_quality_service,
    build_search_service,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_marketplace_quality_profiles_cover_history_no_data_and_stale_state() -> None:
    workspace_id = uuid4()
    active_agent = uuid4()
    empty_agent = uuid4()
    stale_agent = uuid4()
    repository = InMemoryMarketplaceRepository()
    search_service = build_search_service(
        repository=repository,
        documents=[
            build_agent_document(agent_id=active_agent, fqn="finance-ops:active"),
            build_agent_document(agent_id=empty_agent, fqn="finance-ops:empty"),
            build_agent_document(agent_id=stale_agent, fqn="finance-ops:stale"),
        ],
        visibility_by_workspace={workspace_id: ["finance-ops:*"]},
    )[0]
    quality_service = build_quality_service(repository=repository)[0]
    repository.quality_by_agent[stale_agent] = build_quality_aggregate(
        agent_id=stale_agent,
        has_data=True,
        updated_at=datetime.now(UTC) - timedelta(days=2),
        source_unavailable_since=datetime.now(UTC) - timedelta(hours=6),
    )
    for _ in range(100):
        await quality_service.handle_execution_event(
            {"event_type": "step.completed", "agent_id": str(active_agent)}
        )
    for _ in range(5):
        await quality_service.handle_execution_event(
            {"event_type": "step.failed", "agent_id": str(active_agent)}
        )

    app = build_marketplace_app(
        current_user=build_current_user(workspace_id=workspace_id),
        search_service=search_service,
        quality_service=quality_service,
    )
    headers = {"X-Workspace-ID": str(workspace_id)}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        active = await client.get(
            f"/api/v1/marketplace/agents/{active_agent}/quality",
            headers=headers,
        )
        empty = await client.get(
            f"/api/v1/marketplace/agents/{empty_agent}/quality",
            headers=headers,
        )
        stale = await client.get(
            f"/api/v1/marketplace/agents/{stale_agent}/quality",
            headers=headers,
        )

    assert active.status_code == 200
    assert active.json()["has_data"] is True
    assert active.json()["success_rate"] == pytest.approx(100 / 105)
    assert empty.status_code == 200
    assert empty.json()["has_data"] is False
    assert empty.json()["success_rate"] is None
    assert stale.status_code == 200
    assert stale.json()["source_unavailable"] is True
    assert stale.json()["last_updated_at"] is not None

