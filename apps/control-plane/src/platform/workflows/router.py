from __future__ import annotations

import hmac
from hashlib import sha256
from platform.common.dependencies import get_current_user
from platform.execution.dependencies import get_execution_service
from platform.execution.schemas import ExecutionCreate
from platform.execution.service import ExecutionService
from platform.workflows.dependencies import get_workflow_service
from platform.workflows.models import TriggerType, WorkflowStatus
from platform.workflows.schemas import (
    TriggerCreate,
    TriggerListResponse,
    TriggerResponse,
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowUpdate,
    WorkflowVersionResponse,
)
from platform.workflows.service import WorkflowService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    return await workflow_service.create_workflow(payload, _actor_id(current_user))


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    workspace_id: UUID = Query(...),
    status: WorkflowStatus | None = Query(default=None),
    tags: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowListResponse:
    del current_user
    parsed_tags = [item.strip() for item in tags.split(",")] if tags else None
    return await workflow_service.list_workflows(
        workspace_id=workspace_id,
        status=status,
        tags=parsed_tags,
        page=page,
        page_size=page_size,
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    del current_user
    return await workflow_service.get_workflow(workflow_id)


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    return await workflow_service.update_workflow(workflow_id, payload, _actor_id(current_user))


@router.post("/{workflow_id}/archive", response_model=WorkflowResponse)
async def archive_workflow(
    workflow_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    return await workflow_service.archive_workflow(workflow_id, _actor_id(current_user))


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionResponse])
async def list_versions(
    workflow_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> list[WorkflowVersionResponse]:
    del current_user
    return await workflow_service.list_versions(workflow_id)


@router.get("/{workflow_id}/versions/{version_number}", response_model=WorkflowVersionResponse)
async def get_version(
    workflow_id: UUID,
    version_number: int,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowVersionResponse:
    del current_user
    return await workflow_service.get_version(workflow_id, version_number)


@router.post(
    "/{workflow_id}/triggers",
    response_model=TriggerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_trigger(
    workflow_id: UUID,
    payload: TriggerCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> TriggerResponse:
    del current_user
    return await workflow_service.create_trigger(workflow_id, payload)


@router.get("/{workflow_id}/triggers", response_model=TriggerListResponse)
async def list_triggers(
    workflow_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> TriggerListResponse:
    del current_user
    return await workflow_service.list_triggers(workflow_id)


@router.patch("/{workflow_id}/triggers/{trigger_id}", response_model=TriggerResponse)
async def update_trigger(
    workflow_id: UUID,
    trigger_id: UUID,
    payload: TriggerCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> TriggerResponse:
    del current_user
    return await workflow_service.update_trigger(workflow_id, trigger_id, payload)


@router.delete("/{workflow_id}/triggers/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trigger(
    workflow_id: UUID,
    trigger_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> Response:
    del current_user
    await workflow_service.delete_trigger(workflow_id, trigger_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{workflow_id}/webhook/{trigger_id}", status_code=status.HTTP_202_ACCEPTED)
async def invoke_webhook_trigger(
    workflow_id: UUID,
    trigger_id: UUID,
    request: Request,
    x_webhook_signature: str = Header(default=""),
    workflow_service: WorkflowService = Depends(get_workflow_service),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> dict[str, str]:
    trigger_list = await workflow_service.list_triggers(workflow_id)
    trigger = next((item for item in trigger_list.items if item.id == trigger_id), None)
    if trigger is None or trigger.trigger_type != TriggerType.webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
    raw_body = await request.body()
    secret = ""
    repository_trigger = await workflow_service.repository.get_trigger_by_id(trigger_id)
    if repository_trigger is not None:
        secret = str(repository_trigger.config.get("secret", ""))
    expected = hmac.new(secret.encode("utf-8"), raw_body, sha256).hexdigest()
    if not hmac.compare_digest(expected, x_webhook_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    payload = await request.json()
    workflow = await workflow_service.get_workflow(workflow_id)
    execution = await execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow_id,
            trigger_type=TriggerType.webhook,
            trigger_id=trigger_id,
            input_parameters=payload if isinstance(payload, dict) else {"payload": payload},
            workspace_id=workflow.workspace_id,
        )
    )
    await workflow_service.record_trigger_fired(trigger_id, execution_id=execution.id)
    return {"execution_id": str(execution.id)}
