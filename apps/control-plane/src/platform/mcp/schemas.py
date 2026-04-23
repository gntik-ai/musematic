from __future__ import annotations

from datetime import datetime
from platform.mcp.models import MCPInvocationDirection, MCPInvocationOutcome, MCPServerStatus
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class MCPToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict, alias="inputSchema")

    @field_validator("name", "description")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class MCPCapabilities(BaseModel):
    model_config = ConfigDict(extra="allow")

    protocol_version: str = Field(alias="protocolVersion")
    capabilities: dict[str, Any] = Field(default_factory=dict)
    server_info: dict[str, Any] = Field(default_factory=dict, alias="serverInfo")


class MCPToolBinding(BaseModel):
    tool_fqn: str
    server_id: UUID
    tool_name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    is_stale: bool = False


class MCPToolResult(BaseModel):
    content: list[dict[str, Any]] = Field(default_factory=list)
    structured_content: dict[str, Any] | list[Any] | None = Field(
        default=None,
        alias="structuredContent",
    )
    is_error: bool = Field(default=False, alias="isError")
    error_code: str | None = None
    error_classification: str | None = None
    retry_safe: bool | None = None


class MCPServerRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)
    endpoint_url: str = Field(min_length=1, max_length=2048)
    auth_config: dict[str, Any] = Field(default_factory=dict)
    catalog_ttl_seconds: int = Field(default=3600, ge=1)

    @field_validator("display_name", "endpoint_url")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class MCPServerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    status: MCPServerStatus | None = None
    catalog_ttl_seconds: int | None = Field(default=None, ge=1)

    @field_validator("display_name")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class MCPServerHealthStatus(BaseModel):
    status: str
    last_success_at: datetime | None = None
    error_count_5m: int = 0
    last_error_at: datetime | None = None


class MCPServerResponse(BaseModel):
    server_id: UUID
    display_name: str
    endpoint_url: str
    status: MCPServerStatus
    catalog_ttl_seconds: int
    last_catalog_fetched_at: datetime | None = None
    catalog_version_snapshot: str | None = None
    catalog_is_stale: bool = False
    tool_count: int = 0
    health: MCPServerHealthStatus | None = None
    created_at: datetime
    created_by: UUID


class MCPServerListResponse(BaseModel):
    items: list[MCPServerResponse]
    total: int
    page: int
    page_size: int


class MCPExposedToolUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcp_tool_name: str = Field(min_length=1, max_length=128)
    mcp_description: str = Field(min_length=1)
    mcp_input_schema: dict[str, Any] = Field(default_factory=dict)
    is_exposed: bool = False

    @field_validator("mcp_tool_name", "mcp_description")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class MCPExposedToolResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None = None
    tool_fqn: str
    mcp_tool_name: str
    mcp_description: str
    mcp_input_schema: dict[str, Any]
    is_exposed: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MCPExposedToolListResponse(BaseModel):
    items: list[MCPExposedToolResponse]
    total: int
    page: int
    page_size: int


class MCPCatalogResponse(BaseModel):
    server_id: UUID
    fetched_at: datetime
    version_snapshot: str | None = None
    is_stale: bool = False
    tool_count: int
    tools: list[MCPToolDefinition]


class MCPInitializeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    protocol_version: str = Field(alias="protocolVersion")
    capabilities: dict[str, Any] = Field(default_factory=dict)
    client_info: dict[str, Any] = Field(default_factory=dict, alias="clientInfo")


class MCPInitializeResponse(BaseModel):
    protocol_version: str = Field(alias="protocolVersion")
    capabilities: dict[str, Any] = Field(default_factory=dict)
    server_info: dict[str, Any] = Field(default_factory=dict, alias="serverInfo")


class MCPToolsListRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class MCPToolsListResponse(BaseModel):
    tools: list[MCPToolDefinition] = Field(default_factory=list)


class MCPToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPToolCallResponse(BaseModel):
    content: list[dict[str, Any]] = Field(default_factory=list)
    structured_content: dict[str, Any] | list[Any] | None = Field(
        default=None,
        alias="structuredContent",
    )
    is_error: bool = Field(default=False, alias="isError")


class MCPAuditRecordResponse(BaseModel):
    id: UUID
    workspace_id: UUID | None
    principal_id: UUID | None
    agent_id: UUID | None
    agent_fqn: str | None
    server_id: UUID | None
    tool_identifier: str
    direction: MCPInvocationDirection
    outcome: MCPInvocationOutcome
    policy_decision: dict[str, Any] | None
    payload_size_bytes: int | None
    error_code: str | None
    error_classification: str | None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
