from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.discovery.exceptions import WorkspaceProximityRecomputeInFlightError
from platform.discovery.models import DiscoveryExperiment, DiscoveryWorkspaceSettings, Hypothesis
from platform.discovery.schemas import ProximityWorkspaceSettingsUpdateRequest
from platform.discovery.service import _RECOMPUTE_IN_FLIGHT, DiscoveryService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_get_proximity_graph_returns_pre_proximity_without_graph_service() -> None:
    workspace_id = uuid4()
    service = DiscoveryService(
        repository=SimpleNamespace(),
        settings=PlatformSettings.model_validate({"DISCOVERY_MIN_HYPOTHESES": 4}),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
    )

    response = await service.get_proximity_graph(
        workspace_id,
        session_id=None,
        include_edges=True,
        max_nodes=20,
    )

    assert response.status == "pre_proximity"
    assert response.min_hypotheses_required == 4
    assert response.current_embedded_count == 0


@pytest.mark.asyncio
async def test_workspace_settings_update_and_enqueue_recompute() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    pending = _hypothesis(workspace_id)
    current = DiscoveryWorkspaceSettings(
        workspace_id=workspace_id,
        bias_enabled=True,
        recompute_interval_minutes=15,
        last_recomputed_at=datetime.now(UTC),
        last_transition_summary={"clusters_newly_saturated": []},
    )
    updated = DiscoveryWorkspaceSettings(
        workspace_id=workspace_id,
        bias_enabled=False,
        recompute_interval_minutes=30,
        last_recomputed_at=current.last_recomputed_at,
        last_transition_summary=current.last_transition_summary,
    )
    repo = SimpleNamespace(
        upsert_workspace_settings=AsyncMock(return_value=updated),
        list_hypotheses_pending_embedding=AsyncMock(return_value=[pending]),
    )
    graph = SimpleNamespace(
        _get_or_create_workspace_settings=AsyncMock(return_value=current),
        index_hypothesis=AsyncMock(),
        recompute_workspace_graph=AsyncMock(),
    )
    service = DiscoveryService(
        repository=repo,
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
        proximity_graph_service=graph,
    )

    settings_response = await service.get_workspace_proximity_settings(workspace_id)
    updated_response = await service.update_workspace_proximity_settings(
        workspace_id,
        ProximityWorkspaceSettingsUpdateRequest(
            bias_enabled=False,
            recompute_interval_minutes=30,
        ),
        actor_id,
    )
    enqueue_response = await service.enqueue_workspace_recompute(workspace_id, actor_id)

    assert settings_response.bias_enabled is True
    assert updated_response.bias_enabled is False
    assert updated_response.recompute_interval_minutes == 30
    assert enqueue_response.enqueued is True
    graph.index_hypothesis.assert_awaited_once_with(pending.id)
    graph.recompute_workspace_graph.assert_awaited_once_with(workspace_id)


@pytest.mark.asyncio
async def test_enqueue_workspace_recompute_guards_conflicts_and_missing_service() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = DiscoveryService(
        repository=SimpleNamespace(),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
    )

    with pytest.raises(RuntimeError, match="Proximity graph service"):
        await service.enqueue_workspace_recompute(workspace_id, actor_id)

    conflict_service = DiscoveryService(
        repository=SimpleNamespace(),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
        proximity_graph_service=SimpleNamespace(),
    )
    _RECOMPUTE_IN_FLIGHT.add(workspace_id)
    try:
        with pytest.raises(WorkspaceProximityRecomputeInFlightError):
            await conflict_service.enqueue_workspace_recompute(workspace_id, actor_id)
    finally:
        _RECOMPUTE_IN_FLIGHT.discard(workspace_id)


@pytest.mark.asyncio
async def test_get_top_hypotheses_skips_missing_and_recompute_task_no_service() -> None:
    session_id = uuid4()
    workspace_id = uuid4()
    hypothesis_id = uuid4()
    service = DiscoveryService(
        repository=SimpleNamespace(
            list_elo_scores=AsyncMock(return_value={}),
            get_hypothesis=AsyncMock(return_value=None),
            list_active_workspace_ids=AsyncMock(side_effect=AssertionError("should not run")),
        ),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(
            get_leaderboard=AsyncMock(
                return_value=[
                    SimpleNamespace(hypothesis_id=hypothesis_id, elo_score=1000.0, rank=1)
                ]
            )
        ),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
    )

    top = await service.get_top_hypotheses(session_id, workspace_id, limit=5)
    await service.workspace_proximity_recompute_task()

    assert top == []


@pytest.mark.asyncio
async def test_experiment_operations_require_designer() -> None:
    workspace_id = uuid4()
    hypothesis = _hypothesis(workspace_id)
    experiment = DiscoveryExperiment(
        id=uuid4(),
        workspace_id=workspace_id,
        hypothesis_id=hypothesis.id,
        session_id=hypothesis.session_id,
        plan={},
        governance_status="approved",
        governance_violations=[],
        execution_status="not_started",
        designed_by_agent_fqn="designer",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo = SimpleNamespace(
        get_hypothesis=AsyncMock(return_value=hypothesis),
        get_experiment=AsyncMock(return_value=experiment),
    )
    service = DiscoveryService(
        repository=repo,
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
    )

    with pytest.raises(RuntimeError, match="Experiment designer"):
        await service.design_experiment(hypothesis.id, workspace_id, uuid4())
    with pytest.raises(RuntimeError, match="Experiment designer"):
        await service.execute_experiment(experiment.id, workspace_id)


def _hypothesis(workspace_id):
    return Hypothesis(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=uuid4(),
        title="hypothesis",
        description="description",
        reasoning="reasoning",
        confidence=0.7,
        generating_agent_fqn="agent",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_list_hypotheses_elo_desc_and_settings_error_paths() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    service = DiscoveryService(
        repository=SimpleNamespace(),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
    )
    service.get_top_hypotheses = AsyncMock(return_value=[])

    response = await service.list_hypotheses(
        session_id,
        workspace_id,
        status=None,
        order_by="elo_desc",
        limit=5,
        cursor=None,
    )

    assert response.items == []
    with pytest.raises(RuntimeError, match="Proximity graph service"):
        await service.get_workspace_proximity_settings(workspace_id)


@pytest.mark.asyncio
async def test_get_proximity_graph_delegates_when_graph_service_is_configured() -> None:
    workspace_id = uuid4()
    expected = SimpleNamespace(status="computed")
    graph = SimpleNamespace(compute_workspace_graph=AsyncMock(return_value=expected))
    service = DiscoveryService(
        repository=SimpleNamespace(),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        tournament=SimpleNamespace(),
        critique_evaluator=SimpleNamespace(),
        gde_orchestrator=None,
        experiment_designer=None,
        provenance_graph=SimpleNamespace(),
        proximity_clustering=None,
        proximity_graph_service=graph,
    )

    response = await service.get_proximity_graph(
        workspace_id,
        session_id=None,
        include_edges=False,
        max_nodes=25,
    )

    assert response is expected
    graph.compute_workspace_graph.assert_awaited_once_with(
        workspace_id,
        session_id=None,
        include_edges=False,
        max_nodes=25,
    )
