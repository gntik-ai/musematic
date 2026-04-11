from __future__ import annotations

from datetime import datetime
from platform.memory.models import (
    ConflictStatus,
    EmbeddingStatus,
    MemoryScope,
    PatternStatus,
    RetentionPolicy,
)
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MemoryWriteRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50_000)
    scope: MemoryScope
    namespace: str = Field(..., min_length=1, max_length=255)
    source_authority: float = Field(default=1.0, ge=0.0, le=1.0)
    retention_policy: RetentionPolicy = RetentionPolicy.permanent
    ttl_seconds: int | None = Field(default=None, gt=0)
    execution_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_retention_fields(self) -> MemoryWriteRequest:
        if self.retention_policy is RetentionPolicy.time_limited and self.ttl_seconds is None:
            raise ValueError("ttl_seconds is required for time-limited retention")
        if self.retention_policy is RetentionPolicy.permanent and self.ttl_seconds is not None:
            raise ValueError("ttl_seconds is not allowed for permanent retention")
        if self.retention_policy is RetentionPolicy.session_only and self.execution_id is None:
            raise ValueError("execution_id is required for session-only retention")
        return self


class RetrievalQuery(BaseModel):
    query_text: str = Field(..., min_length=1, max_length=5_000)
    scope_filter: MemoryScope | None = None
    agent_fqn_filter: str | None = None
    top_k: int = Field(default=10, ge=1, le=50)
    include_contradictions: bool = True
    rrf_k: int = Field(default=60, ge=1, le=1000)


class CrossScopeTransferRequest(BaseModel):
    memory_entry_id: UUID | None = None
    target_scope: MemoryScope
    target_namespace: str = Field(..., min_length=1, max_length=255)


class KnowledgeNodeCreate(BaseModel):
    node_type: str = Field(..., min_length=1, max_length=100)
    external_name: str = Field(..., min_length=1, max_length=500)
    attributes: dict[str, Any] = Field(default_factory=dict)


class KnowledgeEdgeCreate(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    relationship_type: str = Field(..., min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphTraversalQuery(BaseModel):
    start_node_id: UUID
    max_hops: int = Field(default=3, ge=1, le=5)
    relationship_type_filter: str | None = Field(default=None, max_length=100)


class TrajectoryRecordCreate(BaseModel):
    execution_id: UUID
    agent_fqn: str = Field(..., min_length=1, max_length=255)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    tool_invocations: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    verdicts: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None


class PatternNomination(BaseModel):
    trajectory_record_id: UUID | None = None
    content: str = Field(..., min_length=1, max_length=100_000)
    description: str = Field(..., min_length=1, max_length=2_000)
    tags: list[str] = Field(default_factory=list)


class PatternReview(BaseModel):
    approved: bool
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def _validate_rejection_reason(self) -> PatternReview:
        if not self.approved and not self.rejection_reason:
            raise ValueError("rejection_reason is required when rejecting a pattern")
        return self


class ConflictResolution(BaseModel):
    action: Literal["dismiss", "resolve"]
    resolution_notes: str | None = None


class MemoryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    agent_fqn: str
    namespace: str
    scope: MemoryScope
    content: str
    source_authority: float
    retention_policy: RetentionPolicy
    ttl_expires_at: datetime | None
    embedding_status: EmbeddingStatus
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class RetrievalResult(BaseModel):
    memory_entry_id: UUID
    content: str
    scope: MemoryScope
    agent_fqn: str
    source_authority: float
    rrf_score: float
    recency_factor: float
    final_score: float
    sources_contributed: list[Literal["vector", "keyword", "graph"]]
    contradiction_flag: bool
    conflict_ids: list[UUID] = Field(default_factory=list)


class RetrievalResponse(BaseModel):
    results: list[RetrievalResult]
    partial_sources: list[Literal["vector", "keyword", "graph"]] = Field(default_factory=list)
    query_time_ms: float


class WriteGateResult(BaseModel):
    memory_entry_id: UUID
    contradiction_detected: bool
    conflict_id: UUID | None
    privacy_applied: bool
    rate_limit_remaining_min: int
    rate_limit_remaining_hour: int


class EvidenceConflictResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    memory_entry_id_a: UUID
    memory_entry_id_b: UUID
    conflict_description: str
    similarity_score: float
    status: ConflictStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    resolution_notes: str | None = None
    created_at: datetime


class TrajectoryRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    execution_id: UUID
    agent_fqn: str
    actions: list[dict[str, Any]]
    tool_invocations: list[dict[str, Any]]
    reasoning_snapshots: list[dict[str, Any]]
    verdicts: list[dict[str, Any]]
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


class PatternAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    trajectory_record_id: UUID | None
    nominated_by: str
    content: str
    description: str
    tags: list[str]
    status: PatternStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    memory_entry_id: UUID | None
    created_at: datetime


class KnowledgeNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    node_type: str
    external_name: str
    attributes: dict[str, Any]
    created_by_fqn: str
    created_at: datetime


class KnowledgeEdgeResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    relationship_type: str
    metadata: dict[str, Any]
    created_at: datetime


class GraphTraversalResponse(BaseModel):
    paths: list[list[dict[str, Any]]] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    query_time_ms: float = 0.0
    partial_sources: list[Literal["graph"]] = Field(default_factory=list)


class MemoryEntryListResponse(BaseModel):
    items: list[MemoryEntryResponse]
    total: int
    page: int
    page_size: int


class EvidenceConflictListResponse(BaseModel):
    items: list[EvidenceConflictResponse]
    total: int
    page: int
    page_size: int


class PatternAssetListResponse(BaseModel):
    items: list[PatternAssetResponse]
    total: int
    page: int
    page_size: int
