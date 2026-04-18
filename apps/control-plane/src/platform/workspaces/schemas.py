from __future__ import annotations

from datetime import datetime
from platform.workspaces.models import (
    GoalStatus,
    WorkspaceGoalState,
    WorkspaceRole,
    WorkspaceStatus,
)
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def require_mutation(self) -> UpdateWorkspaceRequest:
        if self.name is None and self.description is None:
            raise ValueError("At least one workspace field must be provided")
        return self


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    status: WorkspaceStatus
    owner_id: UUID
    is_default: bool
    created_at: datetime
    updated_at: datetime


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class AddMemberRequest(BaseModel):
    user_id: UUID
    role: WorkspaceRole = WorkspaceRole.member

    @field_validator("role")
    @classmethod
    def reject_owner(cls, value: WorkspaceRole) -> WorkspaceRole:
        if value == WorkspaceRole.owner:
            raise ValueError("Owner role can only be assigned at workspace creation")
        return value


class ChangeMemberRoleRequest(BaseModel):
    role: WorkspaceRole

    @field_validator("role")
    @classmethod
    def reject_owner(cls, value: WorkspaceRole) -> WorkspaceRole:
        if value == WorkspaceRole.owner:
            raise ValueError("Owner role cannot be assigned through membership updates")
        return value


class MembershipResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole
    created_at: datetime


class MemberListResponse(BaseModel):
    items: list[MembershipResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class CreateGoalRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    auto_complete_timeout_seconds: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class UpdateGoalStatusRequest(BaseModel):
    status: GoalStatus


class GoalResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    gid: UUID
    title: str
    description: str | None
    status: GoalStatus
    state: WorkspaceGoalState = WorkspaceGoalState.ready
    auto_complete_timeout_seconds: int | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class GoalListResponse(BaseModel):
    items: list[GoalResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class SetVisibilityGrantRequest(BaseModel):
    visibility_agents: list[str]
    visibility_tools: list[str]

    @field_validator("visibility_agents", "visibility_tools")
    @classmethod
    def normalize_patterns(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class VisibilityGrantResponse(BaseModel):
    workspace_id: UUID
    visibility_agents: list[str]
    visibility_tools: list[str]
    updated_at: datetime


class UpdateSettingsRequest(BaseModel):
    subscribed_agents: list[str] | None = None
    subscribed_fleets: list[UUID] | None = None
    subscribed_policies: list[UUID] | None = None
    subscribed_connectors: list[UUID] | None = None

    @field_validator("subscribed_agents")
    @classmethod
    def normalize_agents(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def require_mutation(self) -> UpdateSettingsRequest:
        if (
            self.subscribed_agents is None
            and self.subscribed_fleets is None
            and self.subscribed_policies is None
            and self.subscribed_connectors is None
        ):
            raise ValueError("At least one settings field must be provided")
        return self


class SettingsResponse(BaseModel):
    workspace_id: UUID
    subscribed_agents: list[str]
    subscribed_fleets: list[UUID]
    subscribed_policies: list[UUID]
    subscribed_connectors: list[UUID]
    updated_at: datetime


class WorkspaceDeletedResponse(BaseModel):
    workspace_id: UUID
    deletion_scheduled: bool = True
