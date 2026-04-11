from __future__ import annotations

from platform.analytics.dependencies import get_analytics_service
from platform.analytics.router import router
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from tests.analytics_support import RouterAnalyticsServiceStub

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_cost_intelligence_endpoint_returns_ranked_agents() -> None:
    workspace_id = uuid4()
    service = RouterAnalyticsServiceStub(workspace_id)
    app = FastAPI()
    app.state.settings = PlatformSettings()
    app.dependency_overrides[get_analytics_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid4())}
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/v1/analytics/cost-intelligence?workspace_id={workspace_id}"
            "&start_time=2026-04-01T00:00:00Z"
            "&end_time=2026-04-11T00:00:00Z"
        )

    assert response.status_code == 200
    assert response.json()["agents"][0]["efficiency_rank"] == 1
