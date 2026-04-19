# Implementation Plan: Dynamic Re-Prioritization and Checkpoint/Rollback

**Branch**: `056-ibor-integration-and` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/063-reprioritization-and-checkpoints/spec.md`

## Summary

Extend the execution engine with two capabilities: (1) configurable re-prioritization triggers that the scheduler evaluates on each dispatch cycle and uses to reorder the pending execution queue, and (2) policy-driven execution checkpoints that snapshot runtime state before configurable dispatch boundaries, combined with an operator-initiated rollback API that restores a prior checkpoint. Both capabilities are additive to the existing `execution/` bounded context — the scheduler, service, models, events, schemas, and router are extended rather than replaced.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, SQLAlchemy 2.x async, Pydantic v2, aiokafka 0.11+, APScheduler 3.x (GC job)  
**Storage**: PostgreSQL 16 (primary), Redis (existing dispatch lease coordination unchanged)  
**Testing**: pytest + pytest-asyncio 8.x  
**Target Platform**: Linux (Kubernetes control-plane pod)  
**Project Type**: Brownfield extension of Python modular monolith  
**Performance Goals**: Checkpoint capture < 500 ms p95 (SC-005); rollback < 3 s p95 (SC-006); checkpoint list query < 1 s p95 for ≤ 100 checkpoints (SC-013)  
**Constraints**: Never mutate execution journal (Principle V); existing executions must continue without error (FR-029); additive enum values only (Brownfield Rule 6)  
**Scale/Scope**: Per-execution checkpoints; per-workspace trigger configs; dispatch cycle adds trigger evaluation pass

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Never rewrite existing code | ✅ PASS | All existing files extended; no file replaced wholesale |
| Every change is an Alembic migration | ✅ PASS | Migration 050 covers all DDL changes |
| Preserve all existing tests | ✅ PASS | New test files only; existing execution tests unchanged |
| Use existing patterns | ✅ PASS | Service layer, Pydantic schemas, FastAPI router, SQLAlchemy mixins, EventEnvelope |
| Reference existing files | ✅ PASS | All modified files cited with exact paths |
| Additive enum values | ✅ PASS | `ExecutionStatus` gets `paused/rolled_back/rollback_failed`; `ExecutionEventType` gets `rolled_back` via `ADD VALUE IF NOT EXISTS` |
| Backward-compatible APIs | ✅ PASS | `checkpoint_policy_snapshot` nullable; `checkpoint_policy` on workflow_version nullable; new endpoints are additive |
| Principle I (modular monolith) | ✅ PASS | All new code within `execution/` bounded context; `workflows/` extended for policy storage only |
| Principle III (dedicated data stores) | ✅ PASS | PostgreSQL for checkpoint records; no vectors/graph/OLAP usage |
| Principle IV (no cross-boundary DB access) | ✅ PASS | `execution/` reads workflow policy via internal service call, not direct table join |
| Principle V (append-only execution journal) | ✅ PASS | Rollback appends `rolled_back` event; does not mutate or delete existing journal entries |
| Principle XI (secrets never in LLM context) | ✅ PASS | Checkpoint captures sanitized execution state; secrets are not in the context window at checkpoint time |
| Critical Reminder 2 (never mutate journal) | ✅ PASS | Rollback creates new records; journal entries are immutable |

**Re-check post-design**: All gates still pass after Phase 1 design. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/063-reprioritization-and-checkpoints/
├── plan.md              ← this file
├── research.md          ← Phase 0 output (generated)
├── data-model.md        ← Phase 1 output (generated)
├── quickstart.md        ← Phase 1 output (generated)
├── contracts/
│   └── rest-api.md      ← Phase 1 output (generated)
└── tasks.md             ← Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code Changes

```text
apps/control-plane/
├── migrations/versions/
│   └── 050_reprioritization_and_checkpoints.py   [NEW]
├── src/platform/
│   ├── execution/
│   │   ├── models.py          [MODIFY] — extend ExecutionStatus, ExecutionEventType,
│   │   │                                  ExecutionCheckpoint, Execution models;
│   │   │                                  add ReprioritizationTrigger,
│   │   │                                  ExecutionRollbackAction models
│   │   ├── schemas.py         [MODIFY] — add checkpoint, trigger, rollback schemas
│   │   ├── events.py          [MODIFY] — add execution_rolled_back event type + publisher;
│   │   │                                  extend ExecutionReprioritizedEvent payload
│   │   ├── scheduler.py       [MODIFY] — integrate ReprioritizationService into tick();
│   │   │                                  add policy-aware checkpoint capture in dispatch path
│   │   ├── service.py         [MODIFY] — add rollback_execution(); snapshot policy on create
│   │   ├── router.py          [MODIFY] — add checkpoints + rollback + trigger endpoints
│   │   ├── exceptions.py      [MODIFY] — add CheckpointSizeLimitExceeded,
│   │   │                                  RollbackNotEligibleError,
│   │   │                                  CheckpointRetentionExpiredError,
│   │   │                                  RollbackFailedError
│   │   ├── reprioritization.py  [NEW]  — ReprioritizationService (trigger CRUD + evaluation)
│   │   └── checkpoint_service.py [NEW] — CheckpointService (capture, list, rollback, GC)
│   └── workflows/
│       ├── models.py          [MODIFY] — add checkpoint_policy JSONB to WorkflowVersion
│       └── schemas.py         [MODIFY] — add checkpoint_policy field to version create/update
│
└── tests/
    ├── unit/execution/
    │   ├── test_reprioritization.py   [NEW]
    │   └── test_checkpoint_service.py [NEW]
    └── integration/execution/
        ├── test_reprioritization_integration.py  [NEW]
        └── test_checkpoint_integration.py         [NEW]
