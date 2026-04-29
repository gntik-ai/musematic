from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SeedScope = Literal[
    'all',
    'users',
    'namespaces',
    'agents',
    'tools',
    'policies',
    'certifiers',
    'fleets',
    'workspace_goals',
]
ResetScope = Literal['all', 'workspaces', 'executions', 'kafka_consumer_offsets']


class SeedRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scope: SeedScope = 'all'


class SeedResponse(BaseModel):
    seeded: dict[str, int] = Field(default_factory=dict)
    skipped: dict[str, int] = Field(default_factory=dict)
    duration_ms: int = 0


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scope: ResetScope = 'all'
    include_baseline: bool = False


class ResetResponse(BaseModel):
    deleted: dict[str, int] = Field(default_factory=dict)
    preserved_baseline: bool = True
    duration_ms: int = 0


class E2EUserProvisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    email: str = Field(pattern=r'^[^@\s]+@e2e\.test$')
    display_name: str | None = None
    password: str = Field(default='e2e-test-password', min_length=1)
    roles: list[str] = Field(default_factory=list)
    status: str = 'active'


class E2EUserProvisionResponse(BaseModel):
    id: UUID
    email: str
    status: str


class ChaosKillPodRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    namespace: str
    label_selector: str
    count: int = Field(default=1, ge=1, le=3)


class ChaosKillPodItem(BaseModel):
    pod: str
    namespace: str
    at: datetime


class ChaosKillPodResponse(BaseModel):
    killed: list[ChaosKillPodItem] = Field(default_factory=list)
    not_found: int = 0


class ChaosPartitionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    from_namespace: str
    to_namespace: str
    ttl_seconds: int = Field(default=30, ge=5, le=300)


class ChaosPartitionResponse(BaseModel):
    network_policy_name: str
    applied_at: datetime
    expires_at: datetime


class MockLLMSetRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt_pattern: str = Field(min_length=1)
    response: str
    streaming_chunks: list[str] | None = None


class MockLLMSetResponse(BaseModel):
    queue_depth: dict[str, int]


class MockLLMRateLimitRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt_pattern: str = Field(min_length=1)
    count: int = Field(default=1, ge=1, le=100)


class MockLLMRateLimitResponse(BaseModel):
    prompt_pattern: str
    remaining: int


class MockLLMClearRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt_pattern: str | None = None


class MockLLMCallsResponse(BaseModel):
    calls: list[dict[str, Any]] = Field(default_factory=list)


class SyntheticFailureInjectRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    correlation_id: str = Field(min_length=1)
    service: str = Field(min_length=1)
    error_message: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)


class SyntheticFailureInjectResponse(BaseModel):
    correlation_id: str
    service: str
    trace_id: str
    emitted: bool = True


class KafkaEventRecord(BaseModel):
    topic: str
    partition: int
    offset: int
    key: str | None = None
    timestamp: datetime
    headers: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any]


class KafkaEventsResponse(BaseModel):
    events: list[KafkaEventRecord] = Field(default_factory=list)
    count: int = 0
