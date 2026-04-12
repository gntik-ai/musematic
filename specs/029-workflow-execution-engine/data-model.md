# Data Model: Workflow Definition, Compilation, and Execution

**Branch**: `029-workflow-execution-engine` | **Date**: 2026-04-12 | **Phase**: 1

---

## Enums

```python
# workflows/models.py
class WorkflowStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"

class TriggerType(str, Enum):
    WEBHOOK = "webhook"
    CRON = "cron"
    ORCHESTRATOR = "orchestrator"
    MANUAL = "manual"
    API = "api"
    EVENT_BUS = "event_bus"
    WORKSPACE_GOAL = "workspace_goal"

# execution/models.py
class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    COMPENSATING = "compensating"

class ExecutionEventType(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNTIME_STARTED = "runtime_started"
    SANDBOX_REQUESTED = "sandbox_requested"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVAL_TIMED_OUT = "approval_timed_out"
    RESUMED = "resumed"
    RETRIED = "retried"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"
    HOT_CHANGED = "hot_changed"
    REASONING_TRACE_EMITTED = "reasoning_trace_emitted"
    SELF_CORRECTION_STARTED = "self_correction_started"
    SELF_CORRECTION_CONVERGED = "self_correction_converged"
    CONTEXT_ASSEMBLED = "context_assembled"
    REPRIORITIZED = "reprioritized"

class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    ESCALATED = "escalated"

class CompensationOutcome(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_AVAILABLE = "not_available"

class ApprovalTimeoutAction(str, Enum):
    FAIL = "fail"
    SKIP = "skip"
    ESCALATE = "escalate"
```

---

## SQLAlchemy Models

### Bounded Context: `workflows/`

```python
# apps/control-plane/src/platform/workflows/models.py

class WorkflowDefinition(Base, UUIDMixin, TimestampMixin, AuditMixin, WorkspaceScopedMixin):
    """Named workflow catalog entry. Parent of all versions."""
    __tablename__ = "workflow_definitions"

    name: Mapped[str]                       # unique within workspace, max 200 chars
    description: Mapped[str | None]
    status: Mapped[WorkflowStatus]          # default: active
    current_version_id: Mapped[UUID | None] # FK → workflow_versions.id (nullable until first version)
    schema_version: Mapped[int]             # JSON Schema version used by current_version
    tags: Mapped[list[str]]                 # ARRAY(TEXT), for discovery

    # Relationships
    versions: Mapped[list["WorkflowVersion"]] = relationship(back_populates="definition")
    trigger_definitions: Mapped[list["WorkflowTriggerDefinition"]] = relationship(back_populates="definition")


class WorkflowVersion(Base, UUIDMixin, TimestampMixin):
    """Immutable snapshot of a workflow definition revision."""
    __tablename__ = "workflow_versions"

    definition_id: Mapped[UUID]             # FK → workflow_definitions.id
    version_number: Mapped[int]             # sequential, 1-based
    yaml_source: Mapped[str]                # original YAML text (TEXT, immutable)
    compiled_ir: Mapped[dict]               # JSONB: WorkflowIR serialized
    schema_version: Mapped[int]             # JSON Schema version used for validation
    change_summary: Mapped[str | None]
    created_by: Mapped[UUID]                # FK → users.id (auth context)
    is_valid: Mapped[bool]                  # False if compilation failed (shouldn't reach DB but safety flag)

    # Index: (definition_id, version_number) UNIQUE


class WorkflowTriggerDefinition(Base, UUIDMixin, TimestampMixin):
    """Configuration for how a workflow can be triggered."""
    __tablename__ = "workflow_trigger_definitions"

    definition_id: Mapped[UUID]             # FK → workflow_definitions.id
    trigger_type: Mapped[TriggerType]
    name: Mapped[str]                       # human-readable label
    is_active: Mapped[bool]                 # default: True
    config: Mapped[dict]                    # JSONB: type-specific config
    # Cron: {"cron_expression": "0 9 * * *", "timezone": "Europe/Rome"}
    # Webhook: {"path_suffix": "payments", "secret": "...", "validation_method": "hmac_sha256"}
    # Event-bus: {"topic": "connector.ingress", "event_type_pattern": "order.created"}
    # Workspace-goal: {"workspace_id": "...", "goal_type_pattern": "analyze-*"}
    # Manual/API/Orchestrator: {} or minimal metadata
    max_concurrent_executions: Mapped[int | None]  # None = unlimited
    last_fired_at: Mapped[datetime | None]
```

