from __future__ import annotations

import re
from platform.common.config import PlatformSettings
from platform.common.exceptions import ValidationError
from platform.simulation.coordination.runner import SimulationRunner
from platform.simulation.exceptions import SimulationNotFoundError
from platform.simulation.models import SimulationScenario
from platform.simulation.repository import SimulationRepository
from platform.simulation.schemas import (
    ScenarioCreate,
    ScenarioListResponse,
    ScenarioRead,
    ScenarioRunRequest,
    ScenarioRunSummary,
    ScenarioUpdate,
)
from typing import Any
from uuid import UUID

SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"
)


class SimulationScenariosService:
    def __init__(
        self,
        *,
        repository: SimulationRepository,
        runner: SimulationRunner,
        settings: PlatformSettings,
        registry_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.runner = runner
        self.settings = settings
        self.registry_service = registry_service

    async def list_scenarios(
        self,
        workspace_id: UUID,
        *,
        include_archived: bool,
        limit: int,
        cursor: str | None,
    ) -> ScenarioListResponse:
        items, next_cursor = await self.repository.list_scenarios(
            workspace_id,
            include_archived=include_archived,
            limit=limit,
            cursor=cursor,
        )
        return ScenarioListResponse(
            items=[ScenarioRead.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def get_scenario(self, scenario_id: UUID, workspace_id: UUID) -> ScenarioRead:
        scenario = await self._scenario_or_raise(scenario_id, workspace_id)
        return ScenarioRead.model_validate(scenario)

    async def create_scenario(self, payload: ScenarioCreate, actor_id: UUID) -> ScenarioRead:
        await self._validate_payload(payload.model_dump())
        scenario = await self.repository.create_scenario(
            SimulationScenario(
                workspace_id=payload.workspace_id,
                name=payload.name.strip(),
                description=payload.description,
                agents_config=payload.agents_config,
                workflow_template_id=payload.workflow_template_id,
                mock_set_config=payload.mock_set_config,
                input_distribution=payload.input_distribution,
                twin_fidelity=payload.twin_fidelity,
                success_criteria=payload.success_criteria,
                run_schedule=payload.run_schedule,
                created_by=actor_id,
            )
        )
        return ScenarioRead.model_validate(scenario)

    async def update_scenario(
        self,
        scenario_id: UUID,
        workspace_id: UUID,
        payload: ScenarioUpdate,
    ) -> ScenarioRead:
        scenario = await self._scenario_or_raise(scenario_id, workspace_id)
        values = payload.model_dump(exclude_unset=True)
        merged = {
            "agents_config": scenario.agents_config,
            "mock_set_config": scenario.mock_set_config,
            "input_distribution": scenario.input_distribution,
            "twin_fidelity": scenario.twin_fidelity,
            "success_criteria": scenario.success_criteria,
            **values,
        }
        await self._validate_payload(merged)
        if "name" in values and values["name"] is not None:
            values["name"] = str(values["name"]).strip()
        updated = await self.repository.update_scenario(scenario_id, workspace_id, values)
        assert updated is not None
        return ScenarioRead.model_validate(updated)

    async def archive_scenario(self, scenario_id: UUID, workspace_id: UUID) -> ScenarioRead:
        scenario = await self.repository.archive_scenario(scenario_id, workspace_id)
        if scenario is None:
            raise SimulationNotFoundError("Simulation scenario", scenario_id)
        return ScenarioRead.model_validate(scenario)

    async def launch_scenario(
        self,
        scenario_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        payload: ScenarioRunRequest,
    ) -> ScenarioRunSummary:
        scenario = await self._scenario_or_raise(scenario_id, workspace_id)
        if scenario.archived_at is not None:
            raise ValidationError("SCENARIO_ARCHIVED", "Archived scenarios cannot be launched")
        queued: list[UUID] = []
        max_duration = self.settings.simulation.max_duration_seconds
        scenario_config = {
            "scenario_id": str(scenario.id),
            "agents_config": scenario.agents_config,
            "workflow_template_id": str(scenario.workflow_template_id)
            if scenario.workflow_template_id
            else None,
            "mock_set_config": scenario.mock_set_config,
            "input_distribution": scenario.input_distribution,
            "twin_fidelity": scenario.twin_fidelity,
            "success_criteria": scenario.success_criteria,
            "use_real_llm": payload.use_real_llm,
        }
        digital_twin_ids = _digital_twin_ids(scenario.twin_fidelity)
        for index in range(payload.iterations):
            run = await self.runner.create(
                workspace_id=workspace_id,
                name=f"{scenario.name} #{index + 1}",
                description=scenario.description,
                digital_twin_ids=digital_twin_ids,
                twin_configs=[],
                scenario_config=scenario_config,
                max_duration_seconds=max_duration,
                isolation_policy_id=None,
                initiated_by=actor_id,
                scenario_id=scenario.id,
            )
            queued.append(run.id)
        return ScenarioRunSummary(
            scenario_id=scenario.id,
            queued_runs=queued,
            iterations=payload.iterations,
        )

    async def _scenario_or_raise(self, scenario_id: UUID, workspace_id: UUID) -> SimulationScenario:
        scenario = await self.repository.get_scenario(scenario_id, workspace_id)
        if scenario is None:
            raise SimulationNotFoundError("Simulation scenario", scenario_id)
        return scenario

    async def _validate_payload(self, values: dict[str, Any]) -> None:
        for key in ("mock_set_config", "input_distribution"):
            if SECRET_PATTERN.search(str(values.get(key, ""))):
                raise ValidationError("PLAINTEXT_SECRET", "Scenario contains a plaintext secret")
        success_criteria = values.get("success_criteria") or []
        if not isinstance(success_criteria, list) or not success_criteria:
            raise ValidationError("EMPTY_SUCCESS_CRITERIA", "success_criteria must not be empty")
        twin_fidelity = values.get("twin_fidelity") or {}
        serialized_fidelity = str(twin_fidelity)
        combines_prod_data_with_mock_tools = (
            "real:production-data" in serialized_fidelity
            and "mock:tool-gateway" in serialized_fidelity
        )
        if combines_prod_data_with_mock_tools:
            raise ValidationError(
                "FORBIDDEN_TWIN_COMBO",
                "twin_fidelity combines production data with mocked tool gateway",
            )
        await self._validate_agent_fqns(values.get("agents_config") or {})

    async def _validate_agent_fqns(self, agents_config: dict[str, Any]) -> None:
        if self.registry_service is None:
            return
        for fqn in _agent_fqns(agents_config):
            resolver = getattr(self.registry_service, "get_agent_by_fqn", None) or getattr(
                self.registry_service,
                "resolve_fqn",
                None,
            )
            if not callable(resolver):
                return
            result = await resolver(fqn)
            if result is None:
                raise ValidationError("UNKNOWN_AGENT_FQN", f"Unknown agent FQN: {fqn}")


def _agent_fqns(agents_config: dict[str, Any]) -> list[str]:
    raw = agents_config.get("agents", agents_config.get("agent_fqns", []))
    if isinstance(raw, list):
        values = []
        for item in raw:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict) and item.get("fqn"):
                values.append(str(item["fqn"]))
        return values
    return []


def _digital_twin_ids(twin_fidelity: dict[str, Any]) -> list[UUID]:
    values = twin_fidelity.get("digital_twin_ids", [])
    if not isinstance(values, list):
        return []
    result: list[UUID] = []
    for value in values:
        try:
            result.append(UUID(str(value)))
        except ValueError:
            continue
    return result
