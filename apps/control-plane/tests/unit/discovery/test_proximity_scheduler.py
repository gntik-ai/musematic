from __future__ import annotations

from datetime import UTC, datetime
from platform.discovery.models import Hypothesis
from platform.discovery.proximity.scheduler import workspace_proximity_recompute_task
from platform.discovery.service import DiscoveryService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_scheduler_wrapper_delegates_to_service() -> None:
    service = SimpleNamespace(workspace_proximity_recompute_task=AsyncMock())

    await workspace_proximity_recompute_task(service, SimpleNamespace())

    service.workspace_proximity_recompute_task.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_service_workspace_recompute_task_isolates_failures() -> None:
    first_workspace = uuid4()
    second_workspace = uuid4()
    first_pending = _hypothesis(first_workspace)
    second_pending = _hypothesis(second_workspace)
    repo = SimpleNamespace(
        list_active_workspace_ids=AsyncMock(return_value=[first_workspace, second_workspace]),
        list_hypotheses_pending_embedding=AsyncMock(
            side_effect=[[first_pending], [second_pending]]
        ),
    )
    graph = SimpleNamespace(
        index_hypothesis=AsyncMock(side_effect=[RuntimeError("boom"), None]),
        recompute_workspace_graph=AsyncMock(),
    )
    service = DiscoveryService(
        repository=repo,
        settings=SimpleNamespace(),
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

    await service.workspace_proximity_recompute_task()

    assert repo.list_hypotheses_pending_embedding.await_args_list == [
        ((first_workspace,), {"limit": 100}),
        ((second_workspace,), {"limit": 100}),
    ]
    assert graph.index_hypothesis.await_args_list == [
        ((first_pending.id,), {}),
        ((second_pending.id,), {}),
    ]
    graph.recompute_workspace_graph.assert_awaited_once_with(second_workspace)


def _hypothesis(workspace_id):
    return Hypothesis(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=uuid4(),
        title="h",
        description="d",
        reasoning="r",
        confidence=0.5,
        generating_agent_fqn="agent",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
