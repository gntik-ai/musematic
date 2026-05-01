from __future__ import annotations

from datetime import UTC, datetime
from platform.common.auth_middleware import AuthMiddleware
from platform.common.dependencies import get_current_user
from platform.status_page.dependencies import get_status_page_service
from platform.status_page.router import router
from platform.status_page.schemas import (
    ComponentDetail,
    ComponentHistoryPoint,
    ComponentStatus,
    OverallState,
    PlatformStatusSnapshotRead,
    PublicIncident,
    PublicIncidentsResponse,
    SourceKind,
)
from platform.status_page.service import SnapshotWithSource

import httpx
import pytest
from fastapi import FastAPI


class _StatusServiceStub:
    def __init__(self) -> None:
        now = datetime(2026, 4, 28, 13, 45, tzinfo=UTC)
        component = ComponentStatus(
            id="control-plane-api",
            name="Control Plane API",
            state=OverallState.degraded,
            last_check_at=now,
            uptime_30d_pct=99.9,
        )
        incident = PublicIncident(
            id="incident-123",
            title="Elevated control-plane errors",
            severity="warning",
            started_at=now,
            last_update_at=now,
            last_update_summary="Investigating elevated 5xx rate.",
            components_affected=["control-plane-api"],
        )
        self.snapshot = PlatformStatusSnapshotRead(
            snapshot_id="snapshot-123",
            generated_at=now,
            source_kind=SourceKind.poll,
            overall_state=OverallState.degraded,
            components=[component],
            active_incidents=[incident],
            scheduled_maintenance=[],
            active_maintenance=None,
            recently_resolved_incidents=[],
            uptime_30d={"control-plane-api": {"pct": 99.9, "incidents": 1}},
        )
        self.incident = incident

    async def get_public_snapshot(self) -> SnapshotWithSource:
        return SnapshotWithSource(self.snapshot, "redis")

    async def compose_current_snapshot(self) -> PlatformStatusSnapshotRead:
        return self.snapshot

    async def get_component_detail(self, component_id: str, *, days: int = 30) -> ComponentDetail:
        assert component_id == "control-plane-api"
        assert days == 30
        component = self.snapshot.components[0]
        return ComponentDetail(
            **component.model_dump(),
            history_30d=[
                ComponentHistoryPoint(
                    at=self.snapshot.generated_at,
                    state=OverallState.degraded,
                )
            ],
        )

    async def list_public_incidents(self, *, status: str | None = None) -> PublicIncidentsResponse:
        if status is None or status == "active":
            return PublicIncidentsResponse(incidents=[self.incident])
        return PublicIncidentsResponse(incidents=[])


def _build_app(service: _StatusServiceStub) -> FastAPI:
    app = FastAPI()
    app.state.clients = {}
    app.add_middleware(AuthMiddleware)
    app.include_router(router)
    app.dependency_overrides[get_status_page_service] = lambda: service
    return app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_public_status_endpoints_are_auth_exempt_and_contract_shaped() -> None:
    app = _build_app(_StatusServiceStub())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        status = await client.get("/api/v1/public/status")
        component = await client.get("/api/v1/public/components/control-plane-api")
        incidents = await client.get("/api/v1/public/incidents", params={"status": "active"})
        rss = await client.get("/api/v1/public/status/feed.rss")
        atom = await client.get("/api/v1/public/status/feed.atom")

    assert status.status_code == 200
    assert status.headers["cache-control"].startswith("public, max-age=30")
    assert status.headers["x-snapshot-source"] == "redis"
    assert status.json()["overall_state"] == "degraded"
    assert status.json()["components"][0]["id"] == "control-plane-api"

    assert component.status_code == 200
    assert component.json()["history_30d"][0]["state"] == "degraded"

    assert incidents.status_code == 200
    assert incidents.json()["incidents"][0]["id"] == "incident-123"

    assert rss.status_code == 200
    assert rss.headers["content-type"].startswith("application/rss+xml")
    assert b"<rss" in rss.content

    assert atom.status_code == 200
    assert atom.headers["content-type"].startswith("application/atom+xml")
    assert b"<feed" in atom.content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_internal_regenerate_fallback_requires_superadmin_and_writes_json(tmp_path) -> None:
    service = _StatusServiceStub()
    target = tmp_path / "last-known-good.json"
    app = FastAPI()
    app.state.clients = {}
    app.state.status_last_good_path = str(target)
    app.include_router(router)
    app.dependency_overrides[get_status_page_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "00000000-0000-0000-0000-000000000001",
        "roles": [{"role": "superadmin"}],
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/api/v1/internal/status_page/regenerate-fallback")

    assert response.status_code == 200
    assert response.json()["snapshot_id"] == "snapshot-123"
    assert "control-plane-api" in target.read_text(encoding="utf-8")
