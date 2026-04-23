from __future__ import annotations

from datetime import datetime
from platform.agentops.dependencies import AgentOpsServiceDep, get_agentops_workspace_id
from platform.agentops.schemas import (
    AdaptationApplyRequest,
    AdaptationApplyResponse,
    AdaptationLineageResponse,
    AdaptationOutcomeResponse,
    AdaptationProposalListResponse,
    AdaptationProposalResponse,
    AdaptationReviewRequest,
    AdaptationRevokeRequest,
    AdaptationRevokeResponse,
    AdaptationRollbackRequest,
    AdaptationRollbackResponse,
    AdaptationTriggerRequest,
    AgentHealthConfigResponse,
    AgentHealthConfigUpdateRequest,
    AgentHealthScoreHistoryResponse,
    AgentHealthScoreResponse,
    CanaryDecisionRequest,
    CanaryDeploymentCreateRequest,
    CanaryDeploymentListResponse,
    CanaryDeploymentResponse,
    CiCdGateResultListResponse,
    CiCdGateResultResponse,
    GateCheckRequest,
    GovernanceEventListResponse,
    GovernanceSummaryResponse,
    ProficiencyFleetResponse,
    ProficiencyHistoryResponse,
    ProficiencyResponse,
    RegressionAlertListResponse,
    RegressionAlertResolveRequest,
    RegressionAlertResponse,
    RetirementConfirmRequest,
    RetirementHaltRequest,
    RetirementInitiateRequest,
    RetirementWorkflowResponse,
)
from platform.common.dependencies import get_current_user
from platform.common.exceptions import ValidationError
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/api/v1/agentops", tags=["agentops"])


