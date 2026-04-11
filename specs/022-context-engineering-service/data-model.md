# Data Model: Context Engineering Service

**Feature**: 022-context-engineering-service  
**Date**: 2026-04-11  
**Phase**: 1 — Data model, schemas, service class signatures

---

## 1. PostgreSQL — SQLAlchemy Models

All models in `apps/control-plane/src/platform/context_engineering/models.py`.  
Alembic migration: `apps/control-plane/migrations/versions/007_context_engineering.py`

### Enums

```python
import enum

class CompactionStrategyType(str, enum.Enum):
    RELEVANCE_TRUNCATION = "relevance_truncation"
    PRIORITY_EVICTION = "priority_eviction"
    HIERARCHICAL_COMPRESSION = "hierarchical_compression"
    SEMANTIC_DEDUPLICATION = "semantic_deduplication"

class ContextSourceType(str, enum.Enum):
    SYSTEM_INSTRUCTIONS = "system_instructions"
    WORKFLOW_STATE = "workflow_state"
    CONVERSATION_HISTORY = "conversation_history"
    LONG_TERM_MEMORY = "long_term_memory"
    TOOL_OUTPUTS = "tool_outputs"
    CONNECTOR_PAYLOADS = "connector_payloads"
    WORKSPACE_METADATA = "workspace_metadata"
    REASONING_TRACES = "reasoning_traces"
    WORKSPACE_GOAL_HISTORY = "workspace_goal_history"

class AbTestStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"

class ProfileAssignmentLevel(str, enum.Enum):
    AGENT = "agent"
    ROLE_TYPE = "role_type"
    WORKSPACE = "workspace"
```

### ContextEngineeringProfile

```python
class ContextEngineeringProfile(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "context_engineering_profiles"

    name: Mapped[str]                              # display name
    description: Mapped[str | None]
    is_default: Mapped[bool]                       # workspace-level default flag
    source_config: Mapped[list[dict]]              # JSONB: [{source_type, priority, enabled, max_elements}]
    budget_config: Mapped[dict]                    # JSONB: {max_tokens_step, max_tokens_execution, max_tokens_agent, max_cost_step, max_sources}
    compaction_strategies: Mapped[list[str]]       # JSONB: ordered list of CompactionStrategyType values
    quality_weights: Mapped[dict]                  # JSONB: {relevance, freshness, authority, contradiction, efficiency, coverage}
    privacy_overrides: Mapped[dict]                # JSONB: {allowed_classifications: [...], excluded_source_types: [...]}
    created_by: Mapped[UUID]

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_ce_profile_workspace_name"),
        Index("ix_ce_profile_workspace_default", "workspace_id", "is_default"),
    )
```

### ContextProfileAssignment

```python
class ContextProfileAssignment(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "context_profile_assignments"

    profile_id: Mapped[UUID]                       # FK → context_engineering_profiles.id
    assignment_level: Mapped[ProfileAssignmentLevel]
    agent_fqn: Mapped[str | None]                  # set when level=agent
    role_type: Mapped[str | None]                  # set when level=role_type
    # workspace_id from WorkspaceScopedMixin covers level=workspace

    __table_args__ = (
        Index("ix_ce_assignment_agent_fqn", "agent_fqn"),
        Index("ix_ce_assignment_role_type", "role_type"),
    )
```

### ContextAssemblyRecord

```python
class ContextAssemblyRecord(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "context_assembly_records"

    execution_id: Mapped[UUID]
    step_id: Mapped[UUID]
    agent_fqn: Mapped[str]
    profile_id: Mapped[UUID | None]                # FK → context_engineering_profiles.id (null if default used)
    quality_score_pre: Mapped[float]               # pre-compaction aggregate score
    quality_score_post: Mapped[float]              # post-compaction aggregate score (same as pre if no compaction)
    token_count_pre: Mapped[int]
    token_count_post: Mapped[int]
    sources_queried: Mapped[list[str]]             # JSONB: list of ContextSourceType values
    sources_available: Mapped[list[str]]           # JSONB: sources that responded (partial_sources flag)
    compaction_applied: Mapped[bool]
    compaction_actions: Mapped[list[dict]]         # JSONB: [{strategy, elements_removed, tokens_saved}]
    privacy_exclusions: Mapped[list[dict]]         # JSONB: [{element_id, reason, policy_id}]
    provenance_chain: Mapped[list[dict]]           # JSONB: list of ContextProvenanceEntry
    bundle_storage_key: Mapped[str | None]         # MinIO key for full bundle text
    ab_test_id: Mapped[UUID | None]
    ab_test_group: Mapped[str | None]              # "control" or "variant"
    flags: Mapped[list[str]]                       # JSONB: ["partial_sources", "budget_exceeded_minimum", "zero_quality"]

    __table_args__ = (
        Index("ix_ce_record_execution_step", "execution_id", "step_id"),
        Index("ix_ce_record_agent_fqn_created", "agent_fqn", "created_at"),
        Index("ix_ce_record_workspace_created", "workspace_id", "created_at"),
    )
```

