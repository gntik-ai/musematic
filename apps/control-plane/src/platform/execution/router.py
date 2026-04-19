from __future__ import annotations

from datetime import datetime
from platform.auth.router import _require_platform_admin
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from platform.execution.checkpoint_service import CheckpointService
from platform.execution.dependencies import (
    get_checkpoint_service,
    get_execution_service,
    get_reprioritization_service,
    get_runtime_controller_client,
)
from platform.execution.models import ExecutionEventType, ExecutionStatus
from platform.execution.reprioritization import ReprioritizationService
from platform.execution.schemas import (
    ApprovalDecisionRequest,
    ApprovalWaitListResponse,
    ApprovalWaitResponse,
    CheckpointDetailResponse,
    CheckpointListResponse,
    ExecutionCreate,
    ExecutionEventListResponse,
    ExecutionListResponse,
    ExecutionResponse,
    ExecutionStateResponse,
    HotChangeApplyResponse,
    HotChangeRequest,
    ReasoningTraceResponse,
    ReprioritizationTriggerCreate,
    ReprioritizationTriggerListResponse,
    ReprioritizationTriggerResponse,
    ReprioritizationTriggerUpdate,
    RollbackRequest,
    RollbackResponse,
    TaskPlanFullResponse,
    TaskPlanRecordResponse,
    WarmPoolConfigRequest,
    WarmPoolConfigResponse,
    WarmPoolStatusResponse,
)
from platform.execution.service import ExecutionService
from platform.workflows.models import TriggerType
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Response, status