### Bounded Context: `execution/`

```python
# apps/control-plane/src/platform/execution/models.py

class Execution(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Single execution run of a workflow version."""
    __tablename__ = "executions"

    workflow_version_id: Mapped[UUID]       # FK → workflow_versions.id
    workflow_definition_id: Mapped[UUID]    # FK → workflow_definitions.id (denorm for quick filter)
    trigger_id: Mapped[UUID | None]         # FK → workflow_trigger_definitions.id (null for direct API)
    trigger_type: Mapped[TriggerType]       # denormalized from trigger
    status: Mapped[ExecutionStatus]         # derived from journal but persisted for indexing
    input_parameters: Mapped[dict]          # JSONB: initial input passed to execution
    # Correlation context (all nullable except workspace_id)
    correlation_workspace_id: Mapped[UUID]  # = workspace_id
    correlation_conversation_id: Mapped[UUID | None]
    correlation_interaction_id: Mapped[UUID | None]
    correlation_fleet_id: Mapped[UUID | None]
    correlation_goal_id: Mapped[UUID | None]  # GID per §X
    # Lineage
    parent_execution_id: Mapped[UUID | None]  # FK → executions.id (resume: links to original)
    rerun_of_execution_id: Mapped[UUID | None] # FK → executions.id (rerun: links to original)
    # Timing
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    sla_deadline: Mapped[datetime | None]   # for re-prioritization SLA checks
    created_by: Mapped[UUID | None]         # user who triggered (null for auto triggers)

    # Indices: (workspace_id, status), (workflow_definition_id), (correlation_goal_id)


class ExecutionEvent(Base, UUIDMixin):
    """Append-only execution journal entry. NEVER UPDATE OR DELETE."""
    __tablename__ = "execution_events"

    execution_id: Mapped[UUID]              # FK → executions.id
    sequence: Mapped[int]                   # monotonic within execution (1, 2, 3...)
    event_type: Mapped[ExecutionEventType]
    step_id: Mapped[str | None]             # step identity from workflow IR (null for execution-level events)
    agent_fqn: Mapped[str | None]           # FQN of agent involved (if applicable)
    payload: Mapped[dict]                   # JSONB: type-specific event data
    # Correlation context (snapshot at time of event)
    correlation_workspace_id: Mapped[UUID]
    correlation_conversation_id: Mapped[UUID | None]
    correlation_interaction_id: Mapped[UUID | None]
    correlation_goal_id: Mapped[UUID | None]
    correlation_fleet_id: Mapped[UUID | None]
    correlation_execution_id: Mapped[UUID]  # = execution_id (for CorrelationContext compatibility)
    created_at: Mapped[datetime]            # NOT a TimestampMixin (no updated_at — immutable)

    # Note: NO UUIDMixin updated_at. Single created_at field only.
    # Index: (execution_id, sequence), (execution_id, event_type), (created_at)
    # Constraint: CHECK that no UPDATE/DELETE triggers exist (enforced at application level via INSERT-only repository)


class ExecutionCheckpoint(Base, UUIDMixin, TimestampMixin):
    """Snapshot of execution state at a specific event sequence."""
    __tablename__ = "execution_checkpoints"

    execution_id: Mapped[UUID]              # FK → executions.id
    last_event_sequence: Mapped[int]        # last event sequence included in this checkpoint
    step_results: Mapped[dict]              # JSONB: {step_id: {status, output, completed_at}}
    completed_step_ids: Mapped[list[str]]   # ARRAY(TEXT): list of step_ids completed as of this checkpoint
    pending_step_ids: Mapped[list[str]]     # ARRAY(TEXT): steps not yet started
    active_step_ids: Mapped[list[str]]      # ARRAY(TEXT): steps dispatched but not complete
    execution_data: Mapped[dict]            # JSONB: accumulated output data bindings

    # Index: (execution_id, last_event_sequence DESC)


class ExecutionDispatchLease(Base, UUIDMixin, TimestampMixin):
    """Audit record of dispatch lease for a step. Hot state held in Redis."""
    __tablename__ = "execution_dispatch_leases"

    execution_id: Mapped[UUID]              # FK → executions.id
    step_id: Mapped[str]                    # from workflow IR
    scheduler_worker_id: Mapped[str]        # identity of scheduler worker holding the lease
    acquired_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    released_at: Mapped[datetime | None]
    expired: Mapped[bool]                   # True if TTL elapsed before release

    # Index: (execution_id, step_id, released_at) WHERE released_at IS NULL → active leases


class ExecutionTaskPlanRecord(Base, UUIDMixin, TimestampMixin):
    """Metadata row for a TaskPlanRecord. Full payload in MinIO."""
    __tablename__ = "execution_task_plan_records"

    execution_id: Mapped[UUID]              # FK → executions.id
    step_id: Mapped[str]
    selected_agent_fqn: Mapped[str | None]
    selected_tool_fqn: Mapped[str | None]
    rationale_summary: Mapped[str | None]   # brief summary (truncated at 500 chars)
    considered_agents_count: Mapped[int]    # total agents considered
    considered_tools_count: Mapped[int]
    rejected_alternatives_count: Mapped[int]
    parameter_sources: Mapped[list[str]]    # ARRAY(TEXT): provenance categories (e.g., "user_input", "prev_step_output")
    storage_key: Mapped[str]                # MinIO key: {execution_id}/{step_id}/task-plan.json
    storage_size_bytes: Mapped[int | None]

    # Index: (execution_id), (execution_id, step_id) UNIQUE


class ExecutionApprovalWait(Base, UUIDMixin, TimestampMixin):
    """Record of a step awaiting human approval."""
    __tablename__ = "execution_approval_waits"

    execution_id: Mapped[UUID]              # FK → executions.id
    step_id: Mapped[str]
    required_approvers: Mapped[list[str]]   # ARRAY(TEXT): user_ids or roles
    timeout_at: Mapped[datetime]
    timeout_action: Mapped[ApprovalTimeoutAction]
    decision: Mapped[ApprovalDecision | None]  # null until decided
    decided_by: Mapped[str | None]          # user_id
    decided_at: Mapped[datetime | None]
    interaction_message_id: Mapped[UUID | None]  # FK → interaction_messages.id (cross-context reference, read-only)

    # Index: (execution_id, step_id), (timeout_at) WHERE decision IS NULL


class ExecutionCompensationRecord(Base, UUIDMixin, TimestampMixin):
    """Record of a compensation (undo) operation for a completed step."""
    __tablename__ = "execution_compensation_records"

    execution_id: Mapped[UUID]              # FK → executions.id
    step_id: Mapped[str]
    compensation_handler: Mapped[str]       # handler identifier from workflow IR
    triggered_by: Mapped[str]              # "user", "downstream_failure", "system"
    outcome: Mapped[CompensationOutcome]
    error_detail: Mapped[str | None]        # if outcome=failed
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]

    # Index: (execution_id)
```

