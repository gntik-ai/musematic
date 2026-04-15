from __future__ import annotations

from datetime import UTC, datetime
from platform.agentops.exceptions import RetirementConflictError
from platform.agentops.models import RetirementWorkflow, RetirementWorkflowStatus
from platform.agentops.retirement.workflow import RetirementManager
from platform.common.exceptions import NotFoundError, ValidationError
from typing import Any
from uuid import UUID, uuid4

import pytest


class _GovernanceStub:
    async def record(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs


class _RepositoryStub:
    def __init__(self, *, active_workflow: RetirementWorkflow | None = None) -> None:
        self.active_workflow = active_workflow
        self.created: list[RetirementWorkflow] = []
        self.updated: list[RetirementWorkflow] = []

    async def get_active_retirement(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> RetirementWorkflow | None:
        del agent_fqn, workspace_id
        return self.active_workflow

    async def create_retirement(self, workflow: RetirementWorkflow) -> RetirementWorkflow:
        workflow.id = uuid4()
        workflow.created_at = datetime.now(UTC)
        workflow.updated_at = workflow.created_at
        self.active_workflow = workflow
        self.created.append(workflow)
        return workflow

    async def get_retirement(self, workflow_id: UUID) -> RetirementWorkflow | None:
        if self.active_workflow is not None and self.active_workflow.id == workflow_id:
            return self.active_workflow
        return next((item for item in self.updated if item.id == workflow_id), None)

    async def update_retirement(self, workflow: RetirementWorkflow) -> RetirementWorkflow:
        workflow.updated_at = datetime.now(UTC)
        self.updated.append(workflow)
        return workflow


class _WorkflowServiceStub:
    def __init__(self, dependencies: list[dict[str, Any]]) -> None:
        self.dependencies = dependencies

    async def find_workflows_using_agent(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> list[dict[str, Any]]:
        del agent_fqn, workspace_id
        return self.dependencies


class _RegistryServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, UUID]] = []

    async def set_marketplace_visibility(
        self,
        agent_fqn: str,
        visible: bool,
        workspace_id: UUID,
    ) -> None:
        self.calls.append((agent_fqn, visible, workspace_id))


@pytest.mark.asyncio
async def test_initiate_raises_conflict_if_retirement_already_active() -> None:
    repository = _RepositoryStub(active_workflow=RetirementWorkflow())
    manager = RetirementManager(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=_GovernanceStub(),  # type: ignore[arg-type]
        workflow_service=_WorkflowServiceStub([]),
        registry_service=_RegistryServiceStub(),
    )

    with pytest.raises(RetirementConflictError):
        await manager.initiate(
            "finance:agent",
            uuid4(),
            uuid4(),
            trigger_reason="sustained_degradation",
            triggered_by=uuid4(),
        )


@pytest.mark.asyncio
async def test_initiate_sets_high_impact_flag_when_dependencies_exist() -> None:
    workspace_id = uuid4()
    manager = RetirementManager(
        repository=_RepositoryStub(),  # type: ignore[arg-type]
        governance_publisher=_GovernanceStub(),  # type: ignore[arg-type]
        workflow_service=_WorkflowServiceStub([{"workflow_id": str(uuid4())}]),
        registry_service=_RegistryServiceStub(),
    )

    workflow = await manager.initiate(
        "finance:agent",
        uuid4(),
        workspace_id,
        trigger_reason="sustained_degradation",
        triggered_by=uuid4(),
    )

    assert workflow.high_impact_flag is True
    assert workflow.status == RetirementWorkflowStatus.grace_period.value


@pytest.mark.asyncio
async def test_operator_confirmation_required_before_retiring_high_impact_agent() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub()
    registry = _RegistryServiceStub()
    manager = RetirementManager(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=_GovernanceStub(),  # type: ignore[arg-type]
        workflow_service=_WorkflowServiceStub([{"workflow_id": str(uuid4())}]),
        registry_service=registry,
    )
    workflow = await manager.initiate(
        "finance:agent",
        uuid4(),
        workspace_id,
        trigger_reason="sustained_degradation",
        triggered_by=uuid4(),
    )

    with pytest.raises(ValidationError):
        await manager.retire_agent(workflow.id)

    assert registry.calls == []


@pytest.mark.asyncio
async def test_halt_sets_status_halted() -> None:
    manager = RetirementManager(
        repository=_RepositoryStub(),  # type: ignore[arg-type]
        governance_publisher=_GovernanceStub(),  # type: ignore[arg-type]
        workflow_service=_WorkflowServiceStub([]),
        registry_service=_RegistryServiceStub(),
    )
    workflow = await manager.initiate(
        "finance:agent",
        uuid4(),
        uuid4(),
        trigger_reason="manual",
        triggered_by=uuid4(),
    )

    halted = await manager.halt(workflow.id, reason="Recovered", halted_by=uuid4())

    assert halted.status == RetirementWorkflowStatus.halted.value
    assert halted.halt_reason == "Recovered"


@pytest.mark.asyncio
async def test_retire_agent_calls_registry_service_to_hide_marketplace_visibility() -> None:
    workspace_id = uuid4()
    registry = _RegistryServiceStub()
    manager = RetirementManager(
        repository=_RepositoryStub(),  # type: ignore[arg-type]
        governance_publisher=_GovernanceStub(),  # type: ignore[arg-type]
        workflow_service=_WorkflowServiceStub([]),
        registry_service=registry,
    )
    workflow = await manager.initiate(
        "finance:agent",
        uuid4(),
        workspace_id,
        trigger_reason="manual",
        triggered_by=uuid4(),
        operator_confirmed=True,
    )

    retired = await manager.retire_agent(workflow.id)

    assert retired.status == RetirementWorkflowStatus.retired.value
    assert registry.calls == [("finance:agent", False, workspace_id)]


@pytest.mark.asyncio
async def test_retirement_manager_get_confirm_and_noop_helpers_cover_remaining_paths() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub()
    manager = RetirementManager(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=None,
        workflow_service=None,
        registry_service=None,
        now_factory=lambda: datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(NotFoundError):
        await manager.get(uuid4())

    workflow = await manager.initiate(
        "finance:agent",
        uuid4(),
        workspace_id,
        trigger_reason="manual",
        triggered_by=uuid4(),
        operator_confirmed=False,
    )
    confirmed = await manager.confirm(workflow.id, confirmed_by=uuid4(), reason="approved")
    dependent = await manager._dependent_workflows("finance:agent", workspace_id)
    await manager._record_event(
        "agentops.retirement.completed",
        confirmed,
        actor=None,
        payload={},
    )

    assert confirmed.operator_confirmed is True
    assert dependent == []
    assert manager._now().tzinfo is UTC