router = APIRouter(prefix="/api/v1/executions", tags=["execution"])
trigger_router = APIRouter(prefix="/api/v1/reprioritization-triggers", tags=["execution"])
runtime_router = APIRouter(prefix="/api/v1/runtime", tags=["execution"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {str(item.get("role")) for item in roles if isinstance(item, dict)}


def _requester_workspace_id(current_user: dict[str, Any]) -> UUID | None:
    value = current_user.get("workspace_id") or current_user.get("workspace")
    if value in {None, ""}:
        return None
    return UUID(str(value))


def _require_workspace_admin(current_user: dict[str, Any]) -> None:
    if {"workspace_admin", "superadmin", "platform_admin"} & _role_names(current_user):
        return
    raise AuthorizationError("PERMISSION_DENIED", "Workspace admin role required")


def _require_execution_rollback(current_user: dict[str, Any]) -> None:
    permissions = {str(item) for item in current_user.get("permissions", [])}
    if "execution.rollback" in permissions:
        return
    if {"superadmin", "platform_admin"} & _role_names(current_user):
        return
    raise AuthorizationError("PERMISSION_DENIED", "Permission 'execution.rollback' required")


@router.post("", response_model=ExecutionResponse, status_code=status.HTTP_201_CREATED)
async def create_execution(
    payload: ExecutionCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionResponse:
    """Create execution."""
    return await execution_service.create_execution(payload, created_by=_actor_id(current_user))


@router.get("", response_model=ExecutionListResponse)
async def list_executions(
    workspace_id: UUID = Query(...),
    workflow_id: UUID | None = Query(default=None),
    status: ExecutionStatus | None = Query(default=None),
    trigger_type: TriggerType | None = Query(default=None),
    goal_id: UUID | None = Query(default=None),
    since: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionListResponse:
    """List executions."""
    del current_user
    return await execution_service.list_executions(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        status=status,
        trigger_type=trigger_type,
        goal_id=goal_id,
        since=since,
        page=page,
        page_size=page_size,
    )


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionResponse:
    """Return execution."""
    del current_user
    return await execution_service.get_execution(execution_id)


@router.post("/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(
    execution_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionResponse:
    """Cancel execution."""
    del current_user
    return await execution_service.cancel_execution(execution_id)


@router.get("/{execution_id}/state", response_model=ExecutionStateResponse)
async def get_execution_state(
    execution_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionStateResponse:
    """Return execution state."""
    del current_user
    return await execution_service.get_execution_state(execution_id)


@router.get("/{execution_id}/journal", response_model=ExecutionEventListResponse)
async def get_execution_journal(
    execution_id: UUID,
    since_sequence: int | None = Query(default=None, ge=0),
    event_type: ExecutionEventType | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionEventListResponse:
    """Return execution journal."""
    del current_user
    return await execution_service.get_journal(
        execution_id,
        since_sequence=since_sequence,
        event_type=event_type,
    )


@router.post("/{execution_id}/replay", response_model=ExecutionStateResponse)
async def replay_execution(
    execution_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionStateResponse:
    """Replay execution."""
    del current_user
    return await execution_service.replay_execution(execution_id)


@router.post(
    "/{execution_id}/resume", response_model=ExecutionResponse, status_code=status.HTTP_201_CREATED
)
async def resume_execution(
    execution_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionResponse:
    """Resume execution."""
    del current_user
    return await execution_service.resume_execution(execution_id)


@router.post(
    "/{execution_id}/rerun", response_model=ExecutionResponse, status_code=status.HTTP_201_CREATED
)
async def rerun_execution(
    execution_id: UUID,
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionResponse:
    """Rerun execution."""
    del current_user
    return await execution_service.rerun_execution(
        execution_id,
        payload.get("input_overrides", {}),
    )


@router.get("/{execution_id}/approvals", response_model=ApprovalWaitListResponse)
async def list_approvals(
    execution_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ApprovalWaitListResponse:
    """List approvals."""
    del current_user
    return await execution_service.list_approvals(execution_id)


@router.post("/{execution_id}/approvals/{step_id}/decide", response_model=ApprovalWaitResponse)
async def decide_approval(
    execution_id: UUID,
    step_id: str,
    payload: ApprovalDecisionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ApprovalWaitResponse:
    """Handle decide approval."""
    return await execution_service.record_approval_decision(
        execution_id,
        step_id,
        payload,
        decided_by=_actor_id(current_user),
    )


@router.get("/{execution_id}/checkpoints", response_model=CheckpointListResponse)
async def list_checkpoints(
    execution_id: UUID,
    include_superseded: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    checkpoint_service: CheckpointService = Depends(get_checkpoint_service),
) -> CheckpointListResponse:
    """List checkpoints for an execution."""
    del current_user
    return await checkpoint_service.list_checkpoints(
        execution_id,
        include_superseded=include_superseded,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{execution_id}/checkpoints/{checkpoint_number}", response_model=CheckpointDetailResponse
)
async def get_checkpoint(
    execution_id: UUID,
    checkpoint_number: int,
    current_user: dict[str, Any] = Depends(get_current_user),
    checkpoint_service: CheckpointService = Depends(get_checkpoint_service),
) -> CheckpointDetailResponse:
    """Return a checkpoint."""
    del current_user
    return await checkpoint_service.get_checkpoint(execution_id, checkpoint_number)


@router.post("/{execution_id}/rollback/{checkpoint_number}", response_model=RollbackResponse)
async def rollback_execution(
    execution_id: UUID,
    checkpoint_number: int,
    payload: RollbackRequest = Body(default_factory=RollbackRequest),
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> RollbackResponse:
    """Rollback an execution to a checkpoint."""
    _require_execution_rollback(current_user)
    return await execution_service.rollback_execution(
        execution_id,
        checkpoint_number,
        initiated_by=_actor_id(current_user),
        reason=payload.reason,
    )


@router.get("/{execution_id}/reasoning-trace", response_model=ReasoningTraceResponse)
async def get_reasoning_trace(
    execution_id: UUID,
    step_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ReasoningTraceResponse:
    """Return the structured reasoning trace for an execution."""
    return await execution_service.get_reasoning_trace(
        execution_id,
        step_id,
        page=page,
        page_size=page_size,
        requester_workspace_id=_requester_workspace_id(current_user),
    )


@router.get("/{execution_id}/task-plan", response_model=list[TaskPlanRecordResponse])
async def list_task_plans(
    execution_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> list[TaskPlanRecordResponse]:
    """List task plans."""
    del current_user
    result = await execution_service.get_task_plan(execution_id, None)
    assert isinstance(result, list)
    return result


@router.get("/{execution_id}/task-plan/{step_id}", response_model=TaskPlanFullResponse)
async def get_task_plan(
    execution_id: UUID,
    step_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> TaskPlanFullResponse:
    """Return task plan."""
    del current_user
    result = await execution_service.get_task_plan(execution_id, step_id)
    assert not isinstance(result, list)
    return result


@router.post("/{execution_id}/hot-change", response_model=HotChangeApplyResponse)
async def hot_change_execution(
    execution_id: UUID,
    payload: HotChangeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> HotChangeApplyResponse:
    """Handle hot change execution."""
    del current_user
    compatibility = await execution_service.validate_hot_change(
        execution_id, payload.new_version_id
    )
    execution = await execution_service.apply_hot_change(execution_id, payload.new_version_id)
    return HotChangeApplyResponse(result=compatibility, execution=execution)


@router.post("/{execution_id}/compensation/{step_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_compensation(
    execution_id: UUID,
    step_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> Response:
    """Trigger compensation."""
    await execution_service.trigger_compensation(
        execution_id,
        step_id,
        triggered_by=str(_actor_id(current_user)),
    )
    return Response(status_code=status.HTTP_202_ACCEPTED)


@trigger_router.post(
    "", response_model=ReprioritizationTriggerResponse, status_code=status.HTTP_201_CREATED
)
async def create_reprioritization_trigger(
    payload: ReprioritizationTriggerCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    reprioritization_service: ReprioritizationService = Depends(get_reprioritization_service),
) -> ReprioritizationTriggerResponse:
    """Create a reprioritization trigger."""
    _require_workspace_admin(current_user)
    trigger = await reprioritization_service.create_trigger(
        payload, created_by=_actor_id(current_user)
    )
    return ReprioritizationTriggerResponse.model_validate(trigger)


@trigger_router.get("", response_model=ReprioritizationTriggerListResponse)
async def list_reprioritization_triggers(
    workspace_id: UUID = Query(...),
    enabled: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    reprioritization_service: ReprioritizationService = Depends(get_reprioritization_service),
) -> ReprioritizationTriggerListResponse:
    """List reprioritization triggers."""
    del current_user
    items, total = await reprioritization_service.list_triggers(
        workspace_id,
        enabled=enabled,
        page=page,
        page_size=page_size,
    )
    return ReprioritizationTriggerListResponse(
        items=[ReprioritizationTriggerResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@trigger_router.get("/{trigger_id}", response_model=ReprioritizationTriggerResponse)
async def get_reprioritization_trigger(
    trigger_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    reprioritization_service: ReprioritizationService = Depends(get_reprioritization_service),
) -> ReprioritizationTriggerResponse:
    """Return a reprioritization trigger."""
    del current_user
    trigger = await reprioritization_service.get_trigger(trigger_id)
    return ReprioritizationTriggerResponse.model_validate(trigger)


@trigger_router.patch("/{trigger_id}", response_model=ReprioritizationTriggerResponse)
async def update_reprioritization_trigger(
    trigger_id: UUID,
    payload: ReprioritizationTriggerUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    reprioritization_service: ReprioritizationService = Depends(get_reprioritization_service),
) -> ReprioritizationTriggerResponse:
    """Update a reprioritization trigger."""
    _require_workspace_admin(current_user)
    trigger = await reprioritization_service.update_trigger(trigger_id, payload)
    return ReprioritizationTriggerResponse.model_validate(trigger)


@trigger_router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reprioritization_trigger(
    trigger_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    reprioritization_service: ReprioritizationService = Depends(get_reprioritization_service),
) -> Response:
    """Delete a reprioritization trigger."""
    _require_workspace_admin(current_user)
    await reprioritization_service.delete_trigger(trigger_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@runtime_router.get("/warm-pool/status", response_model=WarmPoolStatusResponse)
async def warm_pool_status(
    workspace_id: str = Query(default=""),
    agent_type: str = Query(default=""),
    current_user: dict[str, Any] = Depends(get_current_user),
    runtime_controller: RuntimeControllerClient = Depends(get_runtime_controller_client),
) -> WarmPoolStatusResponse:
    _require_platform_admin(current_user)
    result = await runtime_controller.warm_pool_status(
        workspace_id=workspace_id,
        agent_type=agent_type,
    )
    return WarmPoolStatusResponse(**result)


@runtime_router.put("/warm-pool/config", response_model=WarmPoolConfigResponse)
async def warm_pool_config(
    payload: WarmPoolConfigRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    runtime_controller: RuntimeControllerClient = Depends(get_runtime_controller_client),
) -> WarmPoolConfigResponse:
    _require_platform_admin(current_user)
    result = await runtime_controller.warm_pool_config(
        str(payload.workspace_id),
        payload.agent_type,
        payload.target_size,
    )
    return WarmPoolConfigResponse(**result)
