from __future__ import annotations

from platform.workflows.ir import WorkflowIR

import pytest

from tests.unit.execution.test_scheduler import _build_scheduler


class LaunchingRuntimeController:
    def __init__(self, *, warm_start: bool = True, should_fail: bool = False) -> None:
        self.launch_calls: list[tuple[dict[str, object], bool]] = []
        self.dispatch_calls: list[dict[str, object]] = []
        self.warm_start = warm_start
        self.should_fail = should_fail

    async def launch_runtime(
        self,
        payload: dict[str, object],
        *,
        prefer_warm: bool = True,
    ) -> dict[str, object]:
        self.launch_calls.append((payload, prefer_warm))
        if self.should_fail:
            raise RuntimeError("launch failed")
        return {"warm_start": self.warm_start}

    async def dispatch(self, payload: dict[str, object]) -> None:
        self.dispatch_calls.append(payload)


class LegacyRuntimeController:
    def __init__(self) -> None:
        self.dispatch_calls: list[dict[str, object]] = []

    async def dispatch(self, payload: dict[str, object]) -> None:
        self.dispatch_calls.append(payload)


@pytest.mark.asyncio
async def test_dispatch_uses_launch_runtime_with_prefer_warm() -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    runtime_controller = LaunchingRuntimeController()
    scheduler.runtime_controller = runtime_controller
    execution, ir, step = await _create_basic_execution(workflow_service, execution_service)

    await scheduler._dispatch_to_runtime(execution, ir, step)

    assert runtime_controller.launch_calls[0][1] is True
    assert runtime_controller.dispatch_calls == []


@pytest.mark.asyncio
async def test_dispatch_falls_back_to_legacy_dispatch_when_launch_method_missing() -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    runtime_controller = LegacyRuntimeController()
    scheduler.runtime_controller = runtime_controller
    execution, ir, step = await _create_basic_execution(workflow_service, execution_service)

    await scheduler._dispatch_to_runtime(execution, ir, step)

    assert runtime_controller.dispatch_calls[0]["step_id"] == "step_a"


@pytest.mark.asyncio
async def test_dispatch_accepts_cold_start_launch_response_without_error() -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    runtime_controller = LaunchingRuntimeController(warm_start=False)
    scheduler.runtime_controller = runtime_controller
    execution, ir, step = await _create_basic_execution(workflow_service, execution_service)

    await scheduler._dispatch_to_runtime(execution, ir, step)

    assert runtime_controller.launch_calls[0][1] is True


@pytest.mark.asyncio
async def test_dispatch_uses_fallback_dispatch_when_launch_runtime_errors() -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    runtime_controller = LaunchingRuntimeController(should_fail=True)
    scheduler.runtime_controller = runtime_controller
    execution, ir, step = await _create_basic_execution(workflow_service, execution_service)

    await scheduler._dispatch_to_runtime(execution, ir, step)

    assert runtime_controller.launch_calls[0][1] is True
    assert runtime_controller.dispatch_calls[0]["step_id"] == "step_a"


@pytest.mark.asyncio
async def test_dispatch_prefers_step_compute_budget_over_workflow_budget() -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    runtime_controller = LaunchingRuntimeController()
    scheduler.runtime_controller = runtime_controller
    execution, ir, step = await _create_basic_execution(
        workflow_service,
        execution_service,
        yaml_source="""
schema_version: 1
metadata:
  compute_budget: 0.8
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    reasoning_mode: deep
    compute_budget: 0.4
        """.strip(),
    )

    await scheduler._dispatch_to_runtime(execution, ir, step)

    payload = runtime_controller.launch_calls[0][0]
    assert payload["reasoning_mode"] == "deep"
    assert payload["compute_budget"] == 0.4
    assert payload["effective_budget_scope"] == "step"


@pytest.mark.asyncio
async def test_dispatch_prefers_workflow_compute_budget_when_stricter() -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    runtime_controller = LaunchingRuntimeController()
    scheduler.runtime_controller = runtime_controller
    execution, ir, step = await _create_basic_execution(
        workflow_service,
        execution_service,
        yaml_source="""
schema_version: 1
metadata:
  compute_budget: 0.25
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    compute_budget: 0.6
        """.strip(),
    )

    await scheduler._dispatch_to_runtime(execution, ir, step)

    payload = runtime_controller.launch_calls[0][0]
    assert payload["compute_budget"] == 0.25
    assert payload["effective_budget_scope"] == "workflow"


async def _create_basic_execution(
    workflow_service,
    execution_service,
    *,
    yaml_source: str | None = None,
):
    from platform.execution.schemas import ExecutionCreate
    from platform.workflows.schemas import WorkflowCreate
    from uuid import uuid4

    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Dispatch Workflow",
            description=None,
            yaml_source=(
                yaml_source
                or """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
                """.strip()
            ),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    execution_response = await execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow.id,
            workspace_id=workspace_id,
        ),
        created_by=actor_id,
    )
    execution = await execution_service.repository.get_execution_by_id(execution_response.id)
    assert execution is not None
    version = await execution_service._resolve_workflow_version(workflow.id, None)
    ir = WorkflowIR.from_dict(version.compiled_ir)
    step = ir.steps[0]
    return execution, ir, step
