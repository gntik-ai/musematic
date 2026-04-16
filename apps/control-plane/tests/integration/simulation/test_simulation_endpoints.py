from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.simulation.dependencies import get_simulation_service
from platform.simulation.router import router
from platform.simulation.schemas import SimulationRunListResponse, SimulationRunResponse
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_simulation_run_create_get_list_cancel_contracts() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    run_id = uuid4()
    twin_id = uuid4()
    now = datetime.now(UTC)
    run = SimulationRunResponse(
        run_id=run_id,
        workspace_id=workspace_id,
        name="Scenario",
        description=None,
        status="provisioning",
        digital_twin_ids=[twin_id],
        scenario_config={"duration_seconds": 60},
        isolation_policy_id=None,
        controller_run_id="ctrl-1",
        started_at=None,
        completed_at=None,
        results=None,
        initiated_by=actor_id,
        created_at=now,
    )
    service = SimpleNamespace(
        create_simulation_run=AsyncMock(return_value=run),
        get_simulation_run=AsyncMock(return_value=run),
        list_simulation_runs=AsyncMock(return_value=SimulationRunListResponse(items=[run])),
        cancel_simulation_run=AsyncMock(
            return_value=run.model_copy(update={"status": "cancelled"})
        ),
    )
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.dependency_overrides[get_simulation_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
    }
    client = TestClient(app)

    assert (
        client.post(
            "/api/v1/simulations",
            json={
                "workspace_id": str(workspace_id),
                "name": "Scenario",
                "digital_twin_ids": [str(twin_id)],
                "scenario_config": {"duration_seconds": 60},
            },
        ).status_code
        == 201
    )
    assert client.get(f"/api/v1/simulations/{run_id}").status_code == 200
    assert client.get("/api/v1/simulations", params={"status": "provisioning"}).status_code == 200
    cancelled = client.post(f"/api/v1/simulations/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
