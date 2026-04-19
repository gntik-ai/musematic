from __future__ import annotations

from datetime import datetime
from platform.execution.models import ExecutionEventType, ExecutionStatus
from platform.execution.schemas import ExecutionCreate
from platform.workflows.models import TriggerType
from platform.workflows.schemas import WorkflowCreate
from platform.workspaces.models import Membership, Workspace, WorkspaceRole, WorkspaceStatus
from uuid import UUID, uuid4

from tests.integration.conftest import WorkflowExecutionStack


async def create_workspace(
    stack: WorkflowExecutionStack,
    *,
    workspace_id: UUID | None = None,
    name: str = "Execution Workspace",
) -> UUID:
    owner_id = UUID(stack.current_user["sub"])
    workspace = Workspace(
        id=workspace_id or uuid4(),
        name=name,
        description=None,
        owner_id=owner_id,
        is_default=False,
        status=WorkspaceStatus.active,
    )
    membership = Membership(
        workspace_id=workspace.id,
        user_id=owner_id,
        role=WorkspaceRole.owner,
    )
    stack.session.add(workspace)
    stack.session.add(membership)
    await stack.session.flush()
    return workspace.id


async def create_workflow(
    stack: WorkflowExecutionStack,
    *,
    workspace_id: UUID,
    name: str,
    yaml_source: str,
    checkpoint_policy: dict[str, object] | None = None,
) -> UUID:
    workflow = await stack.workflow_service.create_workflow(
        WorkflowCreate(
            name=name,
            description=None,
            yaml_source=yaml_source.strip(),
            checkpoint_policy=checkpoint_policy,
            tags=[],
            workspace_id=workspace_id,
        ),
        UUID(stack.current_user["sub"]),
    )
    return workflow.id


async def create_execution(
    stack: WorkflowExecutionStack,
    *,
    workflow_id: UUID,
    workspace_id: UUID,
    input_parameters: dict[str, object] | None = None,
    workflow_version_id: UUID | None = None,
    sla_deadline: datetime | None = None,
    trigger_type: TriggerType = TriggerType.manual,
    trigger_id: UUID | None = None,
    correlation_goal_id: UUID | None = None,
    correlation_fleet_id: UUID | None = None,
    correlation_interaction_id: UUID | None = None,
) -> UUID:
    execution = await stack.execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow_id,
            workflow_version_id=workflow_version_id,
            workspace_id=workspace_id,
            input_parameters=dict(input_parameters or {}),
            sla_deadline=sla_deadline,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            correlation_goal_id=correlation_goal_id,
            correlation_fleet_id=correlation_fleet_id,
            correlation_interaction_id=correlation_interaction_id,
        ),
        created_by=UUID(stack.current_user["sub"]),
    )
    return execution.id


async def mark_step_completed(
    stack: WorkflowExecutionStack,
    *,
    execution_id: UUID,
    step_id: str,
    payload: dict[str, object] | None = None,
    execution_completed: bool = False,
) -> None:
    event_payload = dict(payload or {})
    if execution_completed:
        event_payload["execution_completed"] = True
    await stack.execution_service.record_runtime_event(
        execution_id,
        step_id=step_id,
        event_type=ExecutionEventType.completed,
        payload=event_payload,
        status=ExecutionStatus.completed if execution_completed else ExecutionStatus.running,
    )


async def mark_step_failed(
    stack: WorkflowExecutionStack,
    *,
    execution_id: UUID,
    step_id: str,
    payload: dict[str, object] | None = None,
) -> None:
    await stack.execution_service.record_runtime_event(
        execution_id,
        step_id=step_id,
        event_type=ExecutionEventType.failed,
        payload=dict(payload or {}),
        status=ExecutionStatus.failed,
    )
