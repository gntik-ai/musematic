from __future__ import annotations

from datetime import UTC, datetime
from platform.discovery.exceptions import (
    DiscoveryNotFoundError,
    InsufficientHypothesesError,
    SessionAlreadyRunningError,
)
from platform.discovery.models import (
    DiscoveryExperiment,
    DiscoverySession,
    EloScore,
    GDECycle,
    Hypothesis,
    HypothesisCluster,
    TournamentRound,
)
from platform.discovery.service import DiscoveryService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_service_query_and_action_paths() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    hypothesis_id = uuid4()
    now = datetime.now(UTC)
    session = DiscoverySession(
        id=session_id,
        workspace_id=workspace_id,
        research_question="rq",
        corpus_refs=[],
        config={},
        status="active",
        current_cycle=0,
        initiated_by=uuid4(),
        created_at=now,
        updated_at=now,
    )
    hypothesis = Hypothesis(
        id=hypothesis_id,
        workspace_id=workspace_id,
        session_id=session_id,
        title="h",
        description="d",
        reasoning="r",
        confidence=0.7,
        generating_agent_fqn="agent",
        status="active",
        created_at=now,
        updated_at=now,
    )
    elo = EloScore(
        id=uuid4(),
        workspace_id=workspace_id,
        hypothesis_id=hypothesis_id,
        session_id=session_id,
        current_score=1000.0,
        wins=1,
        losses=0,
        draws=0,
        score_history=[],
        created_at=now,
        updated_at=now,
    )
    experiment = DiscoveryExperiment(
        id=uuid4(),
        workspace_id=workspace_id,
        hypothesis_id=hypothesis_id,
        session_id=session_id,
        plan={},
        governance_status="approved",
        governance_violations=[],
        execution_status="not_started",
        designed_by_agent_fqn="designer",
        created_at=now,
        updated_at=now,
    )
    cluster = HypothesisCluster(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=session_id,
        cluster_label="cluster_1",
        centroid_description="c",
        hypothesis_count=1,
        density_metric=1.0,
        classification="over_explored",
        hypothesis_ids=[str(hypothesis_id)],
        computed_at=now,
        created_at=now,
        updated_at=now,
    )
    cycle = GDECycle(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=session_id,
        cycle_number=1,
        status="completed",
        generation_count=1,
        debate_record={},
        refinement_count=0,
        converged=False,
        created_at=now,
        updated_at=now,
    )
    repo = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        get_running_cycle=AsyncMock(return_value=None),
        list_active_hypotheses=AsyncMock(
            return_value=[hypothesis, _hypothesis(workspace_id, session_id)]
        ),
        get_cycle=AsyncMock(return_value=cycle),
        list_hypotheses=AsyncMock(return_value=([hypothesis], None)),
        get_hypothesis=AsyncMock(return_value=hypothesis),
        get_elo_score=AsyncMock(return_value=elo),
        list_elo_scores=AsyncMock(return_value={hypothesis_id: elo}),
        list_tournament_rounds=AsyncMock(
            return_value=(
                [
                    TournamentRound(
                        id=uuid4(),
                        workspace_id=workspace_id,
                        session_id=session_id,
                        round_number=1,
                        pairwise_results=[],
                        elo_changes=[],
                        status="completed",
                        created_at=now,
                        updated_at=now,
                    )
                ],
                None,
            )
        ),
        list_critiques=AsyncMock(return_value=[]),
        get_experiment=AsyncMock(return_value=experiment),
        list_clusters=AsyncMock(return_value=[cluster]),
    )
    top_entry = SimpleNamespace(hypothesis_id=hypothesis_id, elo_score=1000.0, rank=1)
    service = DiscoveryService(
        repository=repo,
        settings=SimpleNamespace(),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(get_leaderboard=AsyncMock(return_value=[top_entry])),
        tournament=SimpleNamespace(run_round=AsyncMock()),
        critique_evaluator=SimpleNamespace(critique_hypothesis=AsyncMock()),
        gde_orchestrator=SimpleNamespace(run_cycle=AsyncMock(return_value=cycle)),
        experiment_designer=SimpleNamespace(
            design=AsyncMock(return_value=experiment),
            execute=AsyncMock(return_value=experiment),
        ),
        provenance_graph=SimpleNamespace(
            query_provenance=AsyncMock(
                return_value=SimpleNamespace(hypothesis_id=hypothesis_id, nodes=[], edges=[])
            )
        ),
        proximity_clustering=SimpleNamespace(
            compute=AsyncMock(
                return_value=SimpleNamespace(
                    clusters=[cluster],
                    status="saturated",
                )
            )
        ),
    )

    assert (await service.get_session(session_id, workspace_id)).session_id == session_id
    await service.run_tournament_round(session_id, workspace_id, uuid4())
    assert (await service.run_gde_cycle(session_id, workspace_id, uuid4())).cycle_id == cycle.id
    assert (await service.get_cycle(cycle.id, workspace_id)).cycle_id == cycle.id
    assert (
        await service.list_hypotheses(
            session_id, workspace_id, status=None, order_by="created_at", limit=10, cursor=None
        )
    ).items
    assert (
        await service.get_hypothesis(hypothesis_id, workspace_id)
    ).hypothesis_id == hypothesis_id
    assert (await service.get_top_hypotheses(session_id, workspace_id))[
        0
    ].hypothesis_id == hypothesis_id
    assert (await service.get_leaderboard(session_id, workspace_id, 5)).total_hypotheses == 1
    assert (
        await service.list_tournament_rounds(session_id, workspace_id, limit=10, cursor=None)
    ).items
    assert (await service.get_critiques(hypothesis_id, workspace_id)).items == []
    assert (
        await service.submit_for_critique(hypothesis_id, workspace_id, ["r"], uuid4())
    ).items == []
    assert (
        await service.design_experiment(hypothesis_id, workspace_id, uuid4())
    ).experiment_id == experiment.id
    assert (
        await service.get_experiment(experiment.id, workspace_id)
    ).experiment_id == experiment.id
    assert (
        await service.execute_experiment(experiment.id, workspace_id)
    ).experiment_id == experiment.id
    assert (
        await service.get_hypothesis_provenance(hypothesis_id, workspace_id, 3)
    ).hypothesis_id == hypothesis_id
    assert (
        await service.get_proximity_clusters(session_id, workspace_id)
    ).landscape_status == "saturated"
    assert (
        await service.trigger_proximity_computation(session_id, workspace_id)
    ).landscape_status == "saturated"
    assert await service.get_session_summary(session_id, workspace_id)


