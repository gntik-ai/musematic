from __future__ import annotations

from datetime import datetime
from platform.a2a_gateway.models import A2ATaskState
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class A2AMessagePart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "text"
    text: str | None = None


class A2AMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "agent", "system"]
    parts: list[A2AMessagePart] = Field(default_factory=list)


class A2ATaskSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_fqn: str = Field(min_length=1, max_length=512)
    message: A2AMessage
    conversation_id: UUID | None = None
    protocol_version: str | None = None

    @field_validator("agent_fqn")
    @classmethod
    def _normalize_agent_fqn(cls, value: str) -> str:
        return value.strip()


class A2ATaskResponse(BaseModel):
    task_id: str
    a2a_state: A2ATaskState
    agent_fqn: str
    created_at: datetime


class A2ATaskStatusResponse(BaseModel):
    task_id: str
    a2a_state: A2ATaskState
    agent_fqn: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class A2AFollowUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: A2AMessage


class A2AExternalEndpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    endpoint_url: str = Field(min_length=1, max_length=2048)
    agent_card_url: str = Field(min_length=1, max_length=2048)
    auth_config: dict[str, Any] = Field(default_factory=dict)
    card_ttl_seconds: int = Field(default=3600, ge=1)


class A2AExternalEndpointResponse(BaseModel):
    id: UUID
    name: str
    endpoint_url: str
    agent_card_url: str
    card_ttl_seconds: int
    card_is_stale: bool
    declared_version: str | None = None
    status: str
    card_cached_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class A2AExternalEndpointListResponse(BaseModel):
    items: list[A2AExternalEndpointResponse]
    total: int


class AgentCardAuthentication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme: str
    in_: str = Field(alias="in")
    name: str


class AgentCardSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class AgentCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    url: str
    version: str
    capabilities: list[str] = Field(default_factory=list)
    authentication: list[AgentCardAuthentication] = Field(default_factory=list)
    skills: list[AgentCardSkill] = Field(default_factory=list)


class A2ASSEEvent(BaseModel):
    task_id: str
    state: str
    timestamp: datetime
    prompt: str | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
