from __future__ import annotations

from datetime import datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from platform.governance.dependencies import GovernanceService, get_governance_service
from platform.governance.schemas import (
    EnforcementActionListQuery,
    EnforcementActionListResponse,
    GovernanceVerdictDetail,
    VerdictListQuery,
    VerdictListResponse,
)
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/governance", tags=["governance"])


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {
        str(item.get("role"))
        for item in roles
        if isinstance(item, dict) and item.get("role") is not None
    }


def _require_roles(current_user: dict[str, Any], accepted: set[str]) -> None:
    if _role_names(current_user) & accepted:
        return
    raise AuthorizationError("AUTHORIZATION_ERROR", "Insufficient role: auditor required")


@router.get("/verdicts", response_model=VerdictListResponse)
async def list_verdicts(
    target_agent_fqn: str | None = Query(default=None),
    judge_agent_fqn: str | None = Query(default=None),
    policy_id: UUID | None = Query(default=None),
    verdict_type: str | None = Query(default=None),
    fleet_id: UUID | None = Query(default=None),
    workspace_id: UUID | None = Query(default=None),
    from_time: datetime | None = Query(default=None),
    to_time: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    governance_service: GovernanceService = Depends(get_governance_service),
) -> VerdictListResponse:
    _require_roles(current_user, {"auditor"})
    return await governance_service.list_verdicts(
        VerdictListQuery(
            target_agent_fqn=target_agent_fqn,
            judge_agent_fqn=judge_agent_fqn,
            policy_id=policy_id,
            verdict_type=verdict_type,
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
            cursor=cursor,
        )
    )


@router.get("/verdicts/{verdict_id}", response_model=GovernanceVerdictDetail)
async def get_verdict(
    verdict_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    governance_service: GovernanceService = Depends(get_governance_service),
) -> GovernanceVerdictDetail:
    _require_roles(current_user, {"auditor"})
    return await governance_service.get_verdict(verdict_id)


@router.get("/enforcement-actions", response_model=EnforcementActionListResponse)
async def list_enforcement_actions(
    action_type: str | None = Query(default=None),
    verdict_id: UUID | None = Query(default=None),
    target_agent_fqn: str | None = Query(default=None),
    workspace_id: UUID | None = Query(default=None),
    from_time: datetime | None = Query(default=None),
    to_time: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    governance_service: GovernanceService = Depends(get_governance_service),
) -> EnforcementActionListResponse:
    _require_roles(current_user, {"auditor"})
    return await governance_service.list_enforcement_actions(
        EnforcementActionListQuery(
            action_type=action_type,
            verdict_id=verdict_id,
            target_agent_fqn=target_agent_fqn,
            workspace_id=workspace_id,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
            cursor=cursor,
        )
    )
