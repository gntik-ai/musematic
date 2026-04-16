from __future__ import annotations

from datetime import UTC, datetime
from platform.simulation.coordination.runner import SimulationRunner
from platform.simulation.exceptions import (
    SimulationInfrastructureUnavailableError,
    SimulationNotCancellableError,
)
from platform.simulation.models import SimulationRun
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


class FakeRepository:
    def __init__(self) -> None:
        self.runs: dict[object, SimulationRun] = {}
        self.cache: dict[object, dict[str, object]] = {}

    async def create_run(self, run: SimulationRun) -> SimulationRun:
        run.id = uuid4()
        run.created_at = datetime.now(UTC)
        run.updated_at = run.created_at
        self.runs[run.id] = run
        return run

    async def get_run(self, run_id: object, workspace_id: object) -> SimulationRun | None:
        run = self.runs.get(run_id)
        if run is None or run.workspace_id != workspace_id:
            return None
        return run

    async def update_run_status(
        self,
        run_id: object,
        workspace_id: object,
        status: str,
        *,
        results: dict[str, object] | None = None,
    ) -> SimulationRun | None:
        run = await self.get_run(run_id, workspace_id)
        if run is None:
            return None
        run.status = status
        run.results = results if results is not None else run.results
        run.completed_at = datetime.now(UTC)
        return run

    async def set_status_cache(self, run_id: object, status_dict: dict[str, object]) -> None:
        self.cache[run_id] = status_dict


class FakePublisher:
    def __init__(self) -> None:
        self.created: list[object] = []
        self.cancelled: list[object] = []

    async def simulation_run_created(self, run_id, workspace_id, actor_id, controller_run_id):
        self.created.append((run_id, workspace_id, actor_id, controller_run_id))

    async def simulation_run_cancelled(self, run_id, workspace_id, actor_id=None):
        self.cancelled.append((run_id, workspace_id, actor_id))


@pytest.mark.asyncio
async def test_create_dispatches_controller_and_persists_status() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    twin_id = uuid4()
    repository = FakeRepository()
    controller = SimpleNamespace(
        create_simulation=AsyncMock(
            return_value={"controller_run_id": "ctrl-1", "provisioning_events": ["queued"]}
        )
    )
    publisher = FakePublisher()
    runner = SimulationRunner(
        repository=repository,
        controller_client=controller,
        publisher=publisher,
    )

    run = await runner.create(
        workspace_id=workspace_id,
        name="scenario",
        description=None,
        digital_twin_ids=[twin_id],
        twin_configs=[{"twin_id": str(twin_id)}],
        scenario_config={"duration_seconds": 60},
        max_duration_seconds=60,
        isolation_policy_id=None,
        initiated_by=actor_id,
    )

    controller.create_simulation.assert_awaited_once_with(
        workspace_id=workspace_id,
        twin_configs=[{"twin_id": str(twin_id)}],
        scenario_config={"duration_seconds": 60},
        max_duration_seconds=60,
    )
    assert run.status == "provisioning"
    assert run.controller_run_id == "ctrl-1"
    assert repository.cache[run.id]["current_step"] == "provisioning"
    assert publisher.created == [(run.id, workspace_id, actor_id, "ctrl-1")]


@pytest.mark.asyncio
async def test_cancel_only_allows_running_or_provisioning_runs() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    repository = FakeRepository()
    publisher = FakePublisher()
    controller = SimpleNamespace(cancel_simulation=AsyncMock())
    run = await repository.create_run(
        SimulationRun(
            workspace_id=workspace_id,
            name="scenario",
            digital_twin_ids=[],
            scenario_config={},
            status="running",
            controller_run_id="ctrl-1",
            initiated_by=actor_id,
        )
    )
    runner = SimulationRunner(
        repository=repository,
        controller_client=controller,
        publisher=publisher,
    )

    cancelled = await runner.cancel(run.id, workspace_id, actor_id=actor_id)

    controller.cancel_simulation.assert_awaited_once_with("ctrl-1")
    assert cancelled.status == "cancelled"
    assert publisher.cancelled == [(run.id, workspace_id, actor_id)]

    run.status = "completed"
    with pytest.raises(SimulationNotCancellableError):
        await runner.cancel(run.id, workspace_id, actor_id=actor_id)


@pytest.mark.asyncio
async def test_create_raises_infrastructure_unavailable_when_controller_fails() -> None:
    runner = SimulationRunner(
        repository=FakeRepository(),
        controller_client=SimpleNamespace(create_simulation=AsyncMock(side_effect=RuntimeError("down"))),
        publisher=FakePublisher(),
    )

    with pytest.raises(SimulationInfrastructureUnavailableError) as exc_info:
        await runner.create(
            workspace_id=uuid4(),
            name="scenario",
            description=None,
            digital_twin_ids=[uuid4()],
            twin_configs=[],
            scenario_config={},
            max_duration_seconds=1,
            isolation_policy_id=None,
            initiated_by=uuid4(),
        )

    assert exc_info.value.status_code == 409
