# Research: Dynamic Re-Prioritization and Checkpoint/Rollback

**Feature**: 063-reprioritization-and-checkpoints  
**Date**: 2026-04-19  
**Status**: Complete — all unknowns resolved

---

## Decision 1: Bounded context is `execution/`, not `workflow/`

- **Decision**: All new and modified files go in `apps/control-plane/src/platform/execution/`. The workflows bounded context (`workflows/`) owns workflow definition/version/trigger CRUD only.
- **Rationale**: The user's input plan referenced `workflow/services/scheduler.py`, `workflow/services/executor.py`, `workflow/router.py` — but the actual codebase uses the `execution/` bounded context for the scheduler, service, and router. `execution/scheduler.py` contains `SchedulerService` with the `tick()` dispatch loop. `execution/service.py` contains `ExecutionService`. `execution/router.py` has all execution endpoints.
- **Alternatives considered**: Creating a separate `checkpointing/` bounded context — rejected, unnecessary coupling for what are direct execution-engine concerns.

---

## Decision 2: `execution_checkpoints` table already exists — ALTER, not CREATE

- **Decision**: Migration 050 ALTERs the existing `execution_checkpoints` table. It does NOT create a new one.
- **Rationale**: Feature 029 (workflow execution engine, migration 012) already created `execution_checkpoints` with: `id`, `execution_id`, `last_event_sequence`, `step_results JSONB`, `completed_step_ids TEXT[]`, `pending_step_ids TEXT[]`, `active_step_ids TEXT[]`, `execution_data JSONB`, `created_at`, `updated_at`. The user's input plan DDL (`state_snapshot`, `checkpoint_number`, `current_context`, `accumulated_costs`, `pending_queue`) maps to new columns that need to be added to the existing table.
- **Column additions needed**:
  - `checkpoint_number INTEGER` — per-execution monotonic ID (backfilled from existing rows)
  - `current_context JSONB` — working context snapshot (currently folded into `execution_data`)
  - `accumulated_costs JSONB` — cost accounting snapshot
  - `superseded BOOLEAN NOT NULL DEFAULT FALSE` — set by rollback
  - `policy_snapshot JSONB` — checkpoint policy in force at capture time
- **Alternatives considered**: Creating a parallel `execution_checkpoints_v2` table — rejected; violates Brownfield Rule 1 (never replace a file/table wholesale).

---

## Decision 3: `ExecutionReprioritizedEvent` and publisher already exist — extend, don't duplicate

- **Decision**: `execution/events.py` already defines `ExecutionDomainEventType.execution_reprioritized`, `ExecutionReprioritizedEvent`, and `publish_execution_reprioritized()`. The `reprioritization.py` service calls these existing functions rather than duplicating them.
- **Rationale**: Existing event types are at `execution.reprioritized`. The new feature extends the payload (adds trigger identifier, old queue positions, new queue positions) by adding fields to the existing `ExecutionReprioritizedEvent` schema — backward compatible since new fields are optional.
- **New event needed**: `execution.rolled_back` — add `ExecutionDomainEventType.execution_rolled_back` and `publish_execution_rolled_back()` to `execution/events.py`.

---

## Decision 4: `ExecutionStatus` enum extension — add paused, rolled_back, rollback_failed

- **Decision**: Extend the existing `ExecutionStatus` PostgreSQL enum (Brownfield Rule 6 — additive). Add three values: `paused`, `rolled_back`, `rollback_failed`.
- **Rationale**: Rollback eligibility (FR-016) requires `paused` as a terminal-of-sorts state that permits rollback. `rolled_back` is the post-rollback state that allows resumption. `rollback_failed` is the quarantine state (FR-028).
- **Alembic approach**: `op.execute("ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'paused'")` etc. — Alembic executes raw DDL for enum extensions (standard pattern for PostgreSQL enums in SQLAlchemy/Alembic).
- **Alternatives considered**: Reusing `failed` for rollback-failed — rejected, `failed` does not signal the quarantine semantics; operators need a distinct status to filter on.

---

## Decision 5: `ExecutionEventType` extension — add rolled_back

- **Decision**: Add `rolled_back = "rolled_back"` to the `ExecutionEventType` enum in `execution/models.py`. This is used when writing a journal entry for the rollback operation (append-only journal, Principle V).
- **Rationale**: Every state change in an execution is recorded as an immutable journal entry. Rollback must record a `rolled_back` event that captures the target checkpoint number and actor. The existing `reprioritized` event type already exists.

---

## Decision 6: Checkpoint policy stored on `workflow_versions`, snapshotted on `executions`

- **Decision**: Add `checkpoint_policy JSONB` to `workflow_versions` table (via `workflows/models.py`). Add `checkpoint_policy_snapshot JSONB` to `executions` table. At execution start, the policy is read from the workflow version and written to `checkpoint_policy_snapshot` — satisfying FR-012 (policy not affected by mid-flight changes).
- **JSONB policy shape**:
  ```json
  {"type": "before_tool_invocations"}
  {"type": "before_every_step"}
  {"type": "named_steps", "step_ids": ["s3", "s5"]}
  {"type": "disabled"}
  ```
  Null `checkpoint_policy` on the workflow version means "use default" (FR-029 backward compatibility).