---

## IR (Intermediate Representation) Python Types

```python
# apps/control-plane/src/platform/workflows/ir.py
# These are Python dataclasses that are serialized to JSONB.

@dataclass
class RetryConfigIR:
    max_retries: int                         # default 3
    backoff_strategy: str                    # "fixed" | "exponential" | "linear"
    base_delay_seconds: float               # default 5.0
    max_delay_seconds: float                 # default 300.0
    retry_on_event_types: list[str]          # which failure types are retryable

@dataclass
class ApprovalConfigIR:
    required_approvers: list[str]            # user IDs or role names
    timeout_seconds: int                     # default 86400 (24h)
    timeout_action: str                      # "fail" | "skip" | "escalate"

@dataclass
class StepIR:
    step_id: str                             # stable identity (snake_case, unique within workflow)
    step_type: str                           # "agent_task" | "tool_call" | "approval_gate" | "parallel_fork" | "parallel_join" | "conditional"
    agent_fqn: str | None                    # for agent_task steps
    tool_fqn: str | None                     # for tool_call steps
    input_bindings: dict[str, str]           # {param_name: binding_expression}  e.g. {"query": "$.steps.fetch.output.result"}
    output_schema: dict | None               # expected output shape (JSONB)
    retry_config: RetryConfigIR | None
    timeout_seconds: int | None
    compensation_handler: str | None         # step_id of compensation step
    approval_config: ApprovalConfigIR | None
    reasoning_mode: str | None               # "chain_of_thought" | "tree_of_thought" | "direct"
    context_budget_tokens: int | None        # max tokens for context assembly
    parallel_group: str | None               # for parallel_fork/join grouping
    condition_expression: str | None         # for conditional steps

@dataclass
class WorkflowIR:
    schema_version: int
    workflow_id: str                         # workflow definition name (for reference)
    steps: list[StepIR]
    dag_edges: list[tuple[str, str]]         # [(from_step_id, to_step_id)]
    data_bindings: list[dict]                # additional cross-step bindings
    metadata: dict                           # any extra workflow-level config
```

