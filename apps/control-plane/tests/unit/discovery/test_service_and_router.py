from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.discovery.dependencies import get_discovery_service
from platform.discovery.models import DiscoverySession
from platform.discovery.router import _workspace_id, router
from platform.discovery.schemas import DiscoverySessionResponse, GDECycleResponse
from platform.discovery.service import DiscoveryService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_service_starts_lists_and_halts_session() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    session_row = DiscoverySession(
        id=uuid4(),
        workspace_id=workspace_id,
        research_question="rq",
        corpus_refs=[],
        config={"k_factor": 32},
        status="active",
        current_cycle=0,
        initiated_by=actor_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo = SimpleNamespace(
        create_session=AsyncMock(return_value=session_row),
        list_sessions=AsyncMock(return_value=([session_row], None)),
        update_session_status=AsyncMock(return_value=_assign(session_row, {"status": "halted"})),
    )
    service = DiscoveryService(
        repository=repo,
        settings=SimpleNamespace(),
        publisher=SimpleNamespace(session_started=AsyncMock(), session_halted=AsyncMock()),
        elo_engine=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
    )
    from platform.discovery.schemas import DiscoverySessionCreateRequest

    created = await service.start_session(
        DiscoverySessionCreateRequest(
            workspace_id=workspace_id,
            research_question="rq",
        ),
        actor_id,
    )
    listed = await service.list_sessions(workspace_id, status=None, limit=20, cursor=None)
    halted = await service.halt_session(session_row.id, workspace_id, actor_id, "stop")

    assert created.session_id == session_row.id
    assert listed.items[0].session_id == session_row.id
    assert halted.status == "halted"


def test_router_session_and_cycle_endpoints() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    actor_id = uuid4()
    service = SimpleNamespace(
        start_session=AsyncMock(
            return_value=DiscoverySessionResponse(
                session_id=session_id,
                workspace_id=workspace_id,
                research_question="rq",
                corpus_refs=[],
                config={},
                status="active",
                current_cycle=0,
                convergence_metrics=None,
                initiated_by=actor_id,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ),
        run_gde_cycle=AsyncMock(
            return_value=GDECycleResponse(
                cycle_id=uuid4(),
                session_id=session_id,
                cycle_number=1,
                status="completed",
                generation_count=3,
                debate_record={},
                refinement_count=0,
                convergence_metric=0.0,
                converged=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_discovery_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
    }
    client = TestClient(app)

    created = client.post(
        "/api/v1/discovery/sessions",
        json={"workspace_id": str(workspace_id), "research_question": "rq"},
    )
    cycle = client.post(f"/api/v1/discovery/sessions/{session_id}/cycle")

    assert created.status_code == 201
    assert created.json()["session_id"] == str(session_id)
    assert cycle.status_code == 202
    assert cycle.json()["converged"] is True


def test_workspace_id_requires_query_or_claim() -> None:
    assert _workspace_id({"workspace_id": str(uuid4())}, None)
    with pytest.raises(ValueError, match="workspace_id"):
        _workspace_id({}, None)


def _assign(row, values):
    for key, value in values.items():
        setattr(row, key, value)
    return row