### ContextAbTest

```python
class ContextAbTest(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "context_ab_tests"

    name: Mapped[str]
    control_profile_id: Mapped[UUID]               # FK → context_engineering_profiles.id
    variant_profile_id: Mapped[UUID]               # FK → context_engineering_profiles.id
    target_agent_fqn: Mapped[str | None]           # null = apply to entire workspace
    status: Mapped[AbTestStatus]                   # default: active
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    created_by: Mapped[UUID]

    # Aggregated metrics (updated by background task or on-demand)
    control_assembly_count: Mapped[int]            # default: 0
    variant_assembly_count: Mapped[int]            # default: 0
    control_quality_mean: Mapped[float | None]
    variant_quality_mean: Mapped[float | None]
    control_token_mean: Mapped[float | None]
    variant_token_mean: Mapped[float | None]
```

### ContextDriftAlert

```python
class ContextDriftAlert(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "context_drift_alerts"

    agent_fqn: Mapped[str]
    historical_mean: Mapped[float]
    historical_stddev: Mapped[float]
    recent_mean: Mapped[float]
    degradation_delta: Mapped[float]               # historical_mean - recent_mean
    analysis_window_days: Mapped[int]
    suggested_actions: Mapped[list[str]]           # JSONB: list of action strings
    resolved_at: Mapped[datetime | None]           # null = unresolved

    __table_args__ = (
        Index("ix_ce_drift_alert_agent_fqn", "agent_fqn"),
        Index("ix_ce_drift_alert_workspace_resolved", "workspace_id", "resolved_at"),
    )
```

---

## 2. ClickHouse — Quality Score Time-Series

Created by `context_engineering_clickhouse_setup.py` at startup (idempotent).

```sql
CREATE TABLE IF NOT EXISTS context_quality_scores (
    agent_fqn       String,
    workspace_id    UUID,
    assembly_id     UUID,
    quality_score   Float32,
    quality_subscores JSON,   -- {relevance, freshness, authority, contradiction, efficiency, coverage}
    token_count     UInt32,
    ab_test_id      Nullable(UUID),
    ab_test_group   Nullable(String),
    created_at      DateTime
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (agent_fqn, created_at)
TTL created_at + INTERVAL 90 DAY;
```

---

## 3. MinIO — Context Assembly Bundle Storage

Bucket: `context-assembly-records`  
Object key: `{workspace_id}/{execution_id}/{step_id}/bundle.json`

Bundle JSON structure:
```json
{
  "assembly_id": "uuid",
  "execution_id": "uuid",
  "step_id": "uuid",
  "elements": [
    {
      "id": "uuid",
      "source_type": "conversation_history",
      "content": "...",
      "token_count": 123,
      "provenance": {
        "origin": "conversation:conv-abc123",
        "timestamp": "2026-04-11T10:00:00Z",
        "authority_score": 0.8,
        "policy_justification": "included: source type allowed by profile"
      }
    }
  ],
  "assembled_at": "2026-04-11T10:00:05Z"
}
```

---

## 4. Pydantic Schemas

All in `apps/control-plane/src/platform/context_engineering/schemas.py`.

### Core Assembly Types (internal + API)

