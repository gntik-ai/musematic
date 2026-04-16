from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.simulation.dependencies import get_simulation_service
from platform.simulation.router import router
from platform.simulation.schemas import (
    DigitalTwinListResponse,
    DigitalTwinResponse,
    DigitalTwinVersionListResponse,
)
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_twin_create_get_modify_and_versions_contracts() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    twin_id = uuid4()
    now = datetime.now(UTC)
    twin = DigitalTwinResponse(
        twin_id=twin_id,
        workspace_id=workspace_id,
        source_agent_fqn="namespace.agent",
        source_revision_id=None,
        version=1,
        parent_twin_id=None,
        config_snapshot={"model": {"name": "claude"}},
        behavioral_history_summary={"period_days": 30},
        modifications=[],
        is_active=True,
        created_at=now,
    )
    modified = twin.model_copy(update={"twin_id": uuid4(), "version": 2, "parent_twin_id": twin_id})
    service = SimpleNamespace(
        create_digital_twin=AsyncMock(return_value=twin),
        get_digital_twin=AsyncMock(return_value=twin),
        list_digital_twins=AsyncMock(return_value=DigitalTwinListResponse(items=[twin])),
        modify_digital_twin=AsyncMock(return_value=modified),
        list_twin_versions=AsyncMock(
            return_value=DigitalTwinVersionListResponse(items=[twin, modified], total_versions=2)
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
            "/api/v1/simulations/twins",
            json={"workspace_id": str(workspace_id), "agent_fqn": "namespace.agent"},
        ).status_code
        == 201
    )
    assert client.get(f"/api/v1/simulations/twins/{twin_id}").status_code == 200
    assert client.get("/api/v1/simulations/twins").status_code == 200
    assert (
        client.patch(
            f"/api/v1/simulations/twins/{twin_id}",
            json={"modifications": [{"field": "model.name", "value": "new"}]},
        ).status_code
        == 201
    )
    assert client.get(f"/api/v1/simulations/twins/{twin_id}/versions").json()["total_versions"] == 2