```

## Implementation Tasks

### T1: Alembic Migration 050

**File**: `apps/control-plane/migrations/versions/050_reprioritization_and_checkpoints.py`

- ALTER `execution_checkpoints`: add `checkpoint_number INTEGER`, `current_context JSONB`, `accumulated_costs JSONB`, `superseded BOOLEAN NOT NULL DEFAULT FALSE`, `policy_snapshot JSONB`
- Backfill `checkpoint_number` using `ROW_NUMBER() OVER (PARTITION BY execution_id ORDER BY created_at)`
- Add `NOT NULL` constraint and `UNIQUE(execution_id, checkpoint_number)` after backfill
- ALTER `executions`: add `checkpoint_policy_snapshot JSONB`
- ALTER `workflow_versions`: add `checkpoint_policy JSONB`
- CREATE `reprioritization_triggers` table
- CREATE `execution_rollback_actions` table
- `ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS` for `paused`, `rolled_back`, `rollback_failed`
- `ALTER TYPE executioneventtype ADD VALUE IF NOT EXISTS 'rolled_back'`

---

### T2: Model Extensions (`execution/models.py`, `workflows/models.py`)

**Files**: 
- `apps/control-plane/src/platform/execution/models.py`
- `apps/control-plane/src/platform/workflows/models.py`

- Add `paused`, `rolled_back`, `rollback_failed` to `ExecutionStatus` enum class
- Add `rolled_back` to `ExecutionEventType` enum class
- Extend `ExecutionCheckpoint`: add `checkpoint_number`, `current_context`, `accumulated_costs`, `superseded`, `policy_snapshot` mapped columns + `UniqueConstraint` + index
- Extend `Execution`: add `checkpoint_policy_snapshot` mapped column
- Add `ReprioritizationTrigger` SQLAlchemy model
- Add `ExecutionRollbackAction` SQLAlchemy model
- Extend `WorkflowVersion` (in `workflows/models.py`): add `checkpoint_policy` mapped column

---

### T3: Schema Additions (`execution/schemas.py`, `workflows/schemas.py`)

**Files**: 
- `apps/control-plane/src/platform/execution/schemas.py`
- `apps/control-plane/src/platform/workflows/schemas.py`

New schemas for `execution/schemas.py`:
- `CheckpointPolicySchema` — tagged union for policy types
- `CheckpointSummaryResponse` — list-level checkpoint view (number, created_at, step counts, costs summary)
- `CheckpointDetailResponse` — full checkpoint with all snapshot fields
- `ReprioritizationTriggerCreate`, `ReprioritizationTriggerUpdate`, `ReprioritizationTriggerResponse`
- `RollbackRequest` (optional reason field), `RollbackResponse`

Extend `workflows/schemas.py`:
- Add optional `checkpoint_policy: CheckpointPolicySchema | None` to `WorkflowVersionCreate` and `WorkflowVersionUpdate`

---

### T4: Event Extensions (`execution/events.py`)

**File**: `apps/control-plane/src/platform/execution/events.py`

- Extend `ExecutionReprioritizedEvent`: add `trigger_id: UUID | None`, `trigger_name: str | None`, `new_queue_order: list[str]`
- Add `ExecutionRolledBackEvent` Pydantic schema with fields: `execution_id`, `target_checkpoint_number`, `target_checkpoint_id`, `initiated_by`, `cost_delta_reversed`, `rollback_action_id`
- Add `publish_execution_rolled_back()` function following the existing `publish_*` pattern

---

### T5: New `ReprioritizationService` (`execution/reprioritization.py`)

**File**: `apps/control-plane/src/platform/execution/reprioritization.py`

```python
class ReprioritizationService:
    def __init__(self, db: AsyncSession, settings: PlatformSettings): ...

    # Trigger CRUD
    async def create_trigger(data, *, created_by) -> ReprioritizationTrigger
    async def list_triggers(workspace_id, include_global=True) -> list[ReprioritizationTrigger]
    async def get_trigger(trigger_id, workspace_id) -> ReprioritizationTrigger
    async def update_trigger(trigger_id, data, workspace_id) -> ReprioritizationTrigger
    async def delete_trigger(trigger_id, workspace_id) -> None

    # Evaluation (called from scheduler tick)
    async def evaluate_for_dispatch_cycle(
        executions: list[Execution],
        workspace_id: UUID,
        cycle_budget_ms: int,
    ) -> ReprioritizationResult
    # Returns: reordered execution list + list of trigger-firing audit records
    # Time-bounded: if evaluation exceeds cycle_budget_ms, returns original order + warning

    # Validation
    def _validate_condition_config(trigger_type, condition_config) -> None
    def _evaluate_sla_approach(execution, config) -> bool
