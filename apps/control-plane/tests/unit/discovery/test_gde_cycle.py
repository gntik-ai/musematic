from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.discovery.gde.cycle import GDECycleOrchestrator
from platform.discovery.models import DiscoverySession, GDECycle, Hypothesis
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_run_cycle_generates_critiques_tournament_and_converges() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    session = DiscoverySession(
        id=session_id,
        workspace_id=workspace_id,
        research_question="why",
        corpus_refs=[],
        config={"max_cycles": 10},
        status="active",
        current_cycle=0,
        initiated_by=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    created_cycles: list[GDECycle] = []

    async def create_cycle(row):
        row.id = uuid4()
        row.created_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        created_cycles.append(row)
        return row

    repo = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        create_cycle=AsyncMock(side_effect=create_cycle),
        create_hypothesis=AsyncMock(side_effect=lambda row: _with_identity(row)),
        list_active_hypotheses=AsyncMock(return_value=[]),
        update_session_status=AsyncMock(),
        complete_cycle=AsyncMock(side_effect=lambda row, **values: _assign(row, values)),
    )
    elo = SimpleNamespace(
        update_redis_leaderboard=AsyncMock(),
        persist_elo_score=AsyncMock(),
        get_leaderboard=AsyncMock(return_value=[SimpleNamespace(elo_score=1000.0)]),
    )
    tournament = SimpleNamespace(elo_engine=elo, run_round=AsyncMock())
    critique = SimpleNamespace(critique_hypothesis=AsyncMock())
    publisher = SimpleNamespace(
        hypothesis_generated=AsyncMock(),
        cycle_completed=AsyncMock(),
        session_converged=AsyncMock(),
    )
    orchestrator = GDECycleOrchestrator(
        repository=repo,
        settings=PlatformSettings.model_validate({"DISCOVERY_CONVERGENCE_THRESHOLD": 0.01}),
        publisher=publisher,
        tournament=tournament,
        critique_evaluator=critique,
        workflow_service=None,
    )

    cycle = await orchestrator.run_cycle(
        session_id=session_id,
        workspace_id=workspace_id,
        actor_id=uuid4(),
    )

    assert cycle.status == "completed"
    assert cycle.converged is True
    assert repo.create_hypothesis.await_count == 3
    assert critique.critique_hypothesis.await_count == 3
    publisher.session_converged.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_cycle_workflow_generation_and_iteration_limit() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    session = DiscoverySession(
        id=session_id,
        workspace_id=workspace_id,
        research_question="why",
        corpus_refs=[],
        config={"max_cycles": 1},
        status="active",
        current_cycle=0,
        initiated_by=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    cycle = GDECycle(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=session_id,
        cycle_number=1,
        status="running",
        generation_count=0,
        debate_record={},
        refinement_count=0,
        converged=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    active: list[Hypothesis] = []

    async def create_hypothesis(row):
        row.id = uuid4()
        row.created_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        active.append(row)
        return row

    repo = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        create_cycle=AsyncMock(return_value=cycle),
        create_hypothesis=AsyncMock(side_effect=create_hypothesis),
        list_active_hypotheses=AsyncMock(side_effect=lambda *_: active),
        update_session_status=AsyncMock(),
        complete_cycle=AsyncMock(side_effect=lambda row, **values: _assign(row, values)),
    )
    workflow = SimpleNamespace(
        create_execution=AsyncMock(
            side_effect=[
                {"hypotheses": [{"title": "H1", "description": "D", "confidence": 0.7}]},
                {"debate": "ok"},
            ]
        )
    )
    elo = SimpleNamespace(
        update_redis_leaderboard=AsyncMock(),
        persist_elo_score=AsyncMock(),
        get_leaderboard=AsyncMock(return_value=[]),
    )
    orchestrator = GDECycleOrchestrator(
        repository=repo,
        settings=PlatformSettings(),
        publisher=SimpleNamespace(
            hypothesis_generated=AsyncMock(),
            cycle_completed=AsyncMock(),
            session_converged=AsyncMock(),
        ),
        tournament=SimpleNamespace(elo_engine=elo, run_round=AsyncMock()),
        critique_evaluator=SimpleNamespace(critique_hypothesis=AsyncMock()),
        workflow_service=workflow,
    )

    completed = await orchestrator.run_cycle(
        session_id=session_id,
        workspace_id=workspace_id,
        actor_id=uuid4(),
    )

    assert completed.generation_count == 1
    repo.update_session_status.assert_awaited_with(
        session_id,
        workspace_id,
        "iteration_limit_reached",
        current_cycle=1,
        convergence_metrics={"last_delta": None},
    )


@pytest.mark.asyncio
async def test_run_cycle_errors_when_session_missing() -> None:
    orchestrator = GDECycleOrchestrator(
        repository=SimpleNamespace(get_session=AsyncMock(return_value=None)),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        workflow_service=None,
    )

    with pytest.raises(ValueError, match="Session not found"):
        await orchestrator.run_cycle(session_id=uuid4(), workspace_id=uuid4(), actor_id=uuid4())


def _with_identity(row):
    row.id = uuid4()
    row.created_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    return row


def _assign(row, values):
    for key, value in values.items():
        setattr(row, key, value)
    return row
