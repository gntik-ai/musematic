# Data Model: Dynamic Re-Prioritization and Checkpoint/Rollback

**Feature**: 063-reprioritization-and-checkpoints  
**Migration**: `050_reprioritization_and_checkpoints.py`  
**Date**: 2026-04-19

---

## Migration 050: DDL

```sql
-- ============================================================
-- 1. Extend execution_checkpoints (already exists, migration 012)
-- ============================================================
ALTER TABLE execution_checkpoints
    ADD COLUMN IF NOT EXISTS checkpoint_number    INTEGER,
    ADD COLUMN IF NOT EXISTS current_context      JSONB,
    ADD COLUMN IF NOT EXISTS accumulated_costs    JSONB,
    ADD COLUMN IF NOT EXISTS superseded           BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS policy_snapshot      JSONB;

-- Backfill checkpoint_number for existing rows (per-execution row_number by created_at)
-- Executed as a data migration in the Alembic Python migration body
-- UPDATE execution_checkpoints ec
-- SET checkpoint_number = sub.rn
-- FROM (
--     SELECT id, ROW_NUMBER() OVER (PARTITION BY execution_id ORDER BY created_at) AS rn
--     FROM execution_checkpoints
-- ) sub
-- WHERE ec.id = sub.id;

-- Set NOT NULL and unique constraint after backfill
ALTER TABLE execution_checkpoints
    ALTER COLUMN checkpoint_number SET NOT NULL;

ALTER TABLE execution_checkpoints
    ADD CONSTRAINT uq_execution_checkpoint_number
        UNIQUE (execution_id, checkpoint_number);

-- Index for superseded lookups
CREATE INDEX IF NOT EXISTS ix_execution_checkpoints_execution_superseded
    ON execution_checkpoints (execution_id, superseded);

-- ============================================================
-- 2. Extend executions table
-- ============================================================
ALTER TABLE executions
    ADD COLUMN IF NOT EXISTS checkpoint_policy_snapshot JSONB;

-- ============================================================
-- 3. Extend workflow_versions table
-- ============================================================
ALTER TABLE workflow_versions
    ADD COLUMN IF NOT EXISTS checkpoint_policy JSONB;

-- ============================================================
-- 4. New table: reprioritization_triggers
-- ============================================================
CREATE TABLE IF NOT EXISTS reprioritization_triggers (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID        REFERENCES workspaces(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    trigger_type    VARCHAR(50)  NOT NULL,       -- 'sla_approach'
    condition_config JSONB       NOT NULL,        -- type-specific params
    action          VARCHAR(50)  NOT NULL,        -- 'promote_to_front' | 'demote' | 'reorder'
    priority_rank   INTEGER      NOT NULL DEFAULT 100,
    enabled         BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by      UUID,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_reprioritization_triggers_workspace
    ON reprioritization_triggers (workspace_id)
    WHERE workspace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_reprioritization_triggers_global
    ON reprioritization_triggers (trigger_type, enabled)
    WHERE workspace_id IS NULL;

-- ============================================================
-- 5. New table: execution_rollback_actions
-- ============================================================
CREATE TABLE IF NOT EXISTS execution_rollback_actions (
    id                       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id             UUID         NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    target_checkpoint_id     UUID         NOT NULL REFERENCES execution_checkpoints(id),
    target_checkpoint_number INTEGER      NOT NULL,
    initiated_by             UUID,
    cost_delta_reversed      JSONB,
    status                   VARCHAR(50)  NOT NULL DEFAULT 'completed',
    failure_reason           TEXT,
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_execution_rollback_actions_execution
    ON execution_rollback_actions (execution_id);

-- ============================================================
-- 6. Extend ExecutionStatus enum (additive — Brownfield Rule 6)
-- ============================================================
ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'paused';
ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'rolled_back';
ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'rollback_failed';

-- ============================================================
-- 7. Extend ExecutionEventType enum (additive — Brownfield Rule 6)
-- ============================================================
ALTER TYPE executioneventtype ADD VALUE IF NOT EXISTS 'rolled_back';
```

