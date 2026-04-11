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


async def test_recommendations_endpoint_returns_generated_items() -> None:
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
            f"/api/v1/analytics/recommendations?workspace_id={workspace_id}"
        )

    assert response.status_code == 200
    assert response.json()["recommendations"][0]["recommendation_type"] == "model_switch"
