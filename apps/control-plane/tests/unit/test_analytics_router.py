from __future__ import annotations

from datetime import UTC, datetime
from platform.analytics.dependencies import get_analytics_service
from platform.analytics.router import (
    get_cost_forecast,
    get_cost_intelligence,
    get_kpi,
    get_recommendations,
    get_usage,
    router,
)
from platform.analytics.schemas import Granularity
from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from tests.analytics_support import RouterAnalyticsServiceStub


def _settings() -> PlatformSettings:
    return PlatformSettings(
        AUTH_JWT_SECRET_KEY="analytics-router-secret",
        AUTH_JWT_ALGORITHM="HS256",
    )


def _build_app(service: RouterAnalyticsServiceStub) -> FastAPI:
    app = FastAPI()
    app.state.settings = _settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.dependency_overrides[get_analytics_service] = lambda: service
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_router_requires_auth_when_middleware_is_enabled() -> None:
    app = FastAPI()
    app.state.settings = _settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.add_middleware(AuthMiddleware)
    app.dependency_overrides[get_analytics_service] = lambda: RouterAnalyticsServiceStub(uuid4())
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/analytics/usage")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_router_endpoint_functions_delegate_to_service() -> None:
    workspace_id = uuid4()
    service = RouterAnalyticsServiceStub(workspace_id)
    user = {"sub": str(uuid4())}
    now = datetime.now(UTC)

    usage = await get_usage(
        workspace_id=workspace_id,
        start_time=now,
        end_time=now,
        granularity=Granularity.DAILY,
        agent_fqn=None,
        model_id=None,
        limit=100,
        offset=0,
        current_user=user,
        analytics_service=service,  # type: ignore[arg-type]
    )
    cost_intelligence = await get_cost_intelligence(
        workspace_id=workspace_id,
        start_time=now,
        end_time=now,
        current_user=user,
        analytics_service=service,  # type: ignore[arg-type]
    )
    recommendations = await get_recommendations(
        workspace_id=workspace_id,
        current_user=user,
        analytics_service=service,  # type: ignore[arg-type]
    )
    forecast = await get_cost_forecast(
        workspace_id=workspace_id,
        horizon_days=30,
        current_user=user,
        analytics_service=service,  # type: ignore[arg-type]
    )
    kpi = await get_kpi(
        workspace_id=workspace_id,
        start_time=now,
        end_time=now,
        granularity=Granularity.DAILY,
        current_user=user,
        analytics_service=service,  # type: ignore[arg-type]
    )

    assert usage.workspace_id == workspace_id
    assert cost_intelligence.workspace_id == workspace_id
    assert recommendations.workspace_id == workspace_id
    assert forecast.workspace_id == workspace_id
    assert kpi.workspace_id == workspace_id
    assert [call[0] for call in service.calls] == [
        "get_usage",
        "get_cost_intelligence",
        "get_recommendations",
        "get_forecast",
        "get_kpi_series",
    ]
