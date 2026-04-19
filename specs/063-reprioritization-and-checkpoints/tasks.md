# Tasks: Dynamic Re-Prioritization and Checkpoint/Rollback

**Input**: Design documents from `specs/063-reprioritization-and-checkpoints/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/rest-api.md ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in phase)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Setup

No setup needed — brownfield extension of an existing control-plane application. Repository, tooling, and dependencies are pre-configured.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All DDL changes, base enum extensions, events, and shared schema types that EVERY user story depends on. Nothing in Phase 3+ can start until this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 Create Alembic migration 050 in `apps/control-plane/migrations/versions/050_reprioritization_and_checkpoints.py` — ALTER `execution_checkpoints` (add `checkpoint_number`, `current_context`, `accumulated_costs`, `superseded`, `policy_snapshot`); ALTER `executions` (add `checkpoint_policy_snapshot`); ALTER `workflow_versions` (add `checkpoint_policy`); CREATE `reprioritization_triggers`; CREATE `execution_rollback_actions`; ALTER TYPE `executionstatus` ADD VALUE `paused`/`rolled_back`/`rollback_failed`; ALTER TYPE `executioneventtype` ADD VALUE `rolled_back`; backfill `checkpoint_number` via ROW_NUMBER(); add UNIQUE constraint + indexes; follow pattern in `048_governance_pipeline.py`
- [X] T002 [P] Extend `ExecutionStatus` enum (add `paused`, `rolled_back`, `rollback_failed`) and `ExecutionEventType` enum (add `rolled_back`) in `apps/control-plane/src/platform/execution/models.py`
- [X] T003 [P] Add exception classes `CheckpointSizeLimitExceeded`, `RollbackNotEligibleError` (409), `CheckpointRetentionExpiredError` (410), `RollbackFailedError` (500), `CheckpointNotFoundError` (404), `ReprioritizationTriggerNotFoundError` (404) to `apps/control-plane/src/platform/execution/exceptions.py`
- [X] T004 [P] Add `ExecutionRolledBackEvent` Pydantic schema and `publish_execution_rolled_back()` function; extend `ExecutionReprioritizedEvent` with `trigger_id`, `trigger_name`, `new_queue_order` fields (all optional, backward-compatible) in `apps/control-plane/src/platform/execution/events.py`
- [X] T005 [P] Add `CheckpointPolicySchema` tagged-union Pydantic model (types: `before_tool_invocations`, `before_every_step`, `named_steps` with `step_ids`, `disabled`) and `DEFAULT_CHECKPOINT_POLICY` constant to `apps/control-plane/src/platform/execution/schemas.py`

**Checkpoint**: Foundation complete — enum extensions applied, migration file ready, shared types available. User story phases can now start.

---

## Phase 3: User Story 1 — Scheduler Re-Prioritizes Queue on Trigger (Priority: P1) 🎯 MVP

**Goal**: Platform operators define SLA-approach triggers; the scheduler evaluates them on each dispatch cycle and reorders the pending execution queue; a `execution.reprioritized` event is emitted with trigger identity and new queue positions.

**Independent Test** (Scenario S1–S3 in quickstart.md): Configure SLA-approach trigger at 15%. Enqueue three executions with different SLA remaining fractions. Verify the scheduler promotes the sub-15% execution to position 1 within one dispatch cycle. Verify `execution.reprioritized` event on Kafka with `trigger_id` populated. Disable the trigger; verify no further reprioritization events on next tick.

- [X] T006 [P] [US1] Add `ReprioritizationTrigger` SQLAlchemy model (fields: `id`, `workspace_id`, `name`, `trigger_type`, `condition_config JSONB`, `action`, `priority_rank`, `enabled`, `created_by`, `created_at`, `updated_at`) to `apps/control-plane/src/platform/execution/models.py`
- [X] T007 [P] [US1] Add `ReprioritizationTriggerCreate`, `ReprioritizationTriggerUpdate`, `ReprioritizationTriggerResponse` Pydantic schemas to `apps/control-plane/src/platform/execution/schemas.py`
- [X] T008 [US1] Create `ReprioritizationService` class in `apps/control-plane/src/platform/execution/reprioritization.py` with methods: `create_trigger()`, `list_triggers(workspace_id, include_global)`, `get_trigger(trigger_id, workspace_id)`, `update_trigger()`, `delete_trigger()`, `evaluate_for_dispatch_cycle(executions, workspace_id, cycle_budget_ms)` (time-bounded, returns reordered list + audit records), `_validate_condition_config()`, `_evaluate_sla_approach(execution, config)`; validate `threshold_fraction` in `[0.0, 1.0]`; only `sla_approach` trigger type supported in this release
- [X] T009 [US1] Integrate `ReprioritizationService` into `SchedulerService.tick()` in `apps/control-plane/src/platform/execution/scheduler.py`: after fetching queued executions and before dispatching, call `evaluate_for_dispatch_cycle()` to reorder; emit `execution.reprioritized` event (via existing `publish_execution_reprioritized()`) only when queue position actually changes (idempotent — FR-004); inject service via `__init__`; preserve existing SLA-threshold logic for backward compatibility
- [X] T010 [US1] Add 5 reprioritization trigger CRUD endpoints to `apps/control-plane/src/platform/execution/router.py`: `POST /api/v1/reprioritization-triggers`, `GET /api/v1/reprioritization-triggers`, `GET /api/v1/reprioritization-triggers/{trigger_id}`, `PATCH /api/v1/reprioritization-triggers/{trigger_id}`, `DELETE /api/v1/reprioritization-triggers/{trigger_id}`; delegate to `ReprioritizationService`; require admin role for create/update/delete; workspace-scoped

**Checkpoint**: US1 complete — configurable SLA-approach triggers created, evaluated on dispatch cycle, reprioritization event emitted with trigger identity and new queue order.

---

## Phase 4: User Story 2 — Checkpoint Before Tool Invocation (Priority: P1) 🎯 MVP

**Goal**: Every execution running with the default checkpoint policy captures a checkpoint before each external tool invocation. The checkpoint records complete runtime state (completed steps, context, costs, pending queue). Capture failure pauses the execution rather than dispatching the tool call unchecked.

**Independent Test** (Scenarios S4–S7 in quickstart.md): Submit execution of a 5-step workflow where steps 3 and 4 are tool-invocations. Verify exactly 2 checkpoints created with `checkpoint_number 1` and `2`, all required fields non-null, tool calls dispatched only after checkpoint persisted. Submit compute-only workflow; verify 0 checkpoints. Inject storage fault; verify execution pauses with recoverable error and tool call does NOT proceed.

- [X] T011 [P] [US2] Extend `ExecutionCheckpoint` SQLAlchemy model with new mapped columns (`checkpoint_number`, `current_context`, `accumulated_costs`, `superseded`, `policy_snapshot`), `UniqueConstraint("execution_id", "checkpoint_number")`, and index on `(execution_id, superseded)` in `apps/control-plane/src/platform/execution/models.py`; add `checkpoint_policy_snapshot` mapped column to `Execution` model
- [X] T012 [P] [US2] Add `CheckpointSummaryResponse` (list view: `id`, `checkpoint_number`, `created_at`, `completed_step_count`, `accumulated_costs`, `superseded`, `policy_snapshot`) and `CheckpointDetailResponse` (full view adding all snapshot fields) Pydantic schemas to `apps/control-plane/src/platform/execution/schemas.py`
- [X] T013 [US2] Create `CheckpointService` class in `apps/control-plane/src/platform/execution/checkpoint_service.py` with methods: `should_capture(step, policy_dict)` (returns True based on policy type and step type); `capture(execution_id, step_id, state, policy_snapshot)` (serializes state, checks 10 MB size limit via `settings.checkpoint_max_size_bytes`, assigns `checkpoint_number` via `SELECT MAX(checkpoint_number)+1 FOR UPDATE`, persists record, returns `ExecutionCheckpoint`); `list_checkpoints(execution_id, include_superseded, page, page_size)`; `get_checkpoint(execution_id, checkpoint_number)`; raise `CheckpointSizeLimitExceeded` on oversized captures
- [X] T014 [US2] Integrate checkpoint capture into `SchedulerService._process_execution()` in `apps/control-plane/src/platform/execution/scheduler.py`: before calling `_dispatch_to_runtime()`, call `checkpoint_service.should_capture(step, policy)` using `execution.checkpoint_policy_snapshot` (null → default `before_tool_invocations`); if True, call `checkpoint_service.capture()`; if capture raises any exception, pause execution with recoverable error journal entry (do NOT proceed with dispatch); inject `CheckpointService` via `__init__`
- [X] T015 [US2] Add `GET /api/v1/executions/{execution_id}/checkpoints` and `GET /api/v1/executions/{execution_id}/checkpoints/{checkpoint_number}` endpoints to `apps/control-plane/src/platform/execution/router.py`; return `CheckpointSummaryResponse` list (default excludes superseded) and `CheckpointDetailResponse` respectively; return empty list (not 404) for execution with no checkpoints
- [X] T016 [US2] Snapshot default checkpoint policy at execution start in `ExecutionService.create_execution()` in `apps/control-plane/src/platform/execution/service.py`: set `execution.checkpoint_policy_snapshot = {"type": "before_tool_invocations"}` when workflow version has no explicit policy (null); existing executions with null snapshot are treated as default (FR-029 backward compatibility)

**Checkpoint**: US2 complete — checkpoints captured before every tool invocation by default; storage fault causes pause not unchecked dispatch; list and detail endpoints return checkpoint data.

---

## Phase 5: User Story 3 — Operator Rollback to Prior Checkpoint (Priority: P2)

**Goal**: An authorized operator can roll back a paused/failed/waiting execution to a specific prior checkpoint, restoring completed steps, context, costs, and pending queue to the checkpoint state. Superseded later checkpoints are retained (not deleted). Rollback emits `execution.rolled_back` event. Failed mid-operation rollback transitions to `rollback_failed` quarantine — no partial restore.

**Independent Test** (Scenarios S8–S12 in quickstart.md): Run execution through 3 checkpoints. Rollback to checkpoint 2. Verify state exactly matches checkpoint 2. Verify checkpoint 3 superseded (retained, not deleted). Verify `execution.rolled_back` Kafka event. Verify active execution → 409. Verify caller without `execution.rollback` → 403. Resume rolled-back execution → dispatches from restored pending queue.

- [X] T017 [P] [US3] Add `ExecutionRollbackAction` SQLAlchemy model (fields: `id`, `execution_id`, `target_checkpoint_id`, `target_checkpoint_number`, `initiated_by`, `cost_delta_reversed JSONB`, `status`, `failure_reason`, `created_at`) with index on `execution_id` in `apps/control-plane/src/platform/execution/models.py`
- [X] T018 [P] [US3] Add `RollbackRequest` (optional `reason: str`) and `RollbackResponse` (`rollback_action_id`, `execution_id`, `target_checkpoint_number`, `initiated_by`, `cost_delta_reversed`, `status`, `execution_status`, `warning`) Pydantic schemas to `apps/control-plane/src/platform/execution/schemas.py`
- [X] T019 [US3] Add `CheckpointService.rollback(execution_id, checkpoint_number, initiated_by, session)` to `apps/control-plane/src/platform/execution/checkpoint_service.py`: validate execution is in rollback-eligible state (`paused`, `waiting_for_approval`, `failed`) else raise `RollbackNotEligibleError` (409); validate checkpoint belongs to execution and exists else raise `CheckpointNotFoundError`; validate checkpoint not retention-expired else raise `CheckpointRetentionExpiredError` (410); in a single DB transaction: restore `execution.completed_step_ids/pending_step_ids/active_step_ids/step_results` from checkpoint, update execution status to `rolled_back`, mark all checkpoints with `checkpoint_number > target` as `superseded=True`, create `ExecutionRollbackAction` record; on any mid-restore exception: transition execution to `rollback_failed` and re-raise `RollbackFailedError` (quarantine — do NOT leave partial state); call `publish_execution_rolled_back()`
- [X] T020 [US3] Add `ExecutionService.rollback_execution(execution_id, checkpoint_number, initiated_by)` to `apps/control-plane/src/platform/execution/service.py`: check caller has `execution.rollback` RBAC permission (raise `AuthorizationError` 403 if not); append `rolled_back` journal event; delegate state restoration to `CheckpointService.rollback()`; add `pause_execution(execution_id)` method to transition `running`/`queued` → `paused`
- [X] T021 [US3] Add `POST /api/v1/executions/{execution_id}/rollback/{checkpoint_number}` endpoint to `apps/control-plane/src/platform/execution/router.py`; require `execution.rollback` permission; delegate to `ExecutionService.rollback_execution()`; map `RollbackNotEligibleError` → 409, `CheckpointNotFoundError` → 404, `CheckpointRetentionExpiredError` → 410, `RollbackFailedError` → 500; include `warning` field in 200 response about external side effects

**Checkpoint**: US3 complete — rollback restores state, supersedes later checkpoints, emits event; ineligible executions rejected 409; authorization enforced; failed rollback quarantines execution.

---

## Phase 6: User Story 4 — Admin Configures Custom Checkpoint Policies (Priority: P2)

**Goal**: Workflow admins configure a per-workflow checkpoint policy (`before_tool_invocations`, `before_every_step`, `named_steps [...]`, `disabled`) on the workflow version. The policy is validated at save time (named step IDs must exist in the compiled IR). The policy is snapshotted at execution start so mid-flight changes don't affect in-progress executions.

**Independent Test** (Scenarios S13–S17 in quickstart.md): Set policy `before_every_step` → 5-step workflow produces 5 checkpoints. Set `disabled` → 0 checkpoints even with tool calls. Set `named_steps ["step-3","step-5"]` → exactly 2 checkpoints. Set `named_steps ["nonexistent"]` → 422 at save time. Change policy mid-flight → in-progress execution uses original policy; new execution uses new policy.

- [X] T022 [P] [US4] Add `checkpoint_policy` mapped column (`JSONB, nullable=True`) to `WorkflowVersion` SQLAlchemy model in `apps/control-plane/src/platform/workflows/models.py`
- [X] T023 [P] [US4] Add optional `checkpoint_policy: CheckpointPolicySchema | None` field to `WorkflowVersionCreate` and `WorkflowVersionUpdate` Pydantic schemas in `apps/control-plane/src/platform/workflows/schemas.py`
- [X] T024 [US4] Add policy validation to `WorkflowService` version create/update in `apps/control-plane/src/platform/workflows/service.py`: when `checkpoint_policy.type == "named_steps"`, validate all `step_ids` exist in the compiled IR of the version; raise `ValidationError` 422 with list of unknown step IDs if any are missing; persist validated policy to `workflow_versions.checkpoint_policy`
- [X] T025 [US4] Snapshot per-workflow policy at execution start in `ExecutionService.create_execution()` in `apps/control-plane/src/platform/execution/service.py`: read `workflow_version.checkpoint_policy`; if non-null, write to `execution.checkpoint_policy_snapshot`; if null, write `{"type": "before_tool_invocations"}` (default); existing null snapshots on running executions continue to use default (FR-029)

**Checkpoint**: US4 complete — per-workflow policies persisted and validated at save; snapshotted at execution start; mid-flight policy changes don't affect in-progress executions.

---

## Phase 7: User Story 5 — Operator Lists Checkpoints for Audit (Priority: P3)

**Goal**: A compliance or support operator can query an execution's complete checkpoint history in checkpoint-number order with summary metadata (timestamps, step counts, cost summaries). The query returns within 1 second at p95 for executions with up to 100 checkpoints.

**Independent Test** (Scenarios S18, S9 in quickstart.md): Run execution producing 5 checkpoints. Query the list. Verify 5 entries in ascending order, each with `checkpoint_number`, `created_at`, `completed_step_count`, `accumulated_costs`. Query with `include_superseded=true` (post-rollback) → superseded checkpoints appear with `superseded=true`. Response time < 1 second.

- [X] T026 [US5] Add `CheckpointService.gc_expired(retention_days)` method to `apps/control-plane/src/platform/execution/checkpoint_service.py`: delete `execution_checkpoints` records where `created_at < now() - retention_days` AND NOT referenced by any pending `execution_rollback_actions` (status != 'failed'); return count of deleted rows; log count at INFO level
- [X] T027 [US5] Add `checkpoint_retention_days: int = 30` and `checkpoint_max_size_bytes: int = 10_485_760` settings to `PlatformSettings` in `apps/control-plane/src/platform/common/config.py`; register APScheduler daily GC job calling `checkpoint_service.gc_expired(settings.checkpoint_retention_days)` in app lifespan startup in `apps/control-plane/src/platform/main.py` using existing `AsyncIOScheduler` pattern from `app.state`

**Checkpoint**: US5 complete — full checkpoint listing with summary fields; GC job retires expired records; retention window configurable.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Test coverage for new services and integration validation across all stories.

- [X] T028 [P] Write unit tests for `ReprioritizationService` in `apps/control-plane/tests/unit/execution/test_reprioritization.py`: trigger CRUD, `_validate_condition_config` edge cases (threshold out-of-range, unknown type), `evaluate_for_dispatch_cycle` with execution above/at/below SLA threshold, idempotency (same queue position → no event emitted), time-budget exceeded → original order returned
- [X] T029 [P] Write unit tests for `CheckpointService` in `apps/control-plane/tests/unit/execution/test_checkpoint_service.py`: `should_capture` for each policy type × step type combinations; `capture` with normal state, oversized state (raises `CheckpointSizeLimitExceeded`), checkpoint_number assignment (monotonic per execution); `rollback` with eligible/ineligible status, superseded marking, quarantine on storage fault; `gc_expired` count returned
- [X] T030 [P] Write integration tests for reprioritization in `apps/control-plane/tests/integration/execution/test_reprioritization_integration.py`: scenarios S1 (trigger promotes execution), S2 (idempotent no duplicate event), S3 (invalid trigger rejected), S19 (time-bounded evaluation), S20 (contradictory triggers — higher priority wins)
- [X] T031 [P] Write integration tests for checkpoints and rollback in `apps/control-plane/tests/integration/execution/test_checkpoint_integration.py`: scenarios S4 (default capture before tool), S5 (multiple checkpoints numbered), S6 (compute-only → zero checkpoints), S7 (capture failure → pause), S8 (successful rollback restores state), S9 (superseded retained), S10 (active execution → 409), S11 (no permission → 403), S12 (resume after rollback), S23 (failed rollback → quarantine), S24 (backward compat null policy)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 2 (Foundation)**: No dependencies — start immediately
- **Phase 3–7 (User Stories)**: ALL depend on Phase 2 completion (migration must run, enums must exist)
- **Phase 3 (US1) and Phase 4 (US2)**: Both P1 — can proceed in parallel after Phase 2
- **Phase 5 (US3)**: Depends on Phase 4 (US2) completing — rollback requires existing checkpoints
- **Phase 6 (US4)**: Independent of Phase 5; depends only on Phase 2 + Phase 4 (checkpoint_policy_snapshot field)
- **Phase 7 (US5)**: Independent — depends only on Phase 4 (CheckpointService exists); can be done alongside Phase 5 or 6
- **Phase 8 (Polish)**: Depends on all user story phases

### User Story Dependencies

- **US1 (P1)**: Phase 2 complete → independent start
- **US2 (P1)**: Phase 2 complete → independent start (parallel with US1)
- **US3 (P2)**: US2 complete (needs CheckpointService + ExecutionCheckpoint extensions)
- **US4 (P2)**: Phase 2 + Phase 4 T016 (checkpoint_policy_snapshot on Execution) complete
- **US5 (P3)**: US2 complete (needs CheckpointService with list/get)

### Within Each User Story

- Models before services (T006 before T008, T011 before T013, T017 before T019, T022 before T024)
- Services before endpoints (T008 before T010, T013 before T015, T019 before T021)
- Schemas in parallel with models (T007 with T006, T012 with T011, T018 with T017, T023 with T022)

### Parallel Opportunities

- T002, T003, T004, T005 within Phase 2
- T006 and T007 within Phase 3 (US1)
- T011 and T012 within Phase 4 (US2)
- T017 and T018 within Phase 5 (US3 model + service start simultaneously)
- T022 and T023 within Phase 6 (US4 model + schema)
- T028, T029, T030, T031 within Phase 8 (all independent test files)
- US1 (Phase 3) and US2 (Phase 4) in parallel across team members after Phase 2

---

## Parallel Example: Phase 2 Foundation

```bash
# After T001 (migration) commits — these 4 can all run simultaneously:
Task: "T002 Extend enums in execution/models.py"
Task: "T003 Add exception classes to execution/exceptions.py"
Task: "T004 Add ExecutionRolledBackEvent to execution/events.py"
Task: "T005 Add CheckpointPolicySchema to execution/schemas.py"
```

## Parallel Example: US1 Phase 3

```bash
# These two can run simultaneously:
Task: "T006 Add ReprioritizationTrigger model to execution/models.py"
Task: "T007 Add trigger schemas to execution/schemas.py"
# Then:
Task: "T008 Create ReprioritizationService in execution/reprioritization.py"
# Then:
Task: "T009 Integrate into scheduler.py"
Task: "T010 Add trigger endpoints to router.py"  # can parallel with T009
```

## Parallel Example: US2 Phase 4

```bash
# These two can run simultaneously:
Task: "T011 Extend ExecutionCheckpoint model in execution/models.py"
Task: "T012 Add checkpoint response schemas to execution/schemas.py"
# Then:
Task: "T013 Create CheckpointService in execution/checkpoint_service.py"
# Then (can parallel):
Task: "T014 Integrate checkpoint capture into scheduler.py"
Task: "T015 Add checkpoint list/get endpoints to router.py"
Task: "T016 Snapshot policy in ExecutionService.create_execution()"
```

---

## Implementation Strategy

### MVP (US1 + US2 — P1 Stories)

1. Complete Phase 2: Foundation (T001–T005)
2. Complete Phase 3: US1 Reprioritization (T006–T010)
3. Complete Phase 4: US2 Checkpoint Capture (T011–T016)
4. **STOP and VALIDATE**: Run Scenarios S1–S7 from quickstart.md
5. Deploy/demo with dynamic queue re-ordering + pre-tool checkpoints

### Incremental Delivery

1. Foundation → US1 → US2 → **Demo: operators see queue respond to SLA pressure + recovery points**
2. US3 (Rollback) → **Demo: operators can restore from bad tool results**
3. US4 (Custom Policy) → **Demo: workflow admins fine-tune checkpoint overhead**
4. US5 (Audit Listing) → **Demo: compliance queries show full checkpoint history**
5. Phase 8 Polish → test suite complete

### Parallel Team Strategy

With two developers after Foundation:
- **Dev A**: US1 (T006–T010) then US3 (T017–T021)
- **Dev B**: US2 (T011–T016) then US4 (T022–T025)
- Both: Phase 8 tests (T028–T031)

---

## Notes

- `[P]` tasks share different files — safe to run in parallel
- `[Story]` label maps every task to its user story for traceability
- Migration T001 MUST complete and be applied before any model code referencing new columns is tested
- Enum value additions (`paused`, `rolled_back`, `rollback_failed`) require Alembic DDL (`ADD VALUE IF NOT EXISTS`) — they cannot be added via Python-only enum class changes
- Existing `_maybe_checkpoint()` (every-100-events compaction) in `execution/scheduler.py` remains unchanged — the new policy-aware capture is a separate hook
- The `checkpoint_policy_snapshot` column added in T001/T011 is nullable — existing executions with null use the default policy (FR-029 backward compatibility guaranteed without data migration)
- Rollback eligibility states (`paused`, `waiting_for_approval`, `failed`) must be checked before any state restoration begins (FR-016)
- All rollbacks MUST be atomic — `RollbackFailedError` transitions to `rollback_failed` quarantine on any mid-restore exception (FR-028)
