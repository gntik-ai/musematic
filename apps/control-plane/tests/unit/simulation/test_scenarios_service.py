from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import ValidationError
from platform.simulation.exceptions import SimulationNotFoundError
from platform.simulation.scenarios_service import (
    SimulationScenariosService,
    _agent_fqns,
    _digital_twin_ids,
    _flatten_strings,
)
from platform.simulation.schemas import ScenarioCreate, ScenarioRunRequest, ScenarioUpdate
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest


class _RegistryStub:
    def __init__(self, known_fqns: set[str]) -> None:
        self.known_fqns = known_fqns

    async def get_agent_by_fqn(self, fqn: str) -> object | None:
        return object() if fqn in self.known_fqns else None


class _SyncRegistryStub:
    def resolve_fqn(self, fqn: str) -> object | None:
        return object() if fqn == "registry:known" else None


class _WorkflowStub:
    def __init__(self, result: object | None) -> None:
        self.result = result

    async def get_workflow_template(self, workflow_template_id: object) -> object | None:
        del workflow_template_id
        return self.result


class _NoResolverWorkflowStub:
    pass


class _RepositoryStub:
    def __init__(self, scenario: SimpleNamespace | None = None) -> None:
        self.scenario = scenario
        self.created: object | None = None
        self.updated_values: dict[str, Any] | None = None

    async def list_scenarios(
        self,
        workspace_id,
        *,
        include_archived: bool,
        limit: int,
        cursor: str | None,
    ):
        assert workspace_id == self.scenario.workspace_id
        assert (include_archived, limit, cursor) == (False, 25, "cursor-1")
        return [self.scenario], "next"

    async def get_scenario(self, scenario_id, workspace_id):
        if (
            self.scenario
            and self.scenario.id == scenario_id
            and self.scenario.workspace_id == workspace_id
        ):
            return self.scenario
        return None

    async def create_scenario(self, scenario):
        self.created = scenario
        scenario.id = uuid4()
        scenario.archived_at = None
        scenario.created_at = datetime.now(UTC)
        scenario.updated_at = datetime.now(UTC)
        return scenario

    async def update_scenario(self, scenario_id, workspace_id, values):
        assert self.scenario is not None
        assert scenario_id == self.scenario.id
        assert workspace_id == self.scenario.workspace_id
        self.updated_values = values
        for key, value in values.items():
            setattr(self.scenario, key, value)
        self.scenario.updated_at = datetime.now(UTC)
        return self.scenario

    async def archive_scenario(self, scenario_id, workspace_id):
        scenario = await self.get_scenario(scenario_id, workspace_id)
        if scenario is None:
            return None
        scenario.archived_at = datetime.now(UTC)
        return scenario


class _RunnerStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(id=uuid4())


def _service(
    *,
    registry_service: object | None = None,
    workflow_service: object | None = None,
) -> SimulationScenariosService:
    return SimulationScenariosService(
        repository=object(),  # type: ignore[arg-type]
        runner=object(),  # type: ignore[arg-type]
        settings=SimpleNamespace(simulation=SimpleNamespace(max_duration_seconds=3600)),  # type: ignore[arg-type]
        registry_service=registry_service,
        workflow_service=workflow_service,
    )


