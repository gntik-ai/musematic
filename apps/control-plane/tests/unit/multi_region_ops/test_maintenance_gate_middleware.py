from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.multi_region_ops.constants import REDIS_KEY_ACTIVE_WINDOW
from platform.multi_region_ops.middleware.maintenance_gate import MaintenanceGateMiddleware
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


class FakeRedis:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload

    async def get(self, key: str) -> bytes | None:
        assert key == REDIS_KEY_ACTIVE_WINDOW
        if self.payload is None:
            return None
        return json.dumps(self.payload).encode()


def _app(settings: PlatformSettings, redis: FakeRedis | None = None) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.clients = {"redis": redis} if redis is not None else {}
    app.add_middleware(MaintenanceGateMiddleware)

    @app.post("/mutate")
    async def mutate() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/admin/maintenance/windows/{window_id}/disable")
    async def disable_window(window_id: str) -> dict[str, str]:
        return {"id": window_id, "status": "completed"}

    @app.get("/read")
    async def read() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _active_window_payload() -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": str(uuid4()),
        "starts_at": (now - timedelta(minutes=5)).isoformat(),
        "ends_at": (now + timedelta(minutes=30)).isoformat(),
        "reason": "database maintenance",
        "blocks_writes": True,
        "announcement_text": "Writes are paused for maintenance",
        "status": "active",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


@pytest.mark.asyncio
async def test_maintenance_gate_short_circuits_when_feature_flag_off() -> None:
    app = _app(
        PlatformSettings(feature_maintenance_mode=False), FakeRedis(_active_window_payload())
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mutate")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_maintenance_gate_blocks_mutations_but_allows_reads() -> None:
    app = _app(PlatformSettings(feature_maintenance_mode=True), FakeRedis(_active_window_payload()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        blocked = await client.post("/mutate")
        allowed = await client.get("/read")

    assert blocked.status_code == 503
    assert blocked.json()["error"] == "maintenance_in_progress"
    assert blocked.headers["Retry-After"]
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_maintenance_gate_allows_disable_control_request() -> None:
    app = _app(PlatformSettings(feature_maintenance_mode=True), FakeRedis(_active_window_payload()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/admin/maintenance/windows/{uuid4()}/disable")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
