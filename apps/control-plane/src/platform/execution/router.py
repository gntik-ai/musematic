from __future__ import annotations

from datetime import datetime
from platform.common.dependencies import get_current_user
from platform.execution.dependencies import get_execution_service
from platform.execution.models import ExecutionEventType, ExecutionStatus
from platform.execution.schemas import (
    ApprovalDecisionRequest,
    ApprovalWaitListResponse,
    ApprovalWaitResponse,
    ExecutionCreate,
    ExecutionEventListResponse,
    ExecutionListResponse,
    ExecutionResponse,
    ExecutionStateResponse,
    HotChangeApplyResponse,
    HotChangeRequest,
    TaskPlanFullResponse,
    TaskPlanRecordResponse,
)
from platform.execution.service import ExecutionService
from platform.workflows.models import TriggerType
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Response, status

router = APIRouter(prefix="/api/v1/executions", tags=["execution"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


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


@router.post(
    "/{execution_id}/approvals/{step_id}/decide",
    response_model=ApprovalWaitResponse,
)
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


@router.get(
    "/{execution_id}/task-plan",
    response_model=list[TaskPlanRecordResponse],
)
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


@router.get(
    "/{execution_id}/task-plan/{step_id}",
    response_model=TaskPlanFullResponse,
)
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
