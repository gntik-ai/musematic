from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.router import router
from platform.agentops.schemas import (
    AgentHealthConfigResponse,
    AgentHealthScoreHistoryResponse,
    AgentHealthScoreResponse,
)
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _HealthRouterServiceStub:
    def __init__(self, response: AgentHealthScoreResponse) -> None:
        self.response = response
        self.config = AgentHealthConfigResponse(
            id=uuid4(),
            workspace_id=response.workspace_id,
            weight_uptime=Decimal("20.00"),
            weight_quality=Decimal("35.00"),
            weight_safety=Decimal("25.00"),
            weight_cost_efficiency=Decimal("10.00"),
            weight_satisfaction=Decimal("10.00"),
            warning_threshold=Decimal("60.00"),
            critical_threshold=Decimal("40.00"),
            scoring_interval_minutes=15,
            min_sample_size=50,
            rolling_window_days=30,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def get_health_score(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> AgentHealthScoreResponse:
        assert agent_fqn == self.response.agent_fqn
        assert workspace_id == self.response.workspace_id
        return self.response

    async def list_health_history(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> AgentHealthScoreHistoryResponse:
        del cursor, limit, start_time, end_time
        assert agent_fqn == self.response.agent_fqn
        assert workspace_id == self.response.workspace_id
        return AgentHealthScoreHistoryResponse(items=[self.response], next_cursor=None)

    async def get_health_config(self, workspace_id: UUID) -> AgentHealthConfigResponse:
        assert workspace_id == self.response.workspace_id
        return self.config

    async def update_health_config(
        self,
        workspace_id: UUID,
        payload,
    ) -> AgentHealthConfigResponse:
        assert workspace_id == self.response.workspace_id
        self.config = AgentHealthConfigResponse(
            id=self.config.id,
            workspace_id=workspace_id,
            weight_uptime=payload.weight_uptime,
            weight_quality=payload.weight_quality,
            weight_safety=payload.weight_safety,
            weight_cost_efficiency=payload.weight_cost_efficiency,
            weight_satisfaction=payload.weight_satisfaction,
            warning_threshold=payload.warning_threshold,
            critical_threshold=payload.critical_threshold,
            scoring_interval_minutes=payload.scoring_interval_minutes,
            min_sample_size=payload.min_sample_size,
            rolling_window_days=payload.rolling_window_days,
            created_at=self.config.created_at,
            updated_at=datetime.now(UTC),
        )
        return self.config


def _build_app(service: _HealthRouterServiceStub, workspace_id: UUID) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(uuid4()),
        "workspace_id": str(workspace_id),
    }
    app.dependency_overrides[get_agentops_service] = lambda: service
    return app


def _health_response(
    *,
    workspace_id: UUID,
    insufficient_data: bool,
    composite_score: Decimal = Decimal("82.50"),
) -> AgentHealthScoreResponse:
    now = datetime.now(UTC)
    return AgentHealthScoreResponse(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=uuid4(),
        composite_score=composite_score,
        uptime_score=None if insufficient_data else Decimal("80.00"),
        quality_score=None if insufficient_data else Decimal("85.00"),
        safety_score=None if insufficient_data else Decimal("90.00"),
        cost_efficiency_score=None if insufficient_data else Decimal("70.00"),
        satisfaction_score=None if insufficient_data else Decimal("87.00"),
        weights_snapshot={
            "uptime": 20.0,
            "quality": 35.0,
            "safety": 25.0,
            "cost_efficiency": 10.0,
            "satisfaction": 10.0,
        },
        missing_dimensions=["uptime", "quality", "safety", "cost_efficiency", "satisfaction"]
        if insufficient_data
        else [],
        sample_counts={},
        computed_at=now,
        observation_window_start=now - timedelta(days=30),
        observation_window_end=now,
        below_warning=not insufficient_data and composite_score < Decimal("60.00"),
        below_critical=not insufficient_data and composite_score < Decimal("40.00"),
        insufficient_data=insufficient_data,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_get_health_returns_200_with_expected_schema() -> None:
    workspace_id = uuid4()
    app = _build_app(
        _HealthRouterServiceStub(
            _health_response(workspace_id=workspace_id, insufficient_data=False)
        ),
        workspace_id,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/agentops/finance:agent/health")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_fqn"] == "finance:agent"
    assert body["workspace_id"] == str(workspace_id)
    assert body["composite_score"] == "82.50"
    assert body["insufficient_data"] is False


@pytest.mark.asyncio
async def test_put_health_config_rejects_weights_that_do_not_sum_to_100() -> None:
    workspace_id = uuid4()
    app = _build_app(
        _HealthRouterServiceStub(
            _health_response(workspace_id=workspace_id, insufficient_data=False)
        ),
        workspace_id,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.put(
            "/api/v1/agentops/health-config",
            json={
                "weight_uptime": "10.00",
                "weight_quality": "10.00",
                "weight_safety": "10.00",
                "weight_cost_efficiency": "10.00",
                "weight_satisfaction": "10.00",
                "warning_threshold": "60.00",
                "critical_threshold": "40.00",
                "scoring_interval_minutes": 15,
                "min_sample_size": 50,
                "rolling_window_days": 30,
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AGENTOPS_WEIGHT_SUM_INVALID"


@pytest.mark.asyncio
async def test_get_health_returns_insufficient_data_when_no_score_exists() -> None:
    workspace_id = uuid4()
    app = _build_app(
        _HealthRouterServiceStub(
            _health_response(workspace_id=workspace_id, insufficient_data=True)
        ),
        workspace_id,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/agentops/finance:agent/health")

    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_data"] is True
    assert body["missing_dimensions"] == [
        "uptime",
        "quality",
        "safety",
        "cost_efficiency",
        "satisfaction",
    ]