```

---

### T6: New `CheckpointService` (`execution/checkpoint_service.py`)

**File**: `apps/control-plane/src/platform/execution/checkpoint_service.py`

```python
class CheckpointService:
    def __init__(self, db: AsyncSession, settings: PlatformSettings, s3_client): ...

    async def should_capture(step: WorkflowIRStep, policy: dict) -> bool
    # Returns True if policy requires capture before this step type

    async def capture(
        execution_id: UUID,
        step_id: str,
        state: ExecutionState,
        policy_snapshot: dict,
    ) -> ExecutionCheckpoint
    # Serializes state, checks size limit (default 10 MB),
    # assigns checkpoint_number (SELECT MAX + 1 for execution),
    # persists record, returns checkpoint

    async def list_checkpoints(
        execution_id: UUID,
        include_superseded: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ExecutionCheckpoint], int]

    async def get_checkpoint(
        execution_id: UUID,
        checkpoint_number: int,
    ) -> ExecutionCheckpoint

    async def rollback(
        execution_id: UUID,
        checkpoint_number: int,
        initiated_by: UUID,
        session: AsyncSession,
    ) -> ExecutionRollbackAction
    # Validates eligibility, restores state in DB transaction,
    # marks superseded checkpoints, records audit, emits event

    async def gc_expired(retention_days: int) -> int
    # Deletes checkpoints older than retention window that are not
    # referenced by pending rollback actions