- **Alternatives considered**: A separate `checkpoint_policies` table — rejected; the policy is a property of the workflow version, not a separately addressable resource.

---

## Decision 7: New table `reprioritization_triggers` in `execution/` bounded context

- **Decision**: New table `reprioritization_triggers` in migration 050. Owned by the `execution/` bounded context. Contains configurable trigger rules (type, condition config, action, priority rank, workspace scope).
- **Rationale**: The existing `SchedulerService.handle_reprioritization_trigger()` handles ad-hoc triggers from external events (budget, fleet health). This feature adds *stored* configurable rules that the scheduler evaluates on every dispatch cycle (FR-001, FR-002, FR-005). These are distinct: existing ad-hoc triggers are pushed by external consumers; new configurable triggers are pulled and evaluated by the scheduler.
- **Trigger types in scope**: `sla_approach` only (FR-005). Other types (`budget_approach`, `priority_signal`, `dependency_ready`) are Out of Scope in this feature.
- **Scope**: Workspace-scoped (`workspace_id` nullable for global-scope triggers).

---

## Decision 8: New table `execution_rollback_actions` for rollback audit

- **Decision**: New table `execution_rollback_actions` in migration 050. Records each operator rollback with: `execution_id`, `target_checkpoint_id`, `target_checkpoint_number`, `initiated_by`, `cost_delta_reversed JSONB`, `status`, `failure_reason`.
- **Rationale**: The spec requires an auditable `Rollback Action` entity (FR-019, FR-024). Rollback events also go to the execution journal and Kafka, but a queryable DB table enables compliance queries without replaying the journal.
- **Alternatives considered**: Using only the execution journal (append-only events) — insufficient because FR-024 requires `cost_delta_reversed` to be queryable for cost reports; a dedicated table makes that query cheap.

---

## Decision 9: Migration 050 — next migration after 049

- **Decision**: New migration file: `apps/control-plane/migrations/versions/050_reprioritization_and_checkpoints.py`
- **Rationale**: The last migration is `049_agent_contracts_and_certification.py`. Sequential numbering convention.
- **Migration scope**:
  1. ALTER `execution_checkpoints` — add `checkpoint_number`, `current_context`, `accumulated_costs`, `superseded`, `policy_snapshot`
  2. ALTER `executions` — add `checkpoint_policy_snapshot`
  3. ALTER `workflow_versions` — add `checkpoint_policy`
  4. CREATE `reprioritization_triggers`
  5. CREATE `execution_rollback_actions`
  6. ALTER TYPE `executionstatus` — add `paused`, `rolled_back`, `rollback_failed`
  7. ALTER TYPE `executioneventtype` — add `rolled_back`
  8. Backfill `checkpoint_number` on existing `execution_checkpoints` rows (per-execution row_number)

---

## Decision 10: Checkpoint capture hook in scheduler dispatch loop

- **Decision**: Policy-aware checkpoint capture is inserted in `SchedulerService._process_execution()` just before `_dispatch_to_runtime()` is called for each step. The existing `_maybe_checkpoint()` (every 100 events) remains unchanged for its own purpose (journal compaction).
- **Rationale**: The spec's "before tool invocation" policy requires capture immediately before the step is dispatched to the runtime controller. The dispatch path goes through `_process_execution()` → `_dispatch_to_runtime()`. Inserting the policy check here (checking the policy type, checking if the step is a tool invocation) is the minimal invasive change.
- **Tool invocation detection**: The existing `WorkflowIR` (intermediate representation) step metadata carries a step type. Tool-invocation steps can be detected by `step.type == "tool"` or equivalent field in the compiled IR.

---

## Decision 11: `CheckpointService` size enforcement and S3 offload

- **Decision**: `CheckpointService.capture()` checks the JSON-serialized size of the snapshot before persistence. If size exceeds the configurable limit (default 10 MB from `PlatformSettings`), the capture fails with a `CheckpointSizeLimitExceeded` error (FR-022). S3 offload of large components is deferred (Out of Scope in this iteration per the spec's explicit out-of-scope note).
- **Rationale**: The spec says "exceeding it fails the checkpoint capture with a clear error, optionally offloading large components to object storage with pointer references" — the "optionally" marks S3 offload as future work.

---

## Decision 12: `reprioritization.py` owns trigger CRUD + evaluation; `checkpoint_service.py` owns checkpoint lifecycle

- **Decision**: New file `execution/reprioritization.py` contains `ReprioritizationService` (trigger CRUD, trigger evaluation loop, queue reordering). New file `execution/checkpoint_service.py` contains `CheckpointService` (capture, list, get, rollback, GC).
- **Rationale**: Separation of concerns matches the spec's two main capability clusters. Both services are injected into the scheduler and execution service via FastAPI dependency injection, following the existing pattern.
- **User's plan correction**: User's plan said `workflow/models/checkpoint.py` for a new model file — the checkpoint model already exists in `execution/models.py`; it only needs extension, not a new file.
