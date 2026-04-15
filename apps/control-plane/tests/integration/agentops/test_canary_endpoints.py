from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.exceptions import CanaryConflictError
from platform.agentops.router import router
from platform.agentops.schemas import CanaryDeploymentListResponse, CanaryDeploymentResponse
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _CanaryRouterServiceStub:
    def __init__(self, workspace_id: UUID) -> None:
        self.workspace_id = workspace_id
        self.active: CanaryDeploymentResponse | None = None
        self.history: list[CanaryDeploymentResponse] = []
        self.events: list[str] = []

    async def start_canary(
        self, agent_fqn: str, payload, *, initiated_by: UUID
    ) -> CanaryDeploymentResponse:
        assert agent_fqn == "finance:agent"
        assert payload.workspace_id == self.workspace_id
        if self.active is not None:
            raise CanaryConflictError(agent_fqn, self.workspace_id)
        now = datetime.now(UTC)
        deployment = CanaryDeploymentResponse(
            id=uuid4(),
            workspace_id=self.workspace_id,
            agent_fqn=agent_fqn,
            production_revision_id=payload.production_revision_id,
            canary_revision_id=payload.canary_revision_id,
            initiated_by=initiated_by,
            traffic_percentage=payload.traffic_percentage,
            observation_window_hours=payload.observation_window_hours,
            quality_tolerance_pct=payload.quality_tolerance_pct,
            latency_tolerance_pct=payload.latency_tolerance_pct,
            error_rate_tolerance_pct=payload.error_rate_tolerance_pct,
            cost_tolerance_pct=payload.cost_tolerance_pct,
            status="active",
            started_at=now,
            observation_ends_at=now + timedelta(hours=payload.observation_window_hours),
            completed_at=None,
            promoted_at=None,
            rolled_back_at=None,
            rollback_reason=None,
            manual_override_by=None,
            manual_override_reason=None,
            latest_metrics_snapshot=None,
            created_at=now,
            updated_at=now,
        )
        self.active = deployment
        self.history.append(deployment)
        return deployment

    async def get_active_canary(
        self, agent_fqn: str, workspace_id: UUID
    ) -> CanaryDeploymentResponse | None:
        assert agent_fqn == "finance:agent"
        assert workspace_id == self.workspace_id
        return self.active

    async def get_canary(self, canary_id: UUID) -> CanaryDeploymentResponse:
        for item in self.history:
            if item.id == canary_id:
                return item
        raise AssertionError("unexpected canary id")

    async def promote_canary(
        self, canary_id: UUID, payload, *, actor: UUID
    ) -> CanaryDeploymentResponse:
        deployment = await self.get_canary(canary_id)
        deployment.status = "manually_promoted"
        deployment.manual_override_by = actor
        deployment.manual_override_reason = payload.reason
        self.active = None
        self.events.append("promoted")
        return deployment

    async def rollback_canary(
        self, canary_id: UUID, payload, *, actor: UUID
    ) -> CanaryDeploymentResponse:
        deployment = await self.get_canary(canary_id)
        deployment.status = "manually_rolled_back"
        deployment.manual_override_by = actor
        deployment.manual_override_reason = payload.reason
        deployment.rollback_reason = payload.reason
        deployment.rolled_back_at = datetime.now(UTC)
        self.active = None
        self.events.append("rolled_back")
        return deployment

    async def list_canaries(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> CanaryDeploymentListResponse:
        del cursor, limit
        assert agent_fqn == "finance:agent"
        assert workspace_id == self.workspace_id
        return CanaryDeploymentListResponse(items=self.history, next_cursor=None)


def _build_app(service: _CanaryRouterServiceStub, workspace_id: UUID, actor_id: UUID) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
    }
    app.dependency_overrides[get_agentops_service] = lambda: service
    return app


def _payload(workspace_id: UUID) -> dict[str, object]:
    return {
        "workspace_id": str(workspace_id),
        "production_revision_id": str(uuid4()),
        "canary_revision_id": str(uuid4()),
        "traffic_percentage": 10,
        "observation_window_hours": 2.0,
        "quality_tolerance_pct": 5.0,
        "latency_tolerance_pct": 5.0,
        "error_rate_tolerance_pct": 5.0,
        "cost_tolerance_pct": 5.0,
    }


@pytest.mark.asyncio
async def test_post_canary_returns_created_with_expected_schema() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _CanaryRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/agentops/finance:agent/canary",
            json=_payload(workspace_id),
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["traffic_percentage"] == 10


@pytest.mark.asyncio
async def test_second_post_canary_returns_conflict() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _CanaryRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/api/v1/agentops/finance:agent/canary", json=_payload(workspace_id)
        )
        second = await client.post(
            "/api/v1/agentops/finance:agent/canary",
            json=_payload(workspace_id),
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "AGENTOPS_CANARY_CONFLICT"


@pytest.mark.asyncio
async def test_post_canary_rollback_changes_status_and_records_event() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _CanaryRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/agentops/finance:agent/canary", json=_payload(workspace_id)
        )
        canary_id = created.json()["id"]
        rollback = await client.post(
            f"/api/v1/agentops/canaries/{canary_id}/rollback",
            json={"reason": "Metric regression"},
        )

    assert rollback.status_code == 200
    assert rollback.json()["status"] == "manually_rolled_back"
    assert service.events == ["rolled_back"]


@pytest.mark.asyncio
async def test_get_active_canary_returns_null_when_none_active() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _CanaryRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/agentops/finance:agent/canary/active")

    assert response.status_code == 200
    assert response.json() is None