---

## SQLAlchemy Model Extensions

### `apps/control-plane/src/platform/execution/models.py`

#### Add to `ExecutionStatus` enum
```python
# Existing values: queued, running, waiting_for_approval, completed, failed, canceled, compensating
paused         = "paused"
rolled_back    = "rolled_back"
rollback_failed = "rollback_failed"
```

#### Add to `ExecutionEventType` enum
```python
# Existing: ... reprioritized
rolled_back = "rolled_back"
```

#### Extend `ExecutionCheckpoint` model
```python
class ExecutionCheckpoint(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "execution_checkpoints"

    execution_id:      Mapped[uuid.UUID]      = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), nullable=False, index=True)
    last_event_sequence: Mapped[int]          = mapped_column(Integer, nullable=False)
    checkpoint_number: Mapped[int]            = mapped_column(Integer, nullable=False)  # NEW
    step_results:      Mapped[dict]           = mapped_column(JSONB, nullable=False, default=dict)
    completed_step_ids: Mapped[list[str]]     = mapped_column(ARRAY(Text), nullable=False, default=list)
    pending_step_ids:  Mapped[list[str]]      = mapped_column(ARRAY(Text), nullable=False, default=list)
    active_step_ids:   Mapped[list[str]]      = mapped_column(ARRAY(Text), nullable=False, default=list)
    execution_data:    Mapped[dict]           = mapped_column(JSONB, nullable=False, default=dict)
    current_context:   Mapped[dict | None]    = mapped_column(JSONB, nullable=True)        # NEW
    accumulated_costs: Mapped[dict | None]    = mapped_column(JSONB, nullable=True)        # NEW
    superseded:        Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)  # NEW
    policy_snapshot:   Mapped[dict | None]    = mapped_column(JSONB, nullable=True)        # NEW

    __table_args__ = (
        UniqueConstraint("execution_id", "checkpoint_number", name="uq_execution_checkpoint_number"),
        Index("ix_execution_checkpoints_execution_superseded", "execution_id", "superseded"),
    )
```

#### Extend `Execution` model
```python
# Add to Execution model:
checkpoint_policy_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # NEW
```

#### New model `ReprioritizationTrigger`
```python
class ReprioritizationTrigger(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "reprioritization_triggers"

    workspace_id:     Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    name:             Mapped[str]              = mapped_column(String(200), nullable=False)
    trigger_type:     Mapped[str]              = mapped_column(String(50), nullable=False)   # 'sla_approach'
    condition_config: Mapped[dict]             = mapped_column(JSONB, nullable=False)
    action:           Mapped[str]              = mapped_column(String(50), nullable=False)   # 'promote_to_front' | 'demote'
    priority_rank:    Mapped[int]              = mapped_column(Integer, nullable=False, default=100)
    enabled:          Mapped[bool]             = mapped_column(Boolean, nullable=False, default=True)
    created_by:       Mapped[uuid.UUID | None] = mapped_column(nullable=True)
```

#### New model `ExecutionRollbackAction`
```python
class ExecutionRollbackAction(Base, UUIDMixin):
    __tablename__ = "execution_rollback_actions"

    execution_id:              Mapped[uuid.UUID]      = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), nullable=False, index=True)
    target_checkpoint_id:      Mapped[uuid.UUID]      = mapped_column(ForeignKey("execution_checkpoints.id"), nullable=False)
    target_checkpoint_number:  Mapped[int]            = mapped_column(Integer, nullable=False)
    initiated_by:              Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    cost_delta_reversed:       Mapped[dict | None]    = mapped_column(JSONB, nullable=True)
    status:                    Mapped[str]            = mapped_column(String(50), nullable=False, default="completed")
    failure_reason:            Mapped[str | None]     = mapped_column(Text, nullable=True)
    created_at:                Mapped[datetime]       = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
```

### `apps/control-plane/src/platform/workflows/models.py`

#### Extend `WorkflowVersion` model
```python
# Add to WorkflowVersion model:
checkpoint_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # NEW
# null → use platform default ("before_tool_invocations")
```

