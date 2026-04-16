from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.simulation.dependencies import get_simulation_service
from platform.simulation.router import router
from platform.simulation.schemas import BehavioralPredictionResponse
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_prediction_create_and_get_contracts() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    twin_id = uuid4()
    prediction_id = uuid4()
    prediction = BehavioralPredictionResponse(
        prediction_id=prediction_id,
        digital_twin_id=twin_id,
        status="pending",
        condition_modifiers={"load_factor": 2.0},
        predicted_metrics=None,
        confidence_level=None,
        history_days_used=0,
        accuracy_report=None,
        created_at=datetime.now(UTC),
    )
    service = SimpleNamespace(
        create_behavioral_prediction=AsyncMock(return_value=prediction),
        get_behavioral_prediction=AsyncMock(
            return_value=prediction.model_copy(
                update={
                    "status": "completed",
                    "confidence_level": "high",
                    "history_days_used": 30,
                    "predicted_metrics": {"quality_score": {"predicted_value": 0.9}},
                }
            )
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
            f"/api/v1/simulations/twins/{twin_id}/predict",
            json={"workspace_id": str(workspace_id), "condition_modifiers": {"load_factor": 2.0}},
        ).status_code
        == 202
    )
    response = client.get(f"/api/v1/simulations/predictions/{prediction_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
