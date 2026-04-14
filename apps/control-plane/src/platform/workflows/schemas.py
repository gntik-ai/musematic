from __future__ import annotations

from datetime import datetime
from platform.workflows.models import TriggerType, WorkflowStatus
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class WorkflowCreate(BaseModel):
    """Represent the workflow create."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    yaml_source: str = Field(min_length=1)
    change_summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    workspace_id: UUID

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Handle normalize name."""
        return value.strip()

    @field_validator("description", "change_summary")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        """Handle normalize optional."""
        return _clean_optional_text(value)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        """Handle normalize tags."""
        return [item.strip() for item in value if item.strip()]


class WorkflowUpdate(BaseModel):
    """Represent the workflow update."""
    model_config = ConfigDict(extra="forbid")

    yaml_source: str = Field(min_length=1)
    change_summary: str | None = None

    @field_validator("change_summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        """Handle normalize summary."""
        return _clean_optional_text(value)


class WorkflowVersionResponse(BaseModel):
    """Represent the workflow version response payload."""
    id: UUID
    version_number: int
    schema_version: int
    change_summary: str | None
    is_valid: bool
    created_at: datetime
    created_by: UUID | None

    model_config = ConfigDict(from_attributes=True)


class WorkflowResponse(BaseModel):
    """Represent the workflow response payload."""
    id: UUID
    name: str
    description: str | None
    status: WorkflowStatus
    schema_version: int
    tags: list[str]
    current_version: WorkflowVersionResponse | None = None
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowListResponse(BaseModel):
    """Represent the workflow list response payload."""
    items: list[WorkflowResponse]
    total: int


class TriggerCreate(BaseModel):
    """Represent the trigger create."""
    model_config = ConfigDict(extra="forbid")

    trigger_type: TriggerType
    name: str = Field(min_length=1, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    max_concurrent_executions: int | None = Field(default=None, ge=1)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Handle normalize name."""
        return value.strip()


class TriggerResponse(BaseModel):
    """Represent the trigger response payload."""
    id: UUID
    trigger_type: TriggerType
    name: str
    is_active: bool
    config: dict[str, Any]
    max_concurrent_executions: int | None
    last_fired_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TriggerListResponse(BaseModel):
    """Represent the trigger list response payload."""
    items: list[TriggerResponse]
    total: int
