from __future__ import annotations

from datetime import UTC, datetime
from platform.common.auth_middleware import AuthMiddleware
from platform.common.dependencies import get_current_user
from platform.status_page.dependencies import get_status_page_service
from platform.status_page.me_router import router
from platform.status_page.schemas import (
    MyIncidentSummary,
    MyMaintenanceWindowSummary,
    MyPlatformStatus,
    OverallState,
)
from typing import Any

import httpx
import pytest
from fastapi import FastAPI


class _StatusServiceStub:
    async def get_my_platform_status(self, current_user: dict[str, Any]) -> MyPlatformStatus:
        assert current_user["sub"] == "user-1"
        now = datetime(2026, 5, 1, 12, tzinfo=UTC)
        return MyPlatformStatus(
            overall_state=OverallState.maintenance,
            active_maintenance=MyMaintenanceWindowSummary(
                window_id="mw-1",
                title="Database upgrade",
                starts_at=now,
                ends_at=now.replace(hour=13),
                blocks_writes=True,
                components_affected=["control-plane-api"],
                affects_my_features=[],
            ),
            active_incidents=[
                MyIncidentSummary(
                    id="incident-1",
                    title="Elevated errors",
                    severity="warning",
                    started_at=now,
                    last_update_at=now,
                    last_update_summary="Investigating",
                    components_affected=["control-plane-api"],
                    affects_my_features=[],
                )
            ],
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_platform_status_requires_auth() -> None:
    app = FastAPI()
    app.state.clients = {}
    app.add_middleware(AuthMiddleware)
    app.include_router(router)
    app.dependency_overrides[get_status_page_service] = lambda: _StatusServiceStub()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/me/platform-status")

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_platform_status_returns_user_affected_features_shape() -> None:
    app = FastAPI()
    app.state.clients = {}
    app.include_router(router)
    app.dependency_overrides[get_status_page_service] = lambda: _StatusServiceStub()
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-1"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/me/platform-status")

    assert response.status_code == 200
    body = response.json()
    assert body["overall_state"] == "maintenance"
    assert body["active_maintenance"]["affects_my_features"] == []
    assert body["active_incidents"][0]["affects_my_features"] == []
