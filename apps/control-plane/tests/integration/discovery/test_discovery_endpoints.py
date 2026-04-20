from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.discovery.dependencies import get_discovery_service
from platform.discovery.router import router
from platform.discovery.schemas import (
    ClusterListResponse,
    CritiqueListResponse,
    DiscoveryExperimentResponse,
    DiscoverySessionListResponse,
    DiscoverySessionResponse,
    HypothesisListResponse,
    HypothesisResponse,
    LeaderboardResponse,
    ProvenanceGraphResponse,
    ProximityGraphResponse,
    ProximityWorkspaceSettingsResponse,
    RecomputeEnqueuedResponse,
    TournamentRoundListResponse,
)
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_discovery_endpoint_contracts() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    session_id = uuid4()
    hypothesis_id = uuid4()
    experiment_id = uuid4()
    now = datetime.now(UTC)
    session = DiscoverySessionResponse(
        session_id=session_id,
        workspace_id=workspace_id,
        research_question="rq",
        corpus_refs=[],
        config={},
        status="active",
        current_cycle=0,
        convergence_metrics=None,
        initiated_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    hypothesis = HypothesisResponse(
        hypothesis_id=hypothesis_id,
        session_id=session_id,
        title="h",
        description="d",
        reasoning="r",
        confidence=0.8,
        generating_agent_fqn="agent",
        status="active",
        elo_score=1010.0,
        rank=1,
        wins=1,
        losses=0,
        draws=0,
        cluster_id="cluster_1",
        created_at=now,
    )
    experiment = DiscoveryExperimentResponse(
        experiment_id=experiment_id,
        hypothesis_id=hypothesis_id,
        session_id=session_id,
        plan={"code": "print(1)"},
        governance_status="approved",
        governance_violations=[],
        execution_status="completed",
        sandbox_execution_id="exec",
        results={"stdout": "ok"},
        designed_by_agent_fqn="designer",
        created_at=now,
        updated_at=now,
    )
    service = SimpleNamespace(
        start_session=AsyncMock(return_value=session),
        get_session=AsyncMock(return_value=session),
        list_sessions=AsyncMock(return_value=DiscoverySessionListResponse(items=[session])),
        halt_session=AsyncMock(return_value=session.model_copy(update={"status": "halted"})),
        list_hypotheses=AsyncMock(return_value=HypothesisListResponse(items=[hypothesis])),
        get_hypothesis=AsyncMock(return_value=hypothesis),
        get_critiques=AsyncMock(return_value=CritiqueListResponse(items=[], aggregated=None)),
        get_leaderboard=AsyncMock(
            return_value=LeaderboardResponse(
                items=[],
                session_id=session_id,
                total_hypotheses=0,
            )
        ),
        list_tournament_rounds=AsyncMock(return_value=TournamentRoundListResponse(items=[])),
        design_experiment=AsyncMock(return_value=experiment),
        get_experiment=AsyncMock(return_value=experiment),
        execute_experiment=AsyncMock(return_value=experiment),
        get_hypothesis_provenance=AsyncMock(
            return_value=ProvenanceGraphResponse(hypothesis_id=hypothesis_id, nodes=[], edges=[])
        ),
        get_proximity_clusters=AsyncMock(
            return_value=ClusterListResponse(items=[], landscape_status="low_data")
        ),
        trigger_proximity_computation=AsyncMock(
            return_value=ClusterListResponse(items=[], landscape_status="low_data")
        ),
        get_proximity_graph=AsyncMock(
            return_value=ProximityGraphResponse(
                workspace_id=workspace_id,
                status="computed",
                saturation_indicator="normal",
                current_embedded_count=1,
                nodes=[],
            )
        ),
        get_workspace_proximity_settings=AsyncMock(
            return_value=ProximityWorkspaceSettingsResponse(
                workspace_id=workspace_id,
                bias_enabled=True,
                recompute_interval_minutes=15,
            )
        ),
        update_workspace_proximity_settings=AsyncMock(
            return_value=ProximityWorkspaceSettingsResponse(
                workspace_id=workspace_id,
                bias_enabled=False,
                recompute_interval_minutes=30,
            )
        ),
        enqueue_workspace_recompute=AsyncMock(return_value=RecomputeEnqueuedResponse()),
    )
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.dependency_overrides[get_discovery_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
    }
    client = TestClient(app)

    assert client.get("/api/v1/discovery/sessions").status_code == 200
    assert client.get(f"/api/v1/discovery/sessions/{session_id}").status_code == 200
    assert (
        client.post(
            f"/api/v1/discovery/sessions/{session_id}/halt", json={"reason": "x"}
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/discovery/sessions/{session_id}/hypotheses").status_code == 200
    assert client.get(f"/api/v1/discovery/hypotheses/{hypothesis_id}").status_code == 200
    assert client.get(f"/api/v1/discovery/hypotheses/{hypothesis_id}/critiques").status_code == 200
    assert client.get(f"/api/v1/discovery/sessions/{session_id}/leaderboard").status_code == 200
    assert (
        client.get(f"/api/v1/discovery/sessions/{session_id}/tournament-rounds").status_code == 200
    )
    assert (
        client.post(
            f"/api/v1/discovery/hypotheses/{hypothesis_id}/experiment",
            json={"workspace_id": str(workspace_id)},
        ).status_code
        == 201
    )
    assert client.get(f"/api/v1/discovery/experiments/{experiment_id}").status_code == 200
    assert client.post(f"/api/v1/discovery/experiments/{experiment_id}/execute").status_code == 202
    assert client.get(f"/api/v1/discovery/hypotheses/{hypothesis_id}/provenance").status_code == 200
    assert client.get(f"/api/v1/discovery/sessions/{session_id}/clusters").status_code == 200
    assert (
        client.post(f"/api/v1/discovery/sessions/{session_id}/compute-proximity").status_code == 202
    )


def test_discovery_proximity_workspace_endpoints_and_authorization() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = SimpleNamespace(
        get_proximity_graph=AsyncMock(
            return_value=ProximityGraphResponse(
                workspace_id=workspace_id,
                status="computed",
                saturation_indicator="normal",
                current_embedded_count=2,
                nodes=[],
            )
        ),
        get_workspace_proximity_settings=AsyncMock(
            return_value=ProximityWorkspaceSettingsResponse(
                workspace_id=workspace_id,
                bias_enabled=True,
                recompute_interval_minutes=15,
            )
        ),
        update_workspace_proximity_settings=AsyncMock(
            return_value=ProximityWorkspaceSettingsResponse(
                workspace_id=workspace_id,
                bias_enabled=False,
                recompute_interval_minutes=30,
            )
        ),
        enqueue_workspace_recompute=AsyncMock(return_value=RecomputeEnqueuedResponse()),
    )
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.dependency_overrides[get_discovery_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
        "roles": [],
    }
    client = TestClient(app)

    assert client.get(f"/api/v1/discovery/{workspace_id}/proximity-graph").status_code == 200
    assert client.get(f"/api/v1/discovery/{workspace_id}/proximity-settings").status_code == 200
    assert (
        client.patch(
            f"/api/v1/discovery/{workspace_id}/proximity-settings",
            json={"bias_enabled": False},
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/v1/discovery/{workspace_id}/proximity-graph/recompute").status_code
        == 403
    )

    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
        "roles": [{"role": "workspace_admin", "workspace_id": str(workspace_id)}],
    }

    updated = client.patch(
        f"/api/v1/discovery/{workspace_id}/proximity-settings",
        json={"bias_enabled": False, "recompute_interval_minutes": 30},
    )
    recompute = client.post(f"/api/v1/discovery/{workspace_id}/proximity-graph/recompute")

    assert updated.status_code == 200
    assert updated.json()["bias_enabled"] is False
    assert recompute.status_code == 202
    service.update_workspace_proximity_settings.assert_awaited_once()
    service.enqueue_workspace_recompute.assert_awaited_once_with(workspace_id, actor_id)
