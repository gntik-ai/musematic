from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.simulation.dependencies import get_simulation_service
from platform.simulation.router import router
from platform.simulation.schemas import (
    SimulationIsolationPolicyListResponse,
    SimulationIsolationPolicyResponse,
)
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_isolation_policy_endpoint_contracts() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    policy_id = uuid4()
    now = datetime.now(UTC)
    policy = SimulationIsolationPolicyResponse(
        policy_id=policy_id,
        workspace_id=workspace_id,
        name="strict",
        description=None,
        blocked_actions=[{"action_type": "connector.send_message", "severity": "critical"}],
        stubbed_actions=[],
        permitted_read_sources=[],
        is_default=False,
        halt_on_critical_breach=True,
        created_at=now,
        updated_at=now,
    )
    service = SimpleNamespace(
        create_isolation_policy=AsyncMock(return_value=policy),
        get_isolation_policy=AsyncMock(return_value=policy),
        list_isolation_policies=AsyncMock(
            return_value=SimulationIsolationPolicyListResponse(items=[policy])
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
            "/api/v1/simulations/isolation-policies",
            json={
                "workspace_id": str(workspace_id),
                "name": "strict",
                "blocked_actions": [
                    {"action_type": "connector.send_message", "severity": "critical"}
                ],
            },
        ).status_code
        == 201
    )
    assert client.get(f"/api/v1/simulations/isolation-policies/{policy_id}").status_code == 200
    response = client.get("/api/v1/simulations/isolation-policies")
    assert response.json()["items"][0]["name"] == "strict"