```python
class ContextProvenanceEntry(BaseModel):
    origin: str                              # e.g., "conversation:conv-abc123"
    timestamp: datetime
    authority_score: float = Field(ge=0.0, le=1.0)
    policy_justification: str
    action: Literal["included", "excluded"] = "included"
    exclusion_policy_id: UUID | None = None

class ContextElement(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_type: ContextSourceType
    content: str
    token_count: int
    priority: int                            # from profile source config
    provenance: ContextProvenanceEntry

class ContextBundle(BaseModel):
    assembly_id: UUID
    execution_id: UUID
    step_id: UUID
    agent_fqn: str
    elements: list[ContextElement]           # ordered, filtered, compacted
    quality_score: float
    quality_subscores: dict[str, float]
    token_count: int
    compaction_applied: bool
    flags: list[str]

class ContextQualityScore(BaseModel):
    relevance: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    authority: float = Field(ge=0.0, le=1.0)
    contradiction_density: float = Field(ge=0.0, le=1.0)  # inverted: higher = less contradiction
    token_efficiency: float = Field(ge=0.0, le=1.0)
    task_brief_coverage: float = Field(ge=0.0, le=1.0)
    aggregate: float = Field(ge=0.0, le=1.0)
```

### Budget and Profile Schemas

```python
class BudgetEnvelope(BaseModel):
    max_tokens_step: int = 8192
    max_tokens_execution: int | None = None
    max_tokens_agent: int | None = None
    max_cost_step: float | None = None       # in USD
    max_sources: int = 9                     # all source types

class SourceConfig(BaseModel):
    source_type: ContextSourceType
    priority: int = Field(ge=1, le=100)      # higher = higher priority in eviction
    enabled: bool = True
    max_elements: int = 10                   # max elements from this source

class ProfileCreate(BaseModel):
    name: str
    description: str | None = None
    source_config: list[SourceConfig]
    budget_config: BudgetEnvelope
    compaction_strategies: list[CompactionStrategyType] = [
        CompactionStrategyType.RELEVANCE_TRUNCATION,
        CompactionStrategyType.PRIORITY_EVICTION,
        CompactionStrategyType.SEMANTIC_DEDUPLICATION,
    ]
    quality_weights: dict[str, float] = {}   # defaults in service
    privacy_overrides: dict[str, Any] = {}
    is_default: bool = False

class ProfileAssignmentCreate(BaseModel):
    profile_id: UUID
    assignment_level: ProfileAssignmentLevel
    agent_fqn: str | None = None
    role_type: str | None = None

class ProfileResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_default: bool
    source_config: list[SourceConfig]
    budget_config: BudgetEnvelope
    compaction_strategies: list[CompactionStrategyType]
    workspace_id: UUID
    created_at: datetime
```

### A/B Test Schemas

```python
class AbTestCreate(BaseModel):
    name: str
    control_profile_id: UUID
    variant_profile_id: UUID
    target_agent_fqn: str | None = None

class AbTestResponse(BaseModel):
    id: UUID
    name: str
    status: AbTestStatus
    control_profile_id: UUID
    variant_profile_id: UUID
    target_agent_fqn: str | None
    control_assembly_count: int
    variant_assembly_count: int
    control_quality_mean: float | None
    variant_quality_mean: float | None
    started_at: datetime
    ended_at: datetime | None
```

### Assembly Record Schemas

```python
class AssemblyRecordResponse(BaseModel):
    id: UUID
    execution_id: UUID
    step_id: UUID
    agent_fqn: str
    quality_score_pre: float
    quality_score_post: float
    token_count_pre: int
    token_count_post: int
    compaction_applied: bool
    sources_queried: list[str]
    sources_available: list[str]
    privacy_exclusions: list[dict]
    flags: list[str]
    ab_test_group: str | None
    created_at: datetime

class DriftAlertResponse(BaseModel):
    id: UUID
    agent_fqn: str
    workspace_id: UUID
    historical_mean: float
    historical_stddev: float
    recent_mean: float
    degradation_delta: float
    suggested_actions: list[str]
    resolved_at: datetime | None
    created_at: datetime
```

---

## 5. Context Source Adapter Protocol

`apps/control-plane/src/platform/context_engineering/adapters.py`

```python
from typing import Protocol

class ContextSourceAdapter(Protocol):
    source_type: ContextSourceType

    async def fetch(
        self,
        execution_id: UUID,
        step_id: UUID,
        budget: BudgetEnvelope,
        max_elements: int = 10,
    ) -> list[ContextElement]: ...

# Concrete adapters (each in adapters.py):
class SystemInstructionsAdapter:      # reads agent purpose + approach from registry_service
class WorkflowStateAdapter:           # reads from execution_service
class ConversationHistoryAdapter:     # reads from interactions_service
class LongTermMemoryAdapter:          # queries Qdrant agent_memory collection
class ToolOutputsAdapter:             # reads from execution_service step outputs
class ConnectorPayloadsAdapter:       # reads from connectors_service
class WorkspaceMetadataAdapter:       # reads from workspaces_service
class ReasoningTracesAdapter:         # reads from execution_service reasoning store
class WorkspaceGoalHistoryAdapter:    # reads WorkspaceGoalMessages from workspaces_service
```

