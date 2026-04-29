from __future__ import annotations

from datetime import datetime
from platform.common.dependencies import get_current_user, get_db
from platform.common.tagging.filter_extension import parse_tag_label_filters
from platform.policies.dependencies import get_policy_service, get_tool_gateway_service
from platform.policies.gateway import ToolGatewayService
from platform.policies.models import EnforcementComponent, PolicyScopeType, PolicyStatus
from platform.policies.schemas import (
    EffectivePolicyResponse,
    EnforcementBundle,
    MaturityGateListResponse,
    PolicyAttachmentListResponse,
    PolicyAttachRequest,
    PolicyAttachResponse,
    PolicyBlockedActionListResponse,
    PolicyBlockedActionRecordResponse,
    PolicyCreate,
    PolicyListResponse,
    PolicyResponse,
    PolicyUpdate,
    PolicyVersionListResponse,
    PolicyVersionResponse,
    PolicyWithVersionResponse,
    SanitizationResult,
    SanitizeToolOutputRequest,
)
from platform.policies.service import PolicyService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


@router.get("/effective/{agent_id}", response_model=EffectivePolicyResponse)
async def get_effective_policy(
    agent_id: UUID,
    workspace_id: UUID = Query(...),
    policy_service: PolicyService = Depends(get_policy_service),
) -> EffectivePolicyResponse:
    return await policy_service.get_effective_policy(agent_id, workspace_id)


@router.get("/bundle/{agent_id}", response_model=EnforcementBundle)
async def get_enforcement_bundle(
    agent_id: UUID,
    workspace_id: UUID = Query(...),
    step_type: str | None = Query(default=None),
    policy_service: PolicyService = Depends(get_policy_service),
) -> EnforcementBundle:
    bundle = await policy_service.get_enforcement_bundle(agent_id, workspace_id)
    return bundle.get_shard(step_type) if step_type else bundle


@router.post("/bundle/{agent_id}/invalidate", status_code=status.HTTP_204_NO_CONTENT)
async def invalidate_enforcement_bundle(
    agent_id: UUID,
    policy_service: PolicyService = Depends(get_policy_service),
) -> Response:
    await policy_service.invalidate_bundle(agent_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/gate/sanitize-output", response_model=SanitizationResult)
async def sanitize_tool_output_endpoint(
    payload: SanitizeToolOutputRequest,
    session: AsyncSession = Depends(get_db),
    gateway: ToolGatewayService = Depends(get_tool_gateway_service),
) -> SanitizationResult:
    return await gateway.sanitize_tool_output(
        payload.output,
        agent_id=payload.agent_id,
        agent_fqn=payload.agent_fqn,
        tool_fqn=payload.tool_fqn,
        execution_id=payload.execution_id,
        workspace_id=payload.workspace_id,
        session=session,
    )


@router.get("/blocked-actions", response_model=PolicyBlockedActionListResponse)
async def list_blocked_actions(
    agent_id: UUID | None = Query(default=None),
    enforcement_component: EnforcementComponent | None = Query(default=None),
    workspace_id: UUID | None = Query(default=None),
    execution_id: UUID | None = Query(default=None),
    since: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyBlockedActionListResponse:
    return await policy_service.list_blocked_action_records(
        agent_id=agent_id,
        enforcement_component=enforcement_component,
        workspace_id=workspace_id,
        execution_id=execution_id,
        since=since,
        page=page,
        page_size=page_size,
    )


@router.get("/blocked-actions/{record_id}", response_model=PolicyBlockedActionRecordResponse)
async def get_blocked_action(
    record_id: UUID,
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyBlockedActionRecordResponse:
    return await policy_service.get_blocked_action_record(record_id)


@router.get("/maturity-gates", response_model=MaturityGateListResponse)
async def get_maturity_gates(
    policy_service: PolicyService = Depends(get_policy_service),
) -> MaturityGateListResponse:
    return await policy_service.get_maturity_gates()


@router.post("", response_model=PolicyWithVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: PolicyCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyWithVersionResponse:
    return await policy_service.create_policy(payload, _actor_id(current_user))


@router.get("", response_model=PolicyListResponse)
async def list_policies(
    request: Request,
    scope_type: PolicyScopeType | None = Query(default=None),
    status: PolicyStatus | None = Query(default=PolicyStatus.active),
    workspace_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyListResponse:
    return await policy_service.list_policies(
        scope_type=scope_type,
        status=status,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        tag_label_filters=parse_tag_label_filters(request),
    )


@router.get("/{policy_id}", response_model=PolicyWithVersionResponse)
async def get_policy(
    policy_id: UUID,
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyWithVersionResponse:
    return await policy_service.get_policy(policy_id)


@router.patch("/{policy_id}", response_model=PolicyWithVersionResponse)
async def update_policy(
    policy_id: UUID,
    payload: PolicyUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyWithVersionResponse:
    return await policy_service.update_policy(policy_id, payload, _actor_id(current_user))


@router.post("/{policy_id}/archive", response_model=PolicyResponse)
async def archive_policy(
    policy_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyResponse:
    return await policy_service.archive_policy(policy_id, _actor_id(current_user))


@router.get("/{policy_id}/versions", response_model=PolicyVersionListResponse)
async def get_policy_versions(
    policy_id: UUID,
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyVersionListResponse:
    return await policy_service.get_version_history(policy_id)


@router.get("/{policy_id}/versions/{version_number}", response_model=PolicyVersionResponse)
async def get_policy_version(
    policy_id: UUID,
    version_number: int,
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyVersionResponse:
    return await policy_service.get_version_by_number(policy_id, version_number)


@router.post(
    "/{policy_id}/attach", response_model=PolicyAttachResponse, status_code=status.HTTP_201_CREATED
)
async def attach_policy(
    policy_id: UUID,
    payload: PolicyAttachRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyAttachResponse:
    return await policy_service.attach_policy(policy_id, payload, _actor_id(current_user))


@router.delete("/{policy_id}/attach/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_policy(
    policy_id: UUID,
    attachment_id: UUID,
    policy_service: PolicyService = Depends(get_policy_service),
) -> Response:
    await policy_service.detach_policy(policy_id, attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{policy_id}/attachments", response_model=PolicyAttachmentListResponse)
async def list_policy_attachments(
    policy_id: UUID,
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyAttachmentListResponse:
    return await policy_service.list_attachments(policy_id)
