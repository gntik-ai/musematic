from __future__ import annotations

from datetime import datetime
from platform.governance.models import ActionType, VerdictType
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VerdictListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_agent_fqn: str | None = None
    judge_agent_fqn: str | None = None
    policy_id: UUID | None = None
    verdict_type: VerdictType | None = None
    fleet_id: UUID | None = None
    workspace_id: UUID | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None

    @field_validator("target_agent_fqn", "judge_agent_fqn")
    @classmethod
    def _normalize_fqn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class EnforcementActionListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionType | None = None
    verdict_id: UUID | None = None
    target_agent_fqn: str | None = None
    workspace_id: UUID | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None

    @field_validator("target_agent_fqn")
    @classmethod
    def _normalize_target_fqn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class EnforcementActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    enforcer_agent_fqn: str
    verdict_id: UUID
    action_type: ActionType
    target_agent_fqn: str | None
    outcome: dict[str, object] | None
    workspace_id: UUID | None
    created_at: datetime


class GovernanceVerdictRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    judge_agent_fqn: str
    verdict_type: VerdictType
    policy_id: UUID | None
    rationale: str
    recommended_action: str | None
    source_event_id: UUID | None
    fleet_id: UUID | None
    workspace_id: UUID | None
    created_at: datetime


class GovernanceVerdictDetail(GovernanceVerdictRead):
    evidence: dict[str, object]
    enforcement_action: EnforcementActionRead | None = None


class VerdictListResponse(BaseModel):
    items: list[GovernanceVerdictRead]
    total: int
    next_cursor: str | None = None


class EnforcementActionListResponse(BaseModel):
    items: list[EnforcementActionRead]
    total: int
    next_cursor: str | None = None
