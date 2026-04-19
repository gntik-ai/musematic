from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.context_engineering.dependencies import get_context_engineering_service
from platform.context_engineering.router import router
from platform.context_engineering.schemas import CorrelationFleetResponse, CorrelationResultResponse
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _CorrelationRouterServiceStub:
    def __init__(self, workspace_id: UUID) -> None:
        now = datetime.now(UTC)
        self.response = CorrelationResultResponse(
            id=uuid4(),
            workspace_id=workspace_id,
            agent_fqn="finance:agent",
            dimension="retrieval_accuracy",
            performance_metric="quality_score",
            window_start=now - timedelta(days=30),
            window_end=now,
            coefficient=0.72,
            classification="strong_positive",
            data_point_count=40,
            computed_at=now,
            created_at=now,
            updated_at=now,
        )

    async def get_latest_correlation(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        *,
        agent_fqn: str,
        window_days=None,
        classification=None,
    ) -> CorrelationFleetResponse:
        del actor_id, window_days, classification
        assert workspace_id == self.response.workspace_id
        assert agent_fqn == self.response.agent_fqn
        return CorrelationFleetResponse(items=[self.response], total=1)

    async def query_fleet_correlations(
        self, workspace_id: UUID, actor_id: UUID, *, classification=None
    ) -> CorrelationFleetResponse:
        del actor_id, classification
        assert workspace_id == self.response.workspace_id
        return CorrelationFleetResponse(items=[self.response], total=1)

    async def enqueue_correlation_recompute(
        self, workspace_id: UUID, actor_id: UUID, *, agent_fqn=None, window_days=None
    ) -> dict[str, object]:
        del actor_id
        assert workspace_id == self.response.workspace_id
        return {"enqueued": True, "agent_fqn": agent_fqn, "window_days": window_days}


def _build_app(service: _CorrelationRouterServiceStub, workspace_id: UUID) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid4())}
    app.dependency_overrides[get_context_engineering_service] = lambda: service
    app.state.settings = object()
    app.state.clients = {}
    app.state.context_engineering_service = service
    return app


@pytest.mark.asyncio
async def test_correlation_routes_return_expected_payloads() -> None:
    workspace_id = uuid4()
    app = _build_app(_CorrelationRouterServiceStub(workspace_id), workspace_id)
    headers = {"X-Workspace-ID": str(workspace_id)}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        agent = await client.get(
            "/api/v1/context-engineering/correlations/finance:agent", headers=headers
        )
        fleet = await client.get(
            "/api/v1/context-engineering/correlations?classification=strong_positive",
            headers=headers,
        )
        recompute = await client.post(
            "/api/v1/context-engineering/correlations/recompute",
            json={"agent_fqn": "finance:agent", "window_days": 30},
            headers=headers,
        )

    assert agent.status_code == 200
    assert agent.json()["items"][0]["coefficient"] == 0.72
    assert fleet.status_code == 200
    assert fleet.json()["total"] == 1
    assert recompute.status_code == 202
    assert recompute.json()["enqueued"] is True