---

## Pydantic Schemas

```python
# apps/control-plane/src/platform/workflows/schemas.py

class WorkflowCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = None
    yaml_source: str                         # raw YAML text
    change_summary: str | None = None
    tags: list[str] = []
    workspace_id: UUID

class WorkflowUpdate(BaseModel):
    yaml_source: str
    change_summary: str | None = None

class WorkflowVersionResponse(BaseModel):
    id: UUID
    version_number: int
    schema_version: int
    change_summary: str | None
    is_valid: bool
    created_at: datetime
    created_by: UUID

class WorkflowResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    status: WorkflowStatus
    schema_version: int
    tags: list[str]
    current_version: WorkflowVersionResponse | None
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime

class WorkflowListResponse(BaseModel):
    items: list[WorkflowResponse]
    total: int

class TriggerCreate(BaseModel):
    trigger_type: TriggerType
    name: str
    config: dict
    max_concurrent_executions: int | None = None

class TriggerResponse(BaseModel):
    id: UUID
    trigger_type: TriggerType
    name: str
    is_active: bool
    config: dict                             # secret fields masked
    max_concurrent_executions: int | None
    last_fired_at: datetime | None


# apps/control-plane/src/platform/execution/schemas.py

class ExecutionCreate(BaseModel):
    workflow_version_id: UUID | None = None  # None = use current version
    workflow_definition_id: UUID
    trigger_type: TriggerType = TriggerType.MANUAL
    input_parameters: dict = {}
    workspace_id: UUID
    correlation_conversation_id: UUID | None = None
    correlation_interaction_id: UUID | None = None
    correlation_fleet_id: UUID | None = None
    correlation_goal_id: UUID | None = None
    sla_deadline: datetime | None = None

class ExecutionResponse(BaseModel):
    id: UUID
    workflow_definition_id: UUID
    workflow_version_id: UUID
    trigger_type: TriggerType
    status: ExecutionStatus
    input_parameters: dict
    workspace_id: UUID
    correlation_goal_id: UUID | None
    parent_execution_id: UUID | None
    rerun_of_execution_id: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    sla_deadline: datetime | None
    created_at: datetime

class ExecutionListResponse(BaseModel):
    items: list[ExecutionResponse]
    total: int

class ExecutionEventResponse(BaseModel):
    id: UUID
    sequence: int
    event_type: ExecutionEventType
    step_id: str | None
    agent_fqn: str | None
    payload: dict
    created_at: datetime

class ExecutionStateResponse(BaseModel):
    execution_id: UUID
    status: ExecutionStatus
    completed_step_ids: list[str]
    active_step_ids: list[str]
    pending_step_ids: list[str]
    step_results: dict                       # {step_id: StepResultSummary}
    last_event_sequence: int

class CheckpointResponse(BaseModel):
    id: UUID
    last_event_sequence: int
    created_at: datetime

class TaskPlanRecordResponse(BaseModel):
    id: UUID
    execution_id: UUID
    step_id: str
    selected_agent_fqn: str | None
    selected_tool_fqn: str | None
    rationale_summary: str | None
    considered_agents_count: int
    considered_tools_count: int
    rejected_alternatives_count: int
    parameter_sources: list[str]
    storage_key: str
    created_at: datetime

class TaskPlanFullResponse(TaskPlanRecordResponse):
    # Extended with full payload from MinIO
    considered_agents: list[dict]            # [{fqn, capabilities, selection_score}]
    considered_tools: list[dict]
    parameters: dict                         # {param: {value, provenance}}
    rejected_alternatives: list[dict]        # [{fqn, reason}]

class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecision               # approved | rejected
    comment: str | None = None

class ReprioritizationEvent(BaseModel):
    execution_id: UUID
    trigger_reason: str
    steps_affected: list[str]
    priority_changes: list[dict]             # [{step_id, old_priority, new_priority}]

class HotChangeRequest(BaseModel):
    new_version_id: UUID

class HotChangeCompatibilityResult(BaseModel):
    compatible: bool
    issues: list[str]                        # empty if compatible
    active_step_ids: list[str]              # steps that were checked
```

