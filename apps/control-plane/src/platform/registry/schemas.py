from __future__ import annotations

from datetime import datetime
from platform.registry.models import AgentRoleType, EmbeddingStatus, LifecycleStatus, MaturityLevel
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,62}$"
SEMVER_PATTERN = r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$"


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_string_list(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value if item.strip()]


class AgentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_name: str = Field(pattern=SLUG_PATTERN)
    version: str = Field(pattern=SEMVER_PATTERN)
    purpose: str = Field(min_length=50)
    role_types: list[AgentRoleType] = Field(min_length=1)
    approach: str | None = None
    maturity_level: MaturityLevel = MaturityLevel.unverified
    reasoning_modes: list[str] = Field(default_factory=list)
    context_profile: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    display_name: str | None = None
    custom_role_description: str | None = None
    mcp_servers: list[str] = Field(default_factory=list)
    data_categories: list[str] = Field(default_factory=list)

    @field_validator("purpose")
    @classmethod
    def normalize_purpose(cls, value: str) -> str:
        return value.strip()

    @field_validator("approach", "display_name", "custom_role_description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("reasoning_modes", "tags", "mcp_servers", "data_categories", mode="before")
    @classmethod
    def normalize_list_fields(cls, value: list[str] | None) -> list[str]:
        if value is None:
            return []
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def custom_role_requires_description(self) -> AgentManifest:
        if AgentRoleType.custom in self.role_types and not self.custom_role_description:
            raise ValueError(
                "custom_role_description is required when role_types contains 'custom'"
            )
        return self


class NamespaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=SLUG_PATTERN)
    description: str | None = None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class AgentUploadParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace_name: str = Field(pattern=SLUG_PATTERN)


class AgentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    purpose: str | None = Field(default=None, min_length=50)
    approach: str | None = None
    tags: list[str] | None = None
    visibility_agents: list[str] | None = None
    visibility_tools: list[str] | None = None
    mcp_servers: list[str] | None = None
    data_categories: list[str] | None = None
    role_types: list[AgentRoleType] | None = None
    custom_role_description: str | None = None
    default_model_binding: str | None = Field(default=None, max_length=128)

    @field_validator("display_name", "purpose", "approach", "custom_role_description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator(
        "tags",
        "visibility_agents",
        "visibility_tools",
        "mcp_servers",
        "data_categories",
    )
    @classmethod
    def normalize_list_fields(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def validate_custom_role(self) -> AgentPatch:
        if (
            self.role_types
            and AgentRoleType.custom in self.role_types
            and not self.custom_role_description
        ):
            raise ValueError(
                "custom_role_description is required when role_types contains 'custom'"
            )
        return self

    @field_validator("default_model_binding")
    @classmethod
    def normalize_model_binding(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class AgentDecommissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class AgentDecommissionResponse(BaseModel):
    agent_id: UUID
    agent_fqn: str
    decommissioned_at: datetime
    decommission_reason: str
    decommissioned_by: UUID
    active_instances_stopped: int


class LifecycleTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: LifecycleStatus
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class MaturityUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maturity_level: MaturityLevel
    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class AgentDiscoveryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID | None = None
    fqn_pattern: str | None = None
    keyword: str | None = None
    maturity_min: int = Field(default=0, ge=0, le=3)
    status: LifecycleStatus = LifecycleStatus.published
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("fqn_pattern", "keyword")
    @classmethod
    def normalize_optional_query(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class NamespaceResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    workspace_id: UUID
    created_at: datetime
    created_by: UUID


class NamespaceListResponse(BaseModel):
    items: list[NamespaceResponse]
    total: int


class AgentRevisionResponse(BaseModel):
    id: UUID
    agent_profile_id: UUID
    version: str
    sha256_digest: str
    storage_key: str
    manifest_snapshot: dict[str, Any]
    uploaded_by: UUID
    created_at: datetime


class AgentRevisionListResponse(BaseModel):
    items: list[AgentRevisionResponse]
    total: int


class AgentProfileResponse(BaseModel):
    id: UUID
    namespace_id: UUID
    fqn: str
    display_name: str | None
    purpose: str
    approach: str | None
    role_types: list[str]
    custom_role_description: str | None
    visibility_agents: list[str]
    visibility_tools: list[str]
    tags: list[str]
    mcp_servers: list[str] = Field(default_factory=list)
    data_categories: list[str] = Field(default_factory=list)
    status: LifecycleStatus
    maturity_level: int
    embedding_status: EmbeddingStatus
    workspace_id: UUID
    created_at: datetime
    current_revision: AgentRevisionResponse | None = None
    default_model_binding: str | None = None


class AgentUploadResponse(BaseModel):
    agent_profile: AgentProfileResponse
    revision: AgentRevisionResponse
    created: bool


class AgentListResponse(BaseModel):
    items: list[AgentProfileResponse]
    total: int
    limit: int
    offset: int


class LifecycleAuditResponse(BaseModel):
    id: UUID
    agent_profile_id: UUID
    previous_status: LifecycleStatus
    new_status: LifecycleStatus
    actor_id: UUID
    reason: str | None
    created_at: datetime


class LifecycleAuditListResponse(BaseModel):
    items: list[LifecycleAuditResponse]
    total: int


class PackageValidationError(BaseModel):
    error_type: str
    detail: str
    field: str | None = None
