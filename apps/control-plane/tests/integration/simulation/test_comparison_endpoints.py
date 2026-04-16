from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.simulation.dependencies import get_simulation_service
from platform.simulation.router import router
from platform.simulation.schemas import SimulationComparisonReportResponse
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_comparison_create_and_get_contracts() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    run_id = uuid4()
    secondary_run_id = uuid4()
    report_id = uuid4()
    report = SimulationComparisonReportResponse(
        report_id=report_id,
        comparison_type="simulation_vs_simulation",
        primary_run_id=run_id,
        secondary_run_id=secondary_run_id,
        production_baseline_period=None,
        prediction_id=None,
        status="completed",
        compatible=True,
        incompatibility_reasons=[],
        metric_differences=[{"metric": "quality_score", "direction": "better"}],
        overall_verdict="primary_better",
        created_at=datetime.now(UTC),
    )
    service = SimpleNamespace(
        create_comparison_report=AsyncMock(return_value=report),
        get_comparison_report=AsyncMock(return_value=report),
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
            f"/api/v1/simulations/{run_id}/compare",
            json={
                "workspace_id": str(workspace_id),
                "comparison_type": "simulation_vs_simulation",
                "secondary_run_id": str(secondary_run_id),
            },
        ).status_code
        == 202
    )
    response = client.get(f"/api/v1/simulations/comparisons/{report_id}")
    assert response.status_code == 200
    assert response.json()["overall_verdict"] == "primary_better"