---

## Service Signatures

```python
# apps/control-plane/src/platform/workflows/service.py
class WorkflowService:
    async def create_workflow(self, data: WorkflowCreate, session: AsyncSession) -> WorkflowResponse: ...
    async def update_workflow(self, workflow_id: UUID, data: WorkflowUpdate, session: AsyncSession) -> WorkflowResponse: ...
    async def archive_workflow(self, workflow_id: UUID, session: AsyncSession) -> WorkflowResponse: ...
    async def get_workflow(self, workflow_id: UUID, session: AsyncSession) -> WorkflowResponse: ...
    async def list_workflows(self, workspace_id: UUID, status: WorkflowStatus | None, page: int, page_size: int, session: AsyncSession) -> WorkflowListResponse: ...
    async def get_version(self, workflow_id: UUID, version_number: int, session: AsyncSession) -> WorkflowVersionResponse: ...
    async def list_versions(self, workflow_id: UUID, session: AsyncSession) -> list[WorkflowVersionResponse]: ...
    async def create_trigger(self, workflow_id: UUID, data: TriggerCreate, session: AsyncSession) -> TriggerResponse: ...
    async def update_trigger(self, trigger_id: UUID, data: TriggerCreate, session: AsyncSession) -> TriggerResponse: ...
    async def delete_trigger(self, trigger_id: UUID, session: AsyncSession) -> None: ...
    async def list_triggers(self, workflow_id: UUID, session: AsyncSession) -> list[TriggerResponse]: ...
    async def validate_and_compile(self, yaml_source: str) -> WorkflowIR: ...  # sync-like; raises WorkflowCompilationError

# apps/control-plane/src/platform/execution/service.py
class ExecutionService:
    async def create_execution(self, data: ExecutionCreate, session: AsyncSession) -> ExecutionResponse: ...
    async def cancel_execution(self, execution_id: UUID, session: AsyncSession) -> ExecutionResponse: ...
    async def get_execution(self, execution_id: UUID, session: AsyncSession) -> ExecutionResponse: ...
    async def list_executions(self, workspace_id: UUID, workflow_id: UUID | None, status: ExecutionStatus | None, page: int, page_size: int, session: AsyncSession) -> ExecutionListResponse: ...
    async def get_execution_state(self, execution_id: UUID, session: AsyncSession) -> ExecutionStateResponse: ...
    async def get_journal(self, execution_id: UUID, session: AsyncSession) -> list[ExecutionEventResponse]: ...
    async def replay_execution(self, execution_id: UUID, session: AsyncSession) -> ExecutionStateResponse: ...
    async def resume_execution(self, execution_id: UUID, session: AsyncSession) -> ExecutionResponse: ...
    async def rerun_execution(self, execution_id: UUID, input_overrides: dict, session: AsyncSession) -> ExecutionResponse: ...
    async def validate_hot_change(self, execution_id: UUID, new_version_id: UUID, session: AsyncSession) -> HotChangeCompatibilityResult: ...
    async def apply_hot_change(self, execution_id: UUID, new_version_id: UUID, session: AsyncSession) -> ExecutionResponse: ...
    async def record_approval_decision(self, execution_id: UUID, step_id: str, decision: ApprovalDecision, decided_by: UUID, comment: str | None, session: AsyncSession) -> None: ...
    async def trigger_compensation(self, execution_id: UUID, step_id: str, session: AsyncSession) -> None: ...
    async def get_task_plan(self, execution_id: UUID, step_id: str | None, session: AsyncSession) -> TaskPlanFullResponse | list[TaskPlanRecordResponse]: ...

# apps/control-plane/src/platform/execution/scheduler.py
class SchedulerService:
    async def tick(self, session: AsyncSession) -> None: ...  # called by APScheduler every 1s
    async def handle_reprioritization_trigger(self, trigger_reason: str, execution_id: UUID, session: AsyncSession) -> None: ...

# apps/control-plane/src/platform/workflows/compiler.py
class WorkflowCompiler:
    def compile(self, yaml_source: str, schema_version: int) -> WorkflowIR: ...  # sync — CPU-bound
    def validate_compatibility(self, old_ir: WorkflowIR, new_ir: WorkflowIR, active_step_ids: list[str]) -> HotChangeCompatibilityResult: ...  # sync
```