@pytest.mark.asyncio
async def test_service_errors_for_missing_and_insufficient_hypotheses() -> None:
    service = DiscoveryService(
        repository=SimpleNamespace(
            get_session=AsyncMock(return_value=None),
            list_active_hypotheses=AsyncMock(return_value=[]),
        ),
        settings=SimpleNamespace(),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
    )

    with pytest.raises(DiscoveryNotFoundError):
        await service.get_session(uuid4(), uuid4())
    with pytest.raises(InsufficientHypothesesError):
        await service.run_tournament_round(uuid4(), uuid4(), uuid4())


@pytest.mark.asyncio
async def test_service_additional_error_and_empty_paths() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    inactive = DiscoverySession(
        id=session_id,
        workspace_id=workspace_id,
        research_question="rq",
        corpus_refs=[],
        config={},
        status="halted",
        current_cycle=0,
        initiated_by=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo = SimpleNamespace(
        update_session_status=AsyncMock(return_value=None),
        get_session=AsyncMock(return_value=inactive),
        get_running_cycle=AsyncMock(return_value=SimpleNamespace()),
        get_cycle=AsyncMock(return_value=None),
        get_hypothesis=AsyncMock(return_value=None),
        get_experiment=AsyncMock(return_value=None),
        list_elo_scores=AsyncMock(return_value={}),
        list_clusters=AsyncMock(return_value=[]),
    )
    service = DiscoveryService(
        repository=repo,
        settings=SimpleNamespace(),
        publisher=SimpleNamespace(session_halted=AsyncMock()),
        elo_engine=SimpleNamespace(get_leaderboard=AsyncMock(return_value=[])),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
    )

    with pytest.raises(DiscoveryNotFoundError):
        await service.halt_session(session_id, workspace_id, uuid4(), "x")
    with pytest.raises(SessionAlreadyRunningError):
        await service.run_gde_cycle(session_id, workspace_id, uuid4())
    inactive.status = "active"
    with pytest.raises(SessionAlreadyRunningError):
        await service.run_gde_cycle(session_id, workspace_id, uuid4())
    repo.get_running_cycle.return_value = None
    with pytest.raises(RuntimeError, match="GDE"):
        await service.run_gde_cycle(session_id, workspace_id, uuid4())
    with pytest.raises(DiscoveryNotFoundError):
        await service.get_cycle(uuid4(), workspace_id)
    assert await service.get_top_hypotheses(session_id, workspace_id) == []
    assert (
        await service.get_proximity_clusters(session_id, workspace_id)
    ).landscape_status == "low_data"
    assert (
        await service.trigger_proximity_computation(session_id, workspace_id)
    ).landscape_status == "low_data"
    repo.get_session.return_value = None
    assert await service.get_session_summary(session_id, workspace_id) is None
    with pytest.raises(DiscoveryNotFoundError):
        await service.get_hypothesis(uuid4(), workspace_id)
    with pytest.raises(DiscoveryNotFoundError):
        await service.get_experiment(uuid4(), workspace_id)
    with pytest.raises(DiscoveryNotFoundError):
        await service.execute_experiment(uuid4(), workspace_id)


def _hypothesis(workspace_id, session_id):
    return Hypothesis(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=session_id,
        title="h2",
        description="d",
        reasoning="r",
        confidence=0.6,
        generating_agent_fqn="agent",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