@router.get("/proficiency", response_model=ProficiencyFleetResponse)
async def get_proficiency_fleet(
    agentops_service: AgentOpsServiceDep,
    *,
    level_at_or_below: str | None = Query(default=None),
    level: str | None = Query(default=None),
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> ProficiencyFleetResponse:
    return await agentops_service.query_proficiency_fleet(
        workspace_id,
        level_at_or_below=level_at_or_below,
        level=level,
    )


@router.get("/health-config", response_model=AgentHealthConfigResponse)
async def get_health_config(
    agentops_service: AgentOpsServiceDep,
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> AgentHealthConfigResponse:
    return await agentops_service.get_health_config(workspace_id)


@router.put("/health-config", response_model=AgentHealthConfigResponse)
async def update_health_config(
    payload: AgentHealthConfigUpdateRequest,
    agentops_service: AgentOpsServiceDep,
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> AgentHealthConfigResponse:
    return await agentops_service.update_health_config(workspace_id, payload)


@router.get("/{agent_fqn}/proficiency", response_model=ProficiencyResponse)
async def get_agent_proficiency(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> ProficiencyResponse:
    return await agentops_service.get_proficiency(agent_fqn, workspace_id)


@router.get("/{agent_fqn}/proficiency/history", response_model=ProficiencyHistoryResponse)
async def get_agent_proficiency_history(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> ProficiencyHistoryResponse:
    return await agentops_service.list_proficiency_history(
        agent_fqn,
        workspace_id,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{agent_fqn}/health", response_model=AgentHealthScoreResponse)
async def get_agent_health(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> AgentHealthScoreResponse:
    return await agentops_service.get_health_score(agent_fqn, workspace_id)


@router.get("/{agent_fqn}/health/history", response_model=AgentHealthScoreHistoryResponse)
async def get_agent_health_history(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> AgentHealthScoreHistoryResponse:
    return await agentops_service.list_health_history(
        agent_fqn,
        workspace_id,
        cursor=cursor,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
    )


@router.get(
    "/{agent_fqn}/regression-alerts",
    response_model=RegressionAlertListResponse,
)
async def list_regression_alerts(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> RegressionAlertListResponse:
    return await agentops_service.list_regression_alerts(
        agent_fqn,
        workspace_id,
        status=status,
        cursor=cursor,
        limit=limit,
    )


@router.post("/{agent_fqn}/gate-check", response_model=CiCdGateResultResponse)
async def run_gate_check(
    agent_fqn: str,
    payload: GateCheckRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> CiCdGateResultResponse:
    resolved_workspace_id = _validate_workspace_scope(payload.workspace_id, workspace_id)
    requested_by = _required_actor_id(current_user)
    return await agentops_service.evaluate_gate_check(
        agent_fqn,
        payload.revision_id,
        resolved_workspace_id,
        requested_by,
    )


@router.get("/{agent_fqn}/gate-checks", response_model=CiCdGateResultListResponse)
async def list_gate_checks(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    revision_id: UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> CiCdGateResultListResponse:
    return await agentops_service.list_gate_checks(
        agent_fqn,
        workspace_id,
        revision_id=revision_id,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/{agent_fqn}/canary",
    response_model=CanaryDeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_canary(
    agent_fqn: str,
    payload: CanaryDeploymentCreateRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> CanaryDeploymentResponse:
    resolved_workspace_id = _validate_workspace_scope(payload.workspace_id, workspace_id)
    return await agentops_service.start_canary(
        agent_fqn,
        payload.model_copy(update={"workspace_id": resolved_workspace_id}),
        initiated_by=_required_actor_id(current_user),
    )


@router.get("/{agent_fqn}/canary/active", response_model=CanaryDeploymentResponse | None)
async def get_active_canary(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> CanaryDeploymentResponse | None:
    return await agentops_service.get_active_canary(agent_fqn, workspace_id)


@router.get("/canaries/{canary_id}", response_model=CanaryDeploymentResponse)
async def get_canary(
    canary_id: UUID,
    agentops_service: AgentOpsServiceDep,
) -> CanaryDeploymentResponse:
    return await agentops_service.get_canary(canary_id)


@router.post("/canaries/{canary_id}/promote", response_model=CanaryDeploymentResponse)
async def promote_canary(
    canary_id: UUID,
    payload: CanaryDecisionRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
) -> CanaryDeploymentResponse:
    return await agentops_service.promote_canary(
        canary_id,
        payload,
        actor=_required_actor_id(current_user),
    )


@router.post("/canaries/{canary_id}/rollback", response_model=CanaryDeploymentResponse)
async def rollback_canary(
    canary_id: UUID,
    payload: CanaryDecisionRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
) -> CanaryDeploymentResponse:
    return await agentops_service.rollback_canary(
        canary_id,
        payload,
        actor=_required_actor_id(current_user),
    )


@router.get("/{agent_fqn}/canaries", response_model=CanaryDeploymentListResponse)
async def list_canaries(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> CanaryDeploymentListResponse:
    return await agentops_service.list_canaries(
        agent_fqn,
        workspace_id,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/{agent_fqn}/retire",
    response_model=RetirementWorkflowResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_retirement(
    agent_fqn: str,
    payload: RetirementInitiateRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> RetirementWorkflowResponse:
    resolved_workspace_id = _validate_workspace_scope(payload.workspace_id, workspace_id)
    return await agentops_service.initiate_retirement(
        agent_fqn,
        payload.model_copy(update={"workspace_id": resolved_workspace_id}),
        actor=_required_actor_id(current_user),
    )


@router.get("/retirements/{workflow_id}", response_model=RetirementWorkflowResponse)
async def get_retirement(
    workflow_id: UUID,
    agentops_service: AgentOpsServiceDep,
) -> RetirementWorkflowResponse:
    return await agentops_service.get_retirement(workflow_id)


@router.post("/retirements/{workflow_id}/halt", response_model=RetirementWorkflowResponse)
async def halt_retirement(
    workflow_id: UUID,
    payload: RetirementHaltRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
) -> RetirementWorkflowResponse:
    return await agentops_service.halt_retirement(
        workflow_id,
        payload,
        actor=_required_actor_id(current_user),
    )


@router.post("/retirements/{workflow_id}/confirm", response_model=RetirementWorkflowResponse)
async def confirm_retirement(
    workflow_id: UUID,
    payload: RetirementConfirmRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
) -> RetirementWorkflowResponse:
    return await agentops_service.confirm_retirement(
        workflow_id,
        payload,
        actor=_required_actor_id(current_user),
    )


@router.get("/{agent_fqn}/governance-events", response_model=GovernanceEventListResponse)
async def list_governance_events(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    event_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> GovernanceEventListResponse:
    return await agentops_service.list_governance_events(
        agent_fqn,
        workspace_id,
        event_type=event_type,
        since=since,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{agent_fqn}/governance", response_model=GovernanceSummaryResponse)
async def get_governance_summary(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> GovernanceSummaryResponse:
    return await agentops_service.get_governance_summary(agent_fqn, workspace_id)


@router.post(
    "/{agent_fqn}/adapt",
    response_model=AdaptationProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def propose_adaptation(
    agent_fqn: str,
    payload: AdaptationTriggerRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
    *,
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> AdaptationProposalResponse:
    resolved_workspace_id = _validate_workspace_scope(payload.workspace_id, workspace_id)
    return await agentops_service.propose_adaptation(
        agent_fqn,
        payload.model_copy(update={"workspace_id": resolved_workspace_id}),
        actor=_required_actor_id(current_user),
    )


@router.post(
    "/adaptations/{proposal_id}/review",
    response_model=AdaptationProposalResponse,
)
async def review_adaptation(
    proposal_id: UUID,
    payload: AdaptationReviewRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
) -> AdaptationProposalResponse:
    return await agentops_service.review_adaptation(
        proposal_id,
        payload,
        actor=_required_actor_id(current_user),
    )


@router.post(
    "/adaptations/{proposal_id}/revoke-approval",
    response_model=AdaptationRevokeResponse,
)
async def revoke_adaptation_approval(
    proposal_id: UUID,
    payload: AdaptationRevokeRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
) -> AdaptationRevokeResponse:
    return await agentops_service.revoke_adaptation_approval(
        proposal_id,
        reason=payload.reason,
        actor=_required_actor_id(current_user),
    )


@router.post(
    "/adaptations/{proposal_id}/apply",
    response_model=AdaptationApplyResponse,
)
async def apply_adaptation(
    proposal_id: UUID,
    payload: AdaptationApplyRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
) -> AdaptationApplyResponse:
    return await agentops_service.apply_adaptation(
        proposal_id,
        actor=_required_actor_id(current_user),
        reason=payload.reason,
    )


@router.post(
    "/adaptations/{proposal_id}/rollback",
    response_model=AdaptationRollbackResponse,
)
async def rollback_adaptation(
    proposal_id: UUID,
    payload: AdaptationRollbackRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
) -> AdaptationRollbackResponse:
    return await agentops_service.rollback_adaptation(
        proposal_id,
        actor=_required_actor_id(current_user),
        reason=payload.reason,
    )


@router.get(
    "/adaptations/{proposal_id}/outcome",
    response_model=AdaptationOutcomeResponse,
)
async def get_adaptation_outcome(
    proposal_id: UUID,
    agentops_service: AgentOpsServiceDep,
) -> AdaptationOutcomeResponse:
    return await agentops_service.get_adaptation_outcome(proposal_id)


@router.get(
    "/adaptations/{proposal_id}/lineage",
    response_model=AdaptationLineageResponse,
)
async def get_adaptation_lineage(
    proposal_id: UUID,
    agentops_service: AgentOpsServiceDep,
) -> AdaptationLineageResponse:
    return await agentops_service.get_adaptation_lineage(proposal_id)


@router.get(
    "/{agent_fqn}/adaptation-history",
    response_model=AdaptationProposalListResponse,
)
async def list_adaptation_history(
    agent_fqn: str,
    agentops_service: AgentOpsServiceDep,
    *,
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    workspace_id: UUID = Depends(get_agentops_workspace_id),
) -> AdaptationProposalListResponse:
    return await agentops_service.list_adaptations(
        agent_fqn,
        workspace_id,
        cursor=cursor,
        limit=limit,
        status=status,
    )


@router.get(
    "/regression-alerts/{alert_id}",
    response_model=RegressionAlertResponse,
)
async def get_regression_alert(
    alert_id: UUID,
    agentops_service: AgentOpsServiceDep,
) -> RegressionAlertResponse:
    return await agentops_service.get_regression_alert(alert_id)


@router.post(
    "/regression-alerts/{alert_id}/resolve",
    response_model=RegressionAlertResponse,
)
async def resolve_regression_alert(
    alert_id: UUID,
    payload: RegressionAlertResolveRequest,
    agentops_service: AgentOpsServiceDep,
    current_user: dict[str, object] = Depends(get_current_user),
) -> RegressionAlertResponse:
    return await agentops_service.resolve_regression_alert(
        alert_id,
        resolution=payload.resolution,
        reason=payload.reason,
        resolved_by=_actor_id(current_user),
    )


def _actor_id(current_user: dict[str, object]) -> UUID | None:
    subject = current_user.get("sub")
    if subject is None:
        return None
    try:
        return UUID(str(subject))
    except ValueError:
        return None


def _required_actor_id(current_user: dict[str, object]) -> UUID:
    actor_id = _actor_id(current_user)
    if actor_id is None:
        raise ValidationError("IDENTITY_REQUIRED", "Authenticated subject is required")
    return actor_id


def _validate_workspace_scope(payload_workspace_id: UUID, request_workspace_id: UUID) -> UUID:
    if payload_workspace_id != request_workspace_id:
        raise ValidationError("WORKSPACE_MISMATCH", "Payload workspace_id does not match request")
    return request_workspace_id
