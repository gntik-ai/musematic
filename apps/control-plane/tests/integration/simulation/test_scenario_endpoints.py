from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.simulation.dependencies import get_simulation_service
from platform.simulation.models import SimulationRun, SimulationScenario
from platform.simulation.router import router
from platform.simulation.scenarios_service import SimulationScenariosService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.integration


class _InMemoryScenarioRepo:
    def __init__(self) -> None:
        self.scenarios: list[SimulationScenario] = []
        self.runs: list[SimulationRun] = []

    async def create_scenario(self, scenario: SimulationScenario) -> SimulationScenario:
        _stamp_model(scenario)
        self.scenarios.append(scenario)
        return scenario

    async def get_scenario(
        self,
        scenario_id: UUID,
        workspace_id: UUID,
    ) -> SimulationScenario | None:
        return next(
            (
                scenario
                for scenario in self.scenarios
                if scenario.id == scenario_id and scenario.workspace_id == workspace_id
            ),
            None,
        )

    async def list_scenarios(
        self,
        workspace_id: UUID,
        *,
        include_archived: bool = False,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[SimulationScenario], str | None]:
        del cursor
        items = [
            scenario
            for scenario in self.scenarios
            if scenario.workspace_id == workspace_id
            and (include_archived or scenario.archived_at is None)
        ]
        items = sorted(items, key=lambda item: (item.updated_at, item.id), reverse=True)
        return items[:limit], None

    async def update_scenario(
        self,
        scenario_id: UUID,
        workspace_id: UUID,
        values: dict[str, Any],
    ) -> SimulationScenario | None:
        scenario = await self.get_scenario(scenario_id, workspace_id)
        if scenario is None:
            return None
        for key, value in values.items():
            setattr(scenario, key, value)
        scenario.updated_at = datetime.now(UTC)
        return scenario

    async def archive_scenario(
        self,
        scenario_id: UUID,
        workspace_id: UUID,
    ) -> SimulationScenario | None:
        return await self.update_scenario(
            scenario_id,
            workspace_id,
            {"archived_at": datetime.now(UTC)},
        )

    async def create_run(self, run: SimulationRun) -> SimulationRun:
        _stamp_model(run)
        self.runs.append(run)
        return run

    async def set_status_cache(self, run_id: UUID, status_dict: dict[str, Any]) -> None:
        del run_id, status_dict


class _FakeRunner:
    def __init__(self, repo: _InMemoryScenarioRepo) -> None:
        self.repo = repo

    async def create(self, **kwargs: Any) -> SimulationRun:
        return await self.repo.create_run(
            SimulationRun(
                workspace_id=kwargs["workspace_id"],
                name=kwargs["name"],
                description=kwargs["description"],
                digital_twin_ids=[str(item) for item in kwargs["digital_twin_ids"]],
                scenario_config=kwargs["scenario_config"],
                isolation_policy_id=kwargs["isolation_policy_id"],
                scenario_id=kwargs["scenario_id"],
                controller_run_id=f"controller-{len(self.repo.runs) + 1}",
                status="provisioning",
                results={"provisioning_events": []},
                initiated_by=kwargs["initiated_by"],
            )
        )


def _stamp_model(model: Any) -> None:
    now = datetime.now(UTC)
    if getattr(model, "id", None) is None:
        model.id = uuid4()
    if getattr(model, "created_at", None) is None:
        model.created_at = now
    model.updated_at = now


def _build_app(service: SimulationScenariosService, user_id: UUID, workspace_id: UUID) -> FastAPI:
    app = FastAPI()
    app.state.clients = {}
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_simulation_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(user_id),
        "workspace_id": str(workspace_id),
    }
    return app


def _scenario_payload(workspace_id: UUID) -> dict[str, Any]:
    return {
        "workspace_id": str(workspace_id),
        "name": "Checkout resilience",
        "description": "Reusable checkout scenario",
        "agents_config": {"agents": ["registry:checkout"]},
        "mock_set_config": {"llm": "mock"},
        "input_distribution": {"kind": "fixed", "value": "checkout"},
        "twin_fidelity": {"data_source": "synthetic", "tools": "mock"},
        "success_criteria": [{"metric": "success_rate", "operator": ">=", "value": 0.98}],
    }


@pytest.mark.asyncio
async def test_scenario_crud_archive_and_run_queues_linked_runs() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    repo = _InMemoryScenarioRepo()
    service = SimulationScenariosService(
        repository=repo,  # type: ignore[arg-type]
        runner=_FakeRunner(repo),  # type: ignore[arg-type]
        settings=SimpleNamespace(simulation=SimpleNamespace(max_duration_seconds=3600)),  # type: ignore[arg-type]
    )
    app = _build_app(service, user_id, workspace_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/simulations/scenarios",
            json=_scenario_payload(workspace_id),
        )
        scenario_id = created.json()["id"]
        listed = await client.get("/api/v1/simulations/scenarios")
        fetched = await client.get(f"/api/v1/simulations/scenarios/{scenario_id}")
        updated = await client.put(
            f"/api/v1/simulations/scenarios/{scenario_id}",
            json={"name": "Checkout resilience v2"},
        )
        queued = await client.post(
            f"/api/v1/simulations/scenarios/{scenario_id}/run",
            json={"iterations": 2, "use_real_llm": False},
        )
        archived = await client.delete(f"/api/v1/simulations/scenarios/{scenario_id}")
        listed_active = await client.get("/api/v1/simulations/scenarios")
        listed_all = await client.get(
            "/api/v1/simulations/scenarios",
            params={"include_archived": "true"},
        )

    assert created.status_code == 201
    assert created.json()["created_by"] == str(user_id)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [scenario_id]
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Checkout resilience"
    assert updated.status_code == 200
    assert updated.json()["name"] == "Checkout resilience v2"
    assert queued.status_code == 202
    assert queued.json()["iterations"] == 2
    assert len(queued.json()["queued_runs"]) == 2
    assert [str(run.scenario_id) for run in repo.runs] == [scenario_id, scenario_id]
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert listed_active.json()["items"] == []
    assert [item["id"] for item in listed_all.json()["items"]] == [scenario_id]