---

## 6. Service Classes

### ContextEngineeringService

`apps/control-plane/src/platform/context_engineering/service.py`

```python
class ContextEngineeringService:
    def __init__(
        self,
        repository: ContextEngineeringRepository,
        adapters: dict[ContextSourceType, ContextSourceAdapter],
        quality_scorer: QualityScorer,
        compactor: ContextCompactor,
        privacy_filter: PrivacyFilter,
        object_storage: ObjectStorageClient,
        clickhouse: ClickHouseClient,
        event_producer: KafkaProducer,
        policies_service: PoliciesService,
    ): ...

    # PRIMARY INTERNAL INTERFACE (called by execution bounded context)
    async def assemble_context(
        self,
        execution_id: UUID,
        step_id: UUID,
        agent_fqn: str,
        workspace_id: UUID,
        goal_id: UUID | None,
        profile: ContextEngineeringProfile | None,
        budget: BudgetEnvelope,
    ) -> ContextBundle: ...
    # Pipeline: resolve profile → fetch sources → privacy filter → quality score
    # → budget check → compaction (if needed) → re-score → persist record → emit event

    # PROFILE MANAGEMENT
    async def create_profile(self, workspace_id: UUID, params: ProfileCreate, actor_id: UUID) -> ContextEngineeringProfile: ...
    async def get_profile(self, workspace_id: UUID, profile_id: UUID) -> ContextEngineeringProfile: ...
    async def list_profiles(self, workspace_id: UUID) -> list[ContextEngineeringProfile]: ...
    async def update_profile(self, workspace_id: UUID, profile_id: UUID, params: ProfileCreate, actor_id: UUID) -> ContextEngineeringProfile: ...
    async def delete_profile(self, workspace_id: UUID, profile_id: UUID) -> None: ...
    async def assign_profile(self, workspace_id: UUID, params: ProfileAssignmentCreate, actor_id: UUID) -> ContextProfileAssignment: ...
    async def resolve_profile(self, agent_fqn: str, workspace_id: UUID) -> ContextEngineeringProfile: ...
    # Resolution order: agent-specific → role_type match → workspace default → built-in default

    # A/B TESTING
    async def create_ab_test(self, workspace_id: UUID, params: AbTestCreate, actor_id: UUID) -> ContextAbTest: ...
    async def get_ab_test(self, workspace_id: UUID, test_id: UUID) -> ContextAbTest: ...
    async def end_ab_test(self, workspace_id: UUID, test_id: UUID, actor_id: UUID) -> ContextAbTest: ...
    async def get_ab_test_results(self, workspace_id: UUID, test_id: UUID) -> AbTestResponse: ...
    async def _resolve_ab_test_profile(self, agent_fqn: str, workspace_id: UUID) -> tuple[ContextEngineeringProfile, str | None]: ...
    # Returns (profile, ab_group) where ab_group is "control"/"variant"/None

    # DRIFT MONITORING (called by DriftMonitorTask)
    async def run_drift_analysis(self) -> list[ContextDriftAlert]: ...

    # QUERY API
    async def list_assembly_records(self, workspace_id: UUID, agent_fqn: str | None, limit: int, offset: int) -> list[AssemblyRecordResponse]: ...
    async def list_drift_alerts(self, workspace_id: UUID, resolved: bool | None) -> list[DriftAlertResponse]: ...
```

### QualityScorer

`apps/control-plane/src/platform/context_engineering/quality_scorer.py`