def _scenario(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "name": "Checkout scenario",
        "description": "Exercise checkout",
        "agents_config": {"agents": ["registry:known"]},
        "workflow_template_id": uuid4(),
        "mock_set_config": {"llm": "mock"},
        "input_distribution": {"kind": "fixed"},
        "twin_fidelity": {"digital_twin_ids": [str(uuid4()), "not-a-uuid"]},
        "success_criteria": [{"metric": "accuracy", "operator": ">=", "value": 0.9}],
        "run_schedule": None,
        "archived_at": None,
        "created_by": uuid4(),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _valid_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "name": "Scenario",
        "agents_config": {"agents": ["registry:known"]},
        "workflow_template_id": None,
        "mock_set_config": {"llm": "mock"},
        "input_distribution": {"kind": "fixed", "value": "hello"},
        "twin_fidelity": {"tools": "mock", "data_source": "synthetic"},
        "success_criteria": [{"metric": "accuracy", "operator": ">=", "value": 0.9}],
        "run_schedule": None,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    ("values", "expected_code", "registry_service", "workflow_service"),
    [
        (
            _valid_values(mock_set_config={"api_key": "sk-test-secret-123456"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(input_distribution={"password": "pass-value-123456"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(agents_config={"plaintext_secret": "agent-secret-123456"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(twin_fidelity={"token": "twin-token-123456"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(success_criteria=[{"secret": "aaaaaaaa"}]),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(run_schedule={"api_key": "aaaaaaaa"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (_valid_values(success_criteria=[]), "EMPTY_SUCCESS_CRITERIA", None, None),
        (_valid_values(success_criteria={}), "EMPTY_SUCCESS_CRITERIA", None, None),
        (_valid_values(success_criteria=None), "EMPTY_SUCCESS_CRITERIA", None, None),
        (
            _valid_values(
                twin_fidelity={
                    "mode": "real:production-data",
                    "tools": "mock:tool-gateway",
                }
            ),
            "FORBIDDEN_TWIN_COMBO",
            None,
            None,
        ),
        (
            _valid_values(
                twin_fidelity={
                    "data_source": "production",
                    "tool_gateway": "mock",
                }
            ),
            "FORBIDDEN_TWIN_COMBO",
            None,
            None,
        ),
        (
            _valid_values(agents_config={"agents": ["registry:missing"]}),
            "UNKNOWN_AGENT_FQN",
            _RegistryStub({"registry:known"}),
            None,
        ),
        (
            _valid_values(agents_config={"agents": [{"fqn": "registry:missing"}]}),
            "UNKNOWN_AGENT_FQN",
            _RegistryStub({"registry:known"}),
            None,
        ),
        (
            _valid_values(workflow_template_id=uuid4()),
            "WORKFLOW_TEMPLATE_NOT_FOUND",
            None,
            _WorkflowStub(None),
        ),
        (
            _valid_values(workflow_template_id=uuid4()),
            "WORKFLOW_TEMPLATE_NOT_APPROVED",
            None,
            _WorkflowStub(SimpleNamespace(approval_status="draft")),
        ),
    ],
)
@pytest.mark.asyncio
async def test_scenario_validation_rejects_invalid_configs(
    values: dict[str, Any],
    expected_code: str,
    registry_service: object | None,
    workflow_service: object | None,
) -> None:
    service = _service(registry_service=registry_service, workflow_service=workflow_service)

    with pytest.raises(ValidationError) as exc_info:
        await service._validate_payload(values)

    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_scenario_validation_accepts_known_agents_and_approved_workflow() -> None:
    service = _service(
        registry_service=_SyncRegistryStub(),
        workflow_service=_WorkflowStub(SimpleNamespace(approval_status="approved")),
    )

    await service._validate_payload(_valid_values(workflow_template_id=uuid4()))


@pytest.mark.asyncio
async def test_scenario_crud_and_launch_paths() -> None:
    scenario = _scenario()
    repository = _RepositoryStub(scenario)
    runner = _RunnerStub()
    service = SimulationScenariosService(
        repository=repository,  # type: ignore[arg-type]
        runner=runner,  # type: ignore[arg-type]
        settings=SimpleNamespace(simulation=SimpleNamespace(max_duration_seconds=1800)),  # type: ignore[arg-type]
    )

    listed = await service.list_scenarios(
        scenario.workspace_id,
        include_archived=False,
        limit=25,
        cursor="cursor-1",
    )
    assert listed.next_cursor == "next"
    assert listed.items[0].id == scenario.id
    assert (await service.get_scenario(scenario.id, scenario.workspace_id)).name == scenario.name

    created = await service.create_scenario(
        ScenarioCreate(
            workspace_id=scenario.workspace_id,
            name="  New scenario  ",
            description="Created",
            agents_config={"agent_fqns": ["registry:known"]},
            workflow_template_id=None,
            mock_set_config={"llm": "mock"},
            input_distribution={"kind": "fixed"},
            twin_fidelity={"tools": "mock", "data_source": "synthetic"},
            success_criteria=[{"metric": "latency", "operator": "<", "value": 100}],
        ),
        actor_id=scenario.created_by,
    )
    assert created.name == "New scenario"
    assert repository.created is not None

    updated = await service.update_scenario(
        scenario.id,
        scenario.workspace_id,
        ScenarioUpdate(name="  Updated scenario  ", description="Updated"),
    )
    assert updated.name == "Updated scenario"
    assert repository.updated_values == {
        "name": "Updated scenario",
        "description": "Updated",
    }

    summary = await service.launch_scenario(
        scenario.id,
        scenario.workspace_id,
        scenario.created_by,
        ScenarioRunRequest(iterations=2, use_real_llm=True),
    )
    assert summary.scenario_id == scenario.id
    assert len(summary.queued_runs) == 2
    assert len(runner.calls) == 2
    assert runner.calls[0]["name"] == "Updated scenario #1"
    assert runner.calls[0]["max_duration_seconds"] == 1800
    assert runner.calls[0]["scenario_config"]["use_real_llm"] is True
    assert len(runner.calls[0]["digital_twin_ids"]) == 1

    archived = await service.archive_scenario(scenario.id, scenario.workspace_id)
    assert archived.archived_at is not None
    with pytest.raises(ValidationError) as exc_info:
        await service.launch_scenario(
            scenario.id,
            scenario.workspace_id,
            scenario.created_by,
            ScenarioRunRequest(iterations=1),
        )
    assert exc_info.value.code == "SCENARIO_ARCHIVED"

    with pytest.raises(SimulationNotFoundError):
        await service.get_scenario(uuid4(), scenario.workspace_id)
    with pytest.raises(SimulationNotFoundError):
        await service.archive_scenario(uuid4(), scenario.workspace_id)


@pytest.mark.asyncio
async def test_scenario_validation_helper_acceptance_edges() -> None:
    await _service()._validate_payload(_valid_values(agents_config={"agents": ["unknown"]}))

    no_resolver = SimpleNamespace(get_agent_by_fqn=None, resolve_fqn=None)
    await _service(registry_service=no_resolver)._validate_payload(_valid_values())

    no_workflow_resolver = _NoResolverWorkflowStub()
    await _service(workflow_service=no_workflow_resolver)._validate_payload(
        _valid_values(workflow_template_id=uuid4())
    )
    published_service = _service(workflow_service=_WorkflowStub(SimpleNamespace(state="published")))
    await published_service._validate_payload(
        _valid_values(workflow_template_id=uuid4())
    )

    assert _agent_fqns({"agents": ["a", {"fqn": "b"}, {"skip": "c"}]}) == ["a", "b"]
    assert _agent_fqns({"agents": "not-a-list"}) == []
    assert _digital_twin_ids({"digital_twin_ids": "not-a-list"}) == []
    valid_twin_id = uuid4()
    assert _digital_twin_ids({"digital_twin_ids": [str(valid_twin_id), "bad"]}) == [valid_twin_id]
    assert _flatten_strings(None) == []
    assert _flatten_strings("VALUE") == ["value"]
    assert _flatten_strings({"a": ["B", 3]}) == ["b", "3"]