---

## Checkpoint Policy JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema",
  "oneOf": [
    { "properties": { "type": { "const": "before_tool_invocations" } }, "required": ["type"] },
    { "properties": { "type": { "const": "before_every_step" } }, "required": ["type"] },
    { "properties": {
        "type": { "const": "named_steps" },
        "step_ids": { "type": "array", "items": { "type": "string" }, "minItems": 1 }
      }, "required": ["type", "step_ids"]
    },
    { "properties": { "type": { "const": "disabled" } }, "required": ["type"] }
  ]
}
```

---

## Reprioritization Trigger Condition Config Schema (SLA Approach)

```json
{
  "type": "sla_approach",
  "threshold_fraction": 0.15,     // fire when remaining SLA < 15% of total window
  "action": "promote_to_front"
}
```

---

## Service Interfaces

### `execution/reprioritization.py` — `ReprioritizationService`

```python
class ReprioritizationService:
    async def create_trigger(data: ReprioritizationTriggerCreate, *, created_by: UUID) -> ReprioritizationTrigger
    async def list_triggers(workspace_id: UUID | None) -> list[ReprioritizationTrigger]
    async def get_trigger(trigger_id: UUID, workspace_id: UUID) -> ReprioritizationTrigger
    async def update_trigger(trigger_id: UUID, data: ReprioritizationTriggerUpdate, workspace_id: UUID) -> ReprioritizationTrigger
    async def delete_trigger(trigger_id: UUID, workspace_id: UUID) -> None
    async def evaluate_for_dispatch_cycle(
        executions: list[Execution],
        workspace_id: UUID,
        cycle_budget_ms: int,
    ) -> ReprioritizationResult
    # Returns (reordered_execution_ids, trigger_firings)
```

### `execution/checkpoint_service.py` — `CheckpointService`

```python
class CheckpointService:
    async def should_capture(execution_id: UUID, step: WorkflowIRStep, policy: dict) -> bool
    async def capture(
        execution_id: UUID,
        step_id: str,
        state: ExecutionState,
        policy_snapshot: dict,
    ) -> ExecutionCheckpoint
    async def list_checkpoints(
        execution_id: UUID,
        include_superseded: bool = False,
    ) -> list[ExecutionCheckpoint]
    async def get_checkpoint(execution_id: UUID, checkpoint_number: int) -> ExecutionCheckpoint
    async def rollback(
        execution_id: UUID,
        checkpoint_number: int,
        initiated_by: UUID,
    ) -> ExecutionRollbackAction
    async def gc_expired(retention_days: int) -> int  # returns count deleted
```

---

## State Transitions

### `ExecutionStatus` state machine (with new states)

```
queued → running → waiting_for_approval → running
running → completed | failed | canceled | compensating
running → paused  (manual operator pause — rollback eligible)
failed → paused   (automatic pause on terminal failures — rollback eligible)
paused → rolled_back  (after successful rollback)
paused → rollback_failed  (after failed rollback — quarantine)
rolled_back → running  (after operator resumes)
```

Rollback-eligible states: `paused`, `waiting_for_approval` (blocked on human), `failed` (terminal, not compensating)

---

## Relationships Diagram

```
workflow_versions
    └── checkpoint_policy JSONB (null = default)

executions
    ├── checkpoint_policy_snapshot JSONB  (copy at start)
    ├── status: ExecutionStatus (+ paused | rolled_back | rollback_failed)
    └──[1:N] execution_checkpoints
              ├── checkpoint_number INTEGER (monotonic per execution)
              ├── superseded BOOLEAN
              ├── current_context JSONB
              ├── accumulated_costs JSONB
              └── policy_snapshot JSONB
    └──[1:N] execution_rollback_actions
              └── target_checkpoint_number INTEGER

reprioritization_triggers (workspace-scoped or global)
    ├── trigger_type: 'sla_approach'
    ├── condition_config JSONB
    └── action: 'promote_to_front' | 'demote'
```