```

---

### T7: Scheduler Extension (`execution/scheduler.py`)

**File**: `apps/control-plane/src/platform/execution/scheduler.py`

Modifications to `SchedulerService`:
1. Inject `ReprioritizationService` and `CheckpointService` via `__init__`
2. In `tick()`: after fetching queued executions, call `reprioritization_service.evaluate_for_dispatch_cycle()` to reorder before dispatch
3. In `_process_execution()` just before `_dispatch_to_runtime()`: call `checkpoint_service.should_capture(step, policy)` and if True, call `checkpoint_service.capture()` — pause execution if capture fails (FR-013)
4. Read `execution.checkpoint_policy_snapshot` to determine policy; fall back to default `{"type": "before_tool_invocations"}` if null
5. Existing `_maybe_checkpoint()` (every-100-events compaction checkpoint) remains unchanged

---

### T8: Service Extension (`execution/service.py`)

**File**: `apps/control-plane/src/platform/execution/service.py`

Modifications to `ExecutionService`:
1. In `create_execution()`: read `workflow_version.checkpoint_policy`; snapshot it to `execution.checkpoint_policy_snapshot`
2. Add `rollback_execution(execution_id, checkpoint_number, initiated_by)`:
   - Validates execution is in rollback-eligible state (`paused`, `waiting_for_approval`, `failed`)
   - Validates checkpoint belongs to execution
   - Validates caller has `execution.rollback` permission
   - Delegates to `CheckpointService.rollback()`
   - Appends `rolled_back` journal event
3. Add `pause_execution(execution_id)` for operator-initiated pause (rollback pre-condition)

---

### T9: Router Extension (`execution/router.py`)

**File**: `apps/control-plane/src/platform/execution/router.py`

New endpoints:
```python
# Checkpoint endpoints
GET  /api/v1/executions/{execution_id}/checkpoints
GET  /api/v1/executions/{execution_id}/checkpoints/{checkpoint_number}

# Rollback endpoint
POST /api/v1/executions/{execution_id}/rollback/{checkpoint_number}

# Reprioritization trigger endpoints
POST   /api/v1/reprioritization-triggers
GET    /api/v1/reprioritization-triggers
GET    /api/v1/reprioritization-triggers/{trigger_id}
PATCH  /api/v1/reprioritization-triggers/{trigger_id}
DELETE /api/v1/reprioritization-triggers/{trigger_id}
```

---

### T10: Exception Additions (`execution/exceptions.py`)

**File**: `apps/control-plane/src/platform/execution/exceptions.py`

```python
class CheckpointSizeLimitExceeded(PlatformError): ...      # 422
class RollbackNotEligibleError(PlatformError): ...          # 409
class CheckpointRetentionExpiredError(PlatformError): ...   # 410
class RollbackFailedError(PlatformError): ...               # 500 (quarantine)
class CheckpointNotFoundError(NotFoundError): ...           # 404
class ReprioritizationTriggerNotFoundError(NotFoundError): ... # 404
```

---

### T11: GC APScheduler Job

**File**: `apps/control-plane/src/platform/main.py` (or scheduler startup hook)

Add APScheduler job that calls `checkpoint_service.gc_expired(retention_days=settings.checkpoint_retention_days)` on a configurable interval (default daily). Follow the existing APScheduler `AsyncIOScheduler` pattern in `app.state`.

Add `checkpoint_retention_days: int = 30` and `checkpoint_max_size_bytes: int = 10_485_760` to `PlatformSettings` in `apps/control-plane/src/platform/common/config.py`.

---

### T12: Unit Tests

**Files**:
- `apps/control-plane/tests/unit/execution/test_reprioritization.py`
- `apps/control-plane/tests/unit/execution/test_checkpoint_service.py`

Cover:
- `ReprioritizationService.evaluate_for_dispatch_cycle()` with SLA threshold at/above/below threshold
- Idempotency: same trigger + same queue position → no event
- Time budget exceeded → returns original order
- `CheckpointService.should_capture()` for each policy type (tool step, compute step, named step, disabled)
- `CheckpointService.capture()` — size limit enforcement, checkpoint_number assignment
- `CheckpointService.rollback()` — state restoration, superseded marking, quarantine on failure
- `_validate_condition_config()` edge cases (threshold out of range)
- Rollback eligibility checks (active execution → 409)

---

### T13: Integration Tests

**Files**:
- `apps/control-plane/tests/integration/execution/test_reprioritization_integration.py`
- `apps/control-plane/tests/integration/execution/test_checkpoint_integration.py`

Cover: scenarios S1–S25 from quickstart.md (selected representative scenarios for integration coverage — full scenario list is the acceptance criteria).

## Complexity Tracking

No violations to justify — all gates pass. No complexity tracking required.