```python
class QualityScorer:
    SOURCE_AUTHORITY: dict[ContextSourceType, float] = {
        ContextSourceType.SYSTEM_INSTRUCTIONS: 1.0,
        ContextSourceType.TOOL_OUTPUTS: 0.9,
        ContextSourceType.CONVERSATION_HISTORY: 0.8,
        ContextSourceType.WORKFLOW_STATE: 0.85,
        ContextSourceType.LONG_TERM_MEMORY: 0.7,
        ContextSourceType.REASONING_TRACES: 0.75,
        ContextSourceType.CONNECTOR_PAYLOADS: 0.6,
        ContextSourceType.WORKSPACE_METADATA: 0.5,
        ContextSourceType.WORKSPACE_GOAL_HISTORY: 0.75,
    }

    async def score(
        self,
        elements: list[ContextElement],
        task_brief: str,
        weights: dict[str, float],
    ) -> ContextQualityScore: ...

    def _score_relevance(self, elements: list[ContextElement], task_brief: str) -> float: ...
    def _score_freshness(self, elements: list[ContextElement]) -> float: ...
    def _score_authority(self, elements: list[ContextElement]) -> float: ...
    def _score_contradiction_density(self, elements: list[ContextElement]) -> float: ...
    def _score_token_efficiency(self, elements: list[ContextElement]) -> float: ...
    def _score_task_brief_coverage(self, elements: list[ContextElement], task_brief: str) -> float: ...
```

### ContextCompactor

`apps/control-plane/src/platform/context_engineering/compactor.py`

```python
class ContextCompactor:
    MINIMUM_VIABLE_SOURCES = {
        ContextSourceType.SYSTEM_INSTRUCTIONS,
        # plus most recent conversation turn (by timestamp)
    }

    async def compact(
        self,
        elements: list[ContextElement],
        budget: BudgetEnvelope,
        strategies: list[CompactionStrategyType],
    ) -> tuple[list[ContextElement], list[dict]]:
        """Returns (compacted_elements, compaction_actions)"""
        ...

    def _relevance_truncate(self, elements: list[ContextElement], target_tokens: int) -> ...: ...
    def _priority_evict(self, elements: list[ContextElement], target_tokens: int) -> ...: ...
    def _semantic_deduplicate(self, elements: list[ContextElement]) -> ...: ...
    async def _hierarchical_compress(self, elements: list[ContextElement]) -> ...: ...  # LLM call
    def _count_tokens(self, elements: list[ContextElement]) -> int: ...
    def _is_minimum_viable(self, element: ContextElement) -> bool: ...
```

### PrivacyFilter

`apps/control-plane/src/platform/context_engineering/privacy_filter.py`

```python
class PrivacyFilter:
    async def filter(
        self,
        elements: list[ContextElement],
        agent_fqn: str,
        workspace_id: UUID,
    ) -> tuple[list[ContextElement], list[dict]]:
        """Returns (allowed_elements, exclusion_records)"""
        # Fetches active context policies via policies_service
        # Evaluates each element's data classification against agent's allowed level
        # Returns exclusion records for ContextAssemblyRecord.privacy_exclusions
        ...
```

### DriftMonitorTask

`apps/control-plane/src/platform/context_engineering/drift_monitor.py`

```python
class DriftMonitorTask:
    """APScheduler background task, registered in scheduler_main.py"""

    async def run(self) -> None:
        """
        Runs every 5 minutes.
        Queries ClickHouse for per-agent quality score stats.
        Compares historical window (7d ago to 1d ago) vs recent window (1d ago to now).
        Creates ContextDriftAlert in PostgreSQL for degraded agents.
        Emits context_engineering.drift.detected Kafka event.
        """

    async def _query_quality_stats(self, window_days: int) -> list[dict]: ...
    async def _detect_degradation(self, historical: dict, recent: dict) -> bool: ...
```

---

## 7. Events

`apps/control-plane/src/platform/context_engineering/events.py`

```python
# Topic: context_engineering.events

class AssemblyCompletedPayload(BaseModel):
    assembly_id: str
    execution_id: str
    step_id: str
    agent_fqn: str
    workspace_id: str
    quality_score: float
    token_count: int
    compaction_applied: bool
    ab_test_group: str | None

class DriftDetectedPayload(BaseModel):
    alert_id: str
    agent_fqn: str
    workspace_id: str
    historical_mean: float
    recent_mean: float
    degradation_delta: float

class BudgetExceededMinimumPayload(BaseModel):
    assembly_id: str
    execution_id: str
    agent_fqn: str
    workspace_id: str
    budget_tokens: int
    minimum_tokens: int

async def publish_assembly_completed(...): ...
async def publish_drift_detected(...): ...
async def publish_budget_exceeded_minimum(...): ...
```
