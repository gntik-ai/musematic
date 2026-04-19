from __future__ import annotations

from datetime import UTC, datetime
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.router import router
from platform.agentops.schemas import (
    ProficiencyFleetResponse,
    ProficiencyHistoryResponse,
    ProficiencyResponse,
)
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _ProficiencyRouterServiceStub:
    def __init__(self, workspace_id: UUID) -> None:
        now = datetime.now(UTC)
        self.response = ProficiencyResponse(
            agent_fqn="finance:agent",
            workspace_id=workspace_id,
            level="competent",
            dimension_values={
                "retrieval_accuracy": 0.7,
                "instruction_adherence": 0.6,
                "context_coherence": 0.6,
                "aggregate_score": 0.64,
            },
            observation_count=9,
            trigger="scheduled",
            assessed_at=now,
            missing_dimensions=[],
        )

    async def get_proficiency(self, agent_fqn: str, workspace_id: UUID) -> ProficiencyResponse:
        assert agent_fqn == self.response.agent_fqn
        assert workspace_id == self.response.workspace_id
        return self.response

    async def list_proficiency_history(
        self, agent_fqn: str, workspace_id: UUID, *, cursor=None, limit=20
    ) -> ProficiencyHistoryResponse:
        del cursor, limit
        assert agent_fqn == self.response.agent_fqn
        assert workspace_id == self.response.workspace_id
        return ProficiencyHistoryResponse(items=[self.response], next_cursor=None)

    async def query_proficiency_fleet(
        self, workspace_id: UUID, *, level_at_or_below=None, level=None
    ) -> ProficiencyFleetResponse:
        del level_at_or_below, level
        assert workspace_id == self.response.workspace_id
        return ProficiencyFleetResponse(items=[self.response], total=1)


def _build_app(service: _ProficiencyRouterServiceStub, workspace_id: UUID) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(uuid4()),
        "workspace_id": str(workspace_id),
    }
    app.dependency_overrides[get_agentops_service] = lambda: service
    return app


@pytest.mark.asyncio
async def test_proficiency_routes_return_expected_payloads() -> None:
    workspace_id = uuid4()
    app = _build_app(_ProficiencyRouterServiceStub(workspace_id), workspace_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        fleet = await client.get("/api/v1/agentops/proficiency?level_at_or_below=competent")
        current = await client.get("/api/v1/agentops/finance:agent/proficiency")
        history = await client.get("/api/v1/agentops/finance:agent/proficiency/history")

    assert fleet.status_code == 200
    assert fleet.json()["total"] == 1
    assert current.status_code == 200
    assert current.json()["level"] == "competent"
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1