---

## Redis Keys

```
exec:lease:{execution_id}:{step_id}           # Dispatch lease, TTL = step timeout (default 300s)
exec:state:{execution_id}                      # Cached ExecutionStateResponse JSON, TTL 30s
exec:priority_queue:{scheduler_worker_id}      # Sorted set for priority queue (if migrated from in-memory)
exec:sla_watch:{execution_id}                  # TTL = time until SLA deadline, triggers re-prioritization check
```

---

## MinIO Buckets

```
execution-task-plans/
  {execution_id}/{step_id}/task-plan.json       # Full TaskPlanRecord payload

execution-checkpoints/                           # Optional: large checkpoint payloads (fallback only)
  {execution_id}/{checkpoint_id}/state.json
```

---

## Kafka Events Produced

```python
# execution/events.py

class ExecutionCreatedEvent(BaseModel):
    execution_id: UUID
    workflow_definition_id: UUID
    workflow_version_id: UUID
    trigger_type: str
    workspace_id: UUID
    correlation_goal_id: UUID | None

class ExecutionStatusChangedEvent(BaseModel):
    execution_id: UUID
    step_id: str | None
    event_type: ExecutionEventType
    new_status: ExecutionStatus | None
    workspace_id: UUID

class ExecutionReprioritizedEvent(BaseModel):
    execution_id: UUID
    trigger_reason: str
    steps_affected: list[str]
    priority_changes: list[dict]
    workspace_id: UUID

# All wrapped in EventEnvelope with correlation context
# Topic: execution.events, Key: execution_id

# workflows/events.py
class WorkflowPublishedEvent(BaseModel):
    workflow_id: UUID
    version_number: int
    workspace_id: UUID

class TriggerFiredEvent(BaseModel):
    trigger_id: UUID
    workflow_id: UUID
    execution_id: UUID

# Topic: workflow.triggers, Key: workflow_id
```
