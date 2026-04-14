# Tasks: Workflow Definition, Compilation, and Execution

**Input**: Design documents from `/specs/029-workflow-execution-engine/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/execution-api.md ✓, quickstart.md ✓

**Tests**: Included — SC-014 requires ≥95% test coverage.

**Organization**: Tasks grouped by user story for independent implementation and testing. Two bounded contexts: `workflows/` (catalog) and `execution/` (hot path).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label [US1]–[US8]

---

## Phase 1: Setup

**Purpose**: Create bounded context skeletons, exception hierarchies.

- [x] T001 Create `apps/control-plane/src/platform/workflows/` with `__init__.py` and `apps/control-plane/src/platform/execution/` with `__init__.py`
- [x] T002 [P] Create `apps/control-plane/src/platform/workflows/exceptions.py` — `WorkflowNotFoundError(NotFoundError)`, `WorkflowCompilationError(ValidationError)`, `TriggerNotFoundError(NotFoundError)` inheriting from `PlatformError`
- [x] T003 [P] Create `apps/control-plane/src/platform/execution/exceptions.py` — `ExecutionNotFoundError(NotFoundError)`, `ExecutionAlreadyRunningError(ValidationError)`, `HotChangeIncompatibleError(ValidationError)`, `ApprovalAlreadyDecidedError(ValidationError)` inheriting from `PlatformError`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: IR types, SQLAlchemy models, Pydantic schemas, repositories, Alembic migration, event skeletons, DI. Must be complete before any user story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Create `apps/control-plane/src/platform/workflows/ir.py` — `RetryConfigIR`, `ApprovalConfigIR`, `StepIR`, `WorkflowIR` Python dataclasses per data-model.md with `to_dict()` / `from_dict()` classmethods for JSONB round-trip serialization
- [x] T005 Create `apps/control-plane/src/platform/workflows/schemas/v1.json` — JSON Schema for workflow YAML v1 matching `WorkflowIR` structure: required `schema_version` (int), required `steps` (array of step objects with `id`, `step_type`, optional `agent_fqn`, `tool_fqn`, `input_bindings`, `retry_config`, `timeout_seconds`, `compensation_handler`, `approval_config`, `reasoning_mode`, `context_budget_tokens`, `parallel_group`, `condition_expression`)
- [x] T006 Create `apps/control-plane/src/platform/workflows/models.py` — `WorkflowStatus`, `TriggerType` enums + 3 SQLAlchemy models `WorkflowDefinition`, `WorkflowVersion`, `WorkflowTriggerDefinition` per data-model.md; use `Base, UUIDMixin, TimestampMixin, AuditMixin, WorkspaceScopedMixin` mixins; `(definition_id, version_number) UNIQUE` on `workflow_versions`
- [x] T007 Create `apps/control-plane/src/platform/execution/models.py` — `ExecutionStatus`, `ExecutionEventType`, `ApprovalDecision`, `CompensationOutcome`, `ApprovalTimeoutAction` enums + 7 SQLAlchemy models `Execution`, `ExecutionEvent`, `ExecutionCheckpoint`, `ExecutionDispatchLease`, `ExecutionTaskPlanRecord`, `ExecutionApprovalWait`, `ExecutionCompensationRecord` per data-model.md; `ExecutionEvent` has NO `updated_at` — only `created_at` (immutable)
- [x] T008 Create Alembic migration `apps/control-plane/migrations/versions/029_workflow_execution_engine.py` — creates all 10 tables (`workflow_definitions`, `workflow_versions`, `workflow_trigger_definitions`, `executions`, `execution_events`, `execution_checkpoints`, `execution_dispatch_leases`, `execution_task_plan_records`, `execution_approval_waits`, `execution_compensation_records`) with correct indices, FK constraints, PostgreSQL enum types, `(execution_id, sequence) UNIQUE` on `execution_events`
- [x] T009 [P] Create `apps/control-plane/src/platform/workflows/schemas.py` — all Pydantic schemas per data-model.md: `WorkflowCreate`, `WorkflowUpdate`, `WorkflowVersionResponse`, `WorkflowResponse`, `WorkflowListResponse`, `TriggerCreate`, `TriggerResponse`; use `WorkflowStatus`, `TriggerType` from models.py
- [x] T010 [P] Create `apps/control-plane/src/platform/execution/schemas.py` — all Pydantic schemas per data-model.md: `ExecutionCreate`, `ExecutionResponse`, `ExecutionListResponse`, `ExecutionEventResponse`, `ExecutionStateResponse`, `CheckpointResponse`, `TaskPlanRecordResponse`, `TaskPlanFullResponse`, `ApprovalDecisionRequest`, `ReprioritizationEvent`, `HotChangeRequest`, `HotChangeCompatibilityResult`
- [x] T011 Create `apps/control-plane/src/platform/workflows/repository.py` — `WorkflowRepository` with all async methods: `create_definition`, `get_definition_by_id`, `list_definitions`, `create_version`, `get_version_by_number`, `list_versions`, `update_current_version_id`, `create_trigger`, `get_trigger_by_id`, `list_triggers`, `update_trigger`, `delete_trigger`; all `async`, `AsyncSession` parameter
- [x] T012 Create `apps/control-plane/src/platform/execution/repository.py` — `ExecutionRepository` with async methods: `create_execution`, `get_execution_by_id`, `list_executions`, `update_execution_status`, `append_event` (INSERT only — never UPDATE/DELETE), `get_events`, `count_events`, `create_checkpoint`, `get_latest_checkpoint`, `create_dispatch_lease`, `release_dispatch_lease`, `upsert_task_plan_record`, `get_task_plan_record`, `create_approval_wait`, `get_approval_wait`, `update_approval_wait`, `create_compensation_record`
- [x] T013 [P] Create `apps/control-plane/src/platform/workflows/events.py` — `WorkflowPublishedEvent`, `TriggerFiredEvent` Pydantic schemas + async publisher functions `publish_workflow_published(producer, event)`, `publish_trigger_fired(producer, event)` via `EventEnvelope`; topic: `workflow.triggers`, key: `workflow_id`
- [x] T014 [P] Create `apps/control-plane/src/platform/execution/events.py` — `ExecutionCreatedEvent`, `ExecutionStatusChangedEvent`, `ExecutionReprioritizedEvent` Pydantic schemas + async publisher functions; topic: `execution.events`, key: `execution_id`; stub consumer functions for `workflow.runtime`, `runtime.reasoning`, `fleet.health`, `workspace.goal`, `interaction.attention` (implementations added in later phases)
- [x] T015 [P] Create `apps/control-plane/src/platform/workflows/dependencies.py` — FastAPI DI: `get_workflow_service` (injects `AsyncSession`, `AIOKafkaProducer`)
- [x] T016 [P] Create `apps/control-plane/src/platform/execution/dependencies.py` — FastAPI DI: `get_execution_service`, `get_scheduler_service` (injects `AsyncSession`, `AsyncRedis`, `AIOKafkaProducer`, `aioboto3.Session`)

**Checkpoint**: Models, schemas, repositories, events, and DI ready. User story implementations can begin.

---

## Phase 3: User Story 1 — Workflow Definition and Compilation (Priority: P1) 🎯 MVP

**Goal**: Workflow developer can author YAML workflows, validate them against schema, compile to typed IR, version immutably, and manage triggers.

**Independent Test**: Create YAML workflow → verify version 1 IR compiled → update YAML → verify version 2 with version 1 unchanged → submit invalid YAML → verify field-level errors. Run: `pytest tests/unit/workflows/test_compiler.py tests/integration/workflows/test_workflow_crud.py`

### Tests for User Story 1

- [x] T017 [P] [US1] Create `apps/control-plane/tests/unit/workflows/test_compiler.py` — test cases matching quickstart.md scenarios 1, 2: valid multi-step YAML compiles to `WorkflowIR` with correct step count and DAG edges; update produces version 2 with version 1 preserved; invalid YAML (negative timeout) returns `WorkflowCompilationError` with `steps[0].timeout_seconds` in error path; circular dependency raises `WorkflowCompilationError` citing the cycle; YAML with undefined step reference raises error with step name in message
- [x] T018 [P] [US1] Create `apps/control-plane/tests/integration/workflows/test_workflow_crud.py` — test cases matching quickstart.md scenarios 1, 2, 11, 12: `POST /workflows` returns version 1; `PATCH` creates version 2 with version 1 still retrievable; `POST /workflows/{id}/archive` removes from active list; `POST /triggers` creates cron trigger; webhook trigger returns 202 on valid HMAC; invalid HMAC returns 401

### Implementation for User Story 1

- [x] T019 [P] [US1] Create `apps/control-plane/src/platform/workflows/compiler.py` — `WorkflowCompiler` class with `compile(yaml_source: str, schema_version: int) -> WorkflowIR` (synchronous, CPU-bound); step 1: `yaml.safe_load` → step 2: `jsonschema.validate` against `schemas/v{N}.json` (raise `WorkflowCompilationError` with path + message per validation error) → step 3: check DAG for cycles (DFS, raise on cycle) → step 4: build `WorkflowIR` from validated dict; `validate_compatibility(old_ir: WorkflowIR, new_ir: WorkflowIR, active_step_ids: list[str]) -> HotChangeCompatibilityResult`: check no active step removed, no breaking binding changes
- [x] T020 [P] [US1] Create `apps/control-plane/src/platform/workflows/service.py` — `WorkflowService.__init__`, `create_workflow` (validate+compile in thread pool executor → `repository.create_definition` + `repository.create_version` → emit `workflow.published`), `update_workflow` (compile + new version + update `current_version_id` → emit `workflow.published`), `archive_workflow`, `get_workflow`, `list_workflows`, `get_version`, `list_versions`, `create_trigger` (+ APScheduler `add_job` for cron), `update_trigger`, `delete_trigger` (+ APScheduler `remove_job`), `list_triggers`
- [x] T021 [US1] Create `apps/control-plane/src/platform/workflows/router.py` — `APIRouter(prefix="/workflows")`; all 14 endpoints per contracts/execution-api.md: `POST /`, `GET /`, `GET /{id}`, `PATCH /{id}`, `POST /{id}/archive`, `GET /{id}/versions`, `GET /{id}/versions/{n}`, `POST /{id}/triggers`, `GET /{id}/triggers`, `PATCH /{id}/triggers/{tid}`, `DELETE /{id}/triggers/{tid}`, `POST /{id}/webhook/{tid}` (HMAC validation + `ExecutionService.create_execution`); all thin, delegate to service

**Checkpoint**: 14 workflow endpoints live; YAML workflows compile; versions are immutable; triggers managed.

---

## Phase 4: User Story 2 — Execution Journal and State Projection (Priority: P1)

**Goal**: Every execution state change is recorded as an append-only event; current state can be projected from the journal at any time.

**Independent Test**: Create execution → tick scheduler → journal has events in sequence → project state → verify status matches events → attempt UPDATE on journal row → verify rejected. Run: `pytest tests/unit/execution/test_projector.py tests/integration/execution/test_execution_journal.py`

### Tests for User Story 2

- [x] T022 [P] [US2] Create `apps/control-plane/tests/unit/execution/test_projector.py` — unit tests for all 21 `ExecutionEventType` transitions in `ExecutionProjector`: `created` → status=queued; `dispatched` → step moves to active; `completed` → step moves to completed; `failed` → step moves to failed; `waiting_for_approval` → execution status=waiting_for_approval; `hot_changed` → workflow_version_id updated in state; `reprioritized` → event recorded but active steps unchanged; verify `project_state` is pure/stateless (same inputs → same output)
- [x] T023 [P] [US2] Create `apps/control-plane/tests/integration/execution/test_execution_journal.py` — test cases matching quickstart.md scenario 3: create execution → verify `created` event in journal; verify `sequence=1`; verify `UPDATE execution_events` raises DB-level error; project state → verify status=queued; get journal → verify events in sequence order; scenario 16 (approval gate): approve → resumed journal event appended

### Implementation for User Story 2

- [x] T024 [P] [US2] Create `apps/control-plane/src/platform/execution/projector.py` — `ExecutionProjector` with `project_state(events: list[ExecutionEvent], checkpoint: ExecutionCheckpoint | None) -> ExecutionStateResponse` (synchronous, stateless); initialize from checkpoint data if provided; apply each event via `match event.event_type` state machine → update `completed_step_ids`, `active_step_ids`, `pending_step_ids`, `step_results`, `status`; handle all 21 event types (unknown types are ignored with warning)
- [x] T025 [P] [US2] Create `apps/control-plane/src/platform/execution/service.py` — `ExecutionService.__init__`, `create_execution` (create `Execution` row + append `created` event + emit `execution.created`), `get_execution`, `list_executions`, `get_execution_state` (load latest checkpoint + events after checkpoint → call projector → cache in Redis `exec:state:{id}` TTL 30s), `get_journal`, `cancel_execution` (append `canceled` event + update status)
- [x] T026 [US2] Create `apps/control-plane/src/platform/execution/router.py` — initial execution endpoints per contracts/execution-api.md: `POST /executions`, `GET /executions`, `GET /executions/{id}`, `POST /executions/{id}/cancel`, `GET /executions/{id}/state`, `GET /executions/{id}/journal`; all thin, delegate to service

**Checkpoint**: Execution CRUD live; journal append-only; state projection from events; Redis state cache working.

---

## Phase 5: User Story 3 — Step Scheduling and Dispatch (Priority: P1)

**Goal**: Scheduler identifies runnable steps, computes priority, acquires dispatch lease, assembles context, allocates reasoning budget, dispatches to runtime controller. Approval gate steps pause execution.

**Independent Test**: Create 2-step execution → tick → only step 1 dispatched (step 2 has unmet dependency) → verify dispatch lease in Redis → verify step 1 not dispatched again on second tick (lease active) → simulate step 1 completion → tick → step 2 dispatched. Run: `pytest tests/integration/execution/test_scheduler_dispatch.py`

### Tests for User Story 3

- [x] T027 [P] [US3] Create `apps/control-plane/tests/unit/execution/test_priority_scorer.py` — unit tests for `PriorityScorer.compute`: urgency-dominant case; SLA deadline proximity increases priority; higher importance wins over lower; reasoning budget depletion reduces priority; dependency depth breaks ties; test scoring consistency (deterministic for same inputs)
- [x] T028 [P] [US3] Create `apps/control-plane/tests/integration/execution/test_scheduler_dispatch.py` — test cases matching quickstart.md scenarios 4, 5: sequential DAG dispatches step A before step B; higher SLA-proximity step dispatched first; Redis lease prevents duplicate dispatch; `tick()` called again while lease active → no second dispatch; expired lease TTL → step re-enters runnable pool on next tick; approval gate step → `waiting_for_approval` event written, NOT dispatched to runtime controller, `ExecutionApprovalWait` record created; scenario 16 approval flow end-to-end

### Implementation for User Story 3

- [x] T029 [P] [US3] Create `apps/control-plane/src/platform/execution/scheduler.py` — `PriorityScorer.compute(step, execution_context) -> float` (score from urgency×0.35 + importance×0.20 + risk×0.15 + severity×0.10 + sla_deadline_factor×0.10 + dependency_depth×0.05 + reasoning_budget_factor×0.05); `SchedulerService.__init__`; `SchedulerService.tick(session)`: (1) query executions in `queued`/`running` status, (2) for each: load latest checkpoint + recent events → project runnable steps via `ExecutionProjector`, (3) skip if `approval_gate` step type → handle_approval_gate branch, (4) compute priority via `PriorityScorer`, (5) acquire Redis lease `SET exec:lease:{execution_id}:{step_id} worker_id NX PX 300000` (skip if lease exists), (6) append `dispatched` event, (7) dispatch to `RuntimeControlService.dispatch()` gRPC stub, (8) on approval gate: append `waiting_for_approval` event + create `ExecutionApprovalWait` row + call `InteractionsService.create_approval_request()`
- [x] T030 [US3] Implement approval decision handling and timeout in `apps/control-plane/src/platform/execution/service.py` — `record_approval_decision(execution_id, step_id, decision, decided_by, comment, session)`: update `ExecutionApprovalWait.decision` + append `approved`/`rejected` journal event + emit `execution.status_changed`; add APScheduler job (60s interval) that scans overdue `ExecutionApprovalWait` rows (timeout_at < now, decision IS NULL) and applies `timeout_action` (fail/skip/escalate); add approval endpoints to `execution/router.py` (`GET /executions/{id}/approvals`, `POST /executions/{id}/approvals/{step_id}/decide`)

**Checkpoint**: Scheduler dispatches with correct priority; dispatch lease prevents duplicates; approval gates pause execution correctly.

---

## Phase 6: User Story 6 — Task Plan Recording (Priority: P2)

**Goal**: Before every dispatch, a TaskPlanRecord is persisted to PostgreSQL + MinIO capturing planning decisions (considered agents/tools, selected agent + rationale, parameter provenance, rejected alternatives).

**Independent Test**: Intercept scheduler just before gRPC dispatch → verify TaskPlanRecord row in PostgreSQL AND JSON file in MinIO exist BEFORE the dispatch call completes → retrieve via API → verify full payload. Run: `pytest tests/integration/execution/test_task_plan_records.py`

### Tests for User Story 6

- [x] T031 [P] [US6] Create `apps/control-plane/tests/integration/execution/test_task_plan_records.py` — test cases matching quickstart.md scenario 14: intercept dispatch → verify TaskPlanRecord PostgreSQL row exists before gRPC call; verify MinIO object at `storage_key` path exists; `GET /executions/{id}/task-plan` returns metadata list; `GET /executions/{id}/task-plan/{step_id}` returns full payload including `considered_agents`, `parameters` with provenance, `rejected_alternatives`; verify task plan is distinct from journal events (different endpoint, different schema)

### Implementation for User Story 6

- [x] T032 [US6] Extend `apps/control-plane/src/platform/execution/scheduler.py` `SchedulerService.tick()` — add `_persist_task_plan(execution_id, step_id, session)` called BEFORE `RuntimeControlService.dispatch()`; builds `TaskPlanRecord` payload (in test/mock mode uses stub data from context engineering; in prod calls `ContextEngineeringService.get_plan_context()`); writes full JSON payload to MinIO bucket `execution-task-plans` at `{execution_id}/{step_id}/task-plan.json` via `aioboto3`; writes metadata row to `execution_task_plan_records` via repository; if MinIO write fails: retry once then log error but DO NOT block dispatch (best-effort, not blocking)
- [x] T033 [P] [US6] Add task plan endpoints to `apps/control-plane/src/platform/execution/service.py` — `get_task_plan(execution_id, step_id, session)`: if step_id provided → load metadata row + fetch JSON from MinIO → return `TaskPlanFullResponse`; if no step_id → return list of metadata rows as `list[TaskPlanRecordResponse]`; add to `apps/control-plane/src/platform/execution/router.py`: `GET /executions/{id}/task-plan`, `GET /executions/{id}/task-plan/{step_id}`

**Checkpoint**: Every dispatch has TaskPlanRecord in PostgreSQL + MinIO BEFORE gRPC call; task plan API accessible.

---

## Phase 7: User Story 4 — Replay, Resume, and Rerun (Priority: P2)

**Goal**: Operators can reconstruct exact execution state from journal (replay), continue from last checkpoint (resume), or create a new lineage from same workflow version (rerun).

**Independent Test**: Run 5-step workflow to completion → replay → verify state matches original; run 5-step workflow that fails at step 3 → resume → verify steps 1-2 not re-dispatched; rerun completed execution → verify new ID with lineage link. Run: `pytest tests/integration/execution/test_replay_resume_rerun.py`

### Tests for User Story 4

- [x] T034 [P] [US4] Create `apps/control-plane/tests/integration/execution/test_replay_resume_rerun.py` — test cases matching quickstart.md scenarios 6, 7, 8: replay completed execution → reconstructed state matches original (all completed_step_ids equal, step_results equal, no new events written); resume failed execution at step 3 → new Execution created with `parent_execution_id` set → steps a+b NOT in dispatch calls for new execution → step_c IS dispatched; rerun completed execution → new Execution with `rerun_of_execution_id` set, same `workflow_version_id`, journal starts at sequence=1

### Implementation for User Story 4

- [x] T035 [P] [US4] Add replay/resume/rerun to `apps/control-plane/src/platform/execution/service.py` — `replay_execution(execution_id, session)`: load all events ordered by sequence + `ReasoningTraceRef` events payload → call projector → return `ExecutionStateResponse` (no new events written); `resume_execution(execution_id, session)`: load latest checkpoint → create new `Execution(parent_execution_id=execution_id, status=queued)` + copy checkpoint `step_results` as pre-completed data in first journal event + append `created` event → return new `ExecutionResponse`; `rerun_execution(execution_id, input_overrides, session)`: load original execution → create new `Execution(rerun_of_execution_id=execution_id, workflow_version_id=original.workflow_version_id, input_parameters=merged(original.input_parameters, input_overrides))` → append `created` event → return new `ExecutionResponse`
- [x] T036 [P] [US4] Add auto-checkpoint to `apps/control-plane/src/platform/execution/scheduler.py` `SchedulerService.tick()` — after appending any journal event, check if `event.sequence % 100 == 0`; if yes: project current state → write `ExecutionCheckpoint(last_event_sequence, step_results, completed_step_ids, pending_step_ids, active_step_ids, execution_data)` via repository
- [x] T037 [US4] Add replay/resume/rerun endpoints to `apps/control-plane/src/platform/execution/router.py` — `POST /executions/{id}/replay`, `POST /executions/{id}/resume`, `POST /executions/{id}/rerun`

**Checkpoint**: Replay, resume, and rerun all working; checkpoint written every 100 events; lineage links present.

---

## Phase 8: User Story 5 — Execution Triggers (Priority: P2)

**Goal**: Workflows triggered by all 7 mechanisms: cron, webhook, workspace-goal, event-bus, orchestrator, manual, API.

**Independent Test**: Configure cron trigger → simulate time → verify execution created; configure webhook trigger → send request with valid HMAC → verify 202 + execution created; send request with invalid HMAC → verify 401; emit workspace-goal Kafka event → verify execution created with `correlation_goal_id` set. Run: `pytest tests/integration/execution/test_triggers.py`

### Tests for User Story 5

- [x] T038 [P] [US5] Create `apps/control-plane/tests/integration/execution/test_triggers.py` — test cases matching quickstart.md scenarios 11, 12, 13: webhook with valid HMAC → 202 + execution with TriggerType.WEBHOOK; webhook with invalid HMAC → 401; cron handler fires → execution created with TriggerType.CRON; workspace-goal Kafka event with matching goal_type_pattern → execution created with `correlation_goal_id` set; event-bus Kafka event matching topic pattern → execution created with TriggerType.EVENT_BUS; concurrency limit reached → 409; no matching trigger → no execution created

### Implementation for User Story 5

- [x] T039 [P] [US5] Add APScheduler cron registration to `apps/control-plane/src/platform/workflows/service.py` — on `create_trigger(trigger_type=CRON)`: register `AsyncIOScheduler.add_job(cron_trigger_handler, CronTrigger.from_crontab(expr, timezone=tz), id=trigger_id)`; on `delete_trigger` or `is_active=False`: `scheduler.remove_job(trigger_id)`; add startup hook to `apps/control-plane/entrypoints/worker_main.py` that loads all active CRON triggers from DB and registers them in APScheduler on startup
- [x] T040 [P] [US5] Implement Kafka consumers for triggers in `apps/control-plane/src/platform/execution/events.py` — `workspace_goal_consumer_handler(event, session)`: load all active WORKSPACE_GOAL triggers matching `event.workspace_id` and `event.goal_type` against `trigger.config.goal_type_pattern` (fnmatch); for each match: check concurrency limit → call `execution_service.create_execution()` with `correlation_goal_id=event.goal_id`; `event_bus_consumer_handler(event, session)`: load all active EVENT_BUS triggers matching `event.topic` and `event.event_type`; create execution on match; register both consumers in Kafka consumer group startup
- [x] T041 [US5] Add HMAC webhook validation to existing `POST /workflows/{id}/webhook/{trigger_id}` endpoint in `apps/control-plane/src/platform/workflows/router.py` — compute `hmac.new(trigger.config.secret.encode(), request_body, hashlib.sha256).hexdigest()`; compare with `X-Webhook-Signature` header value (constant-time comparison via `hmac.compare_digest`); raise `HTTPException(401)` on mismatch; on success call `execution_service.create_execution()` and return `202 {"execution_id": "..."}`

**Checkpoint**: All 7 trigger types initiate workflow execution; HMAC validation working; Kafka consumers active.

---

## Phase 9: User Story 7 — Hot Change and Compensation (Priority: P3)

**Goal**: Operators can update a running workflow's definition if compatible; completed steps can be compensated (undone).

**Independent Test**: Start 5-step execution at step 2 → add step 6 (compatible) → verify change applied; try to remove step 2 (active) → verify 409 with issues list, execution unchanged; trigger compensation on completed step → verify compensation_record created + `compensated` event in journal. Run: `pytest tests/integration/execution/test_hot_change_compensation.py`

### Tests for User Story 7

- [x] T042 [P] [US7] Create `apps/control-plane/tests/integration/execution/test_hot_change_compensation.py` — test cases matching quickstart.md scenarios 9, 10: compatible hot change (add step) applied → `hot_changed` event in journal; incompatible hot change (remove active step) → `HotChangeIncompatibleError` raised, execution status unchanged; compensation triggered on completed step → `ExecutionCompensationRecord` created with `outcome=completed` + `compensated` event; compensation on step without handler → record with `outcome=not_available`; compensation on in-progress step → rejected

### Implementation for User Story 7

- [x] T043 [P] [US7] Add hot change methods to `apps/control-plane/src/platform/execution/service.py` — `validate_hot_change(execution_id, new_version_id, session)`: project state → get active_step_ids → load old_ir (from current `workflow_version_id`) and new_ir (from `new_version_id`) → call `WorkflowCompiler.validate_compatibility(old_ir, new_ir, active_step_ids)` (in thread pool executor) → return `HotChangeCompatibilityResult`; `apply_hot_change(execution_id, new_version_id, session)`: call `validate_hot_change` first → if compatible: update `execution.workflow_version_id` → append `hot_changed` event with `payload={old_version_id, new_version_id}` → invalidate Redis state cache; `trigger_compensation(execution_id, step_id, session)`: verify step completed → find `compensation_handler` in IR → create `ExecutionCompensationRecord(outcome=not_available)` if no handler; if handler exists: dispatch as special step to runtime controller → on completion callback: update record `outcome=completed/failed` + append journal event
- [x] T044 [US7] Add hot change and compensation endpoints to `apps/control-plane/src/platform/execution/router.py` — `POST /executions/{id}/hot-change` (validates then applies; returns 409 with issues on incompatible), `POST /executions/{id}/compensation/{step_id}`

**Checkpoint**: Hot change validates compatibility; incompatible changes rejected; compensation records created.

---

## Phase 10: User Story 8 — Dynamic Re-Prioritization (Priority: P3)

**Goal**: Queued steps are reordered within 500ms when SLA, budget, resource, or external triggers fire; `reprioritized` event emitted with trigger reason.

**Independent Test**: Queue 5 steps → simulate budget threshold breach Kafka event → verify steps reordered (highest-urgency first) → verify `reprioritized` journal event with correct trigger_reason and steps_affected list → verify re-prioritization event on `execution.events` Kafka topic. Run: `pytest tests/integration/execution/test_reprioritization.py`

### Tests for User Story 8

- [x] T045 [P] [US8] Create `apps/control-plane/tests/integration/execution/test_reprioritization.py` — test cases matching quickstart.md scenario 15: budget breach event → `reprioritized` journal event appended with `trigger_reason=budget_threshold_breached`; SLA deadline > 80% consumed → SLA-bound step promoted in queue; fleet member failure → re-prioritization triggered for fleet-linked executions; already-dispatched steps unaffected; `execution.events` Kafka message with `event_type=execution.reprioritized` emitted

### Implementation for User Story 8

- [x] T046 [P] [US8] Add re-prioritization to `apps/control-plane/src/platform/execution/scheduler.py` — `SchedulerService.handle_reprioritization_trigger(trigger_reason, execution_id, session)`: (1) get all queued (not dispatched) step IDs for execution from projected state, (2) re-score each via `PriorityScorer.compute()`, (3) sort by new priority descending, (4) append `reprioritized` journal event with payload `{trigger_reason, steps_affected=[step_ids], priority_changes=[{step_id, old_priority, new_priority}]}`, (5) emit `ExecutionReprioritizedEvent` on `execution.events` topic; add SLA check to `tick()`: for each execution with `sla_deadline`, if `datetime.now() > sla_deadline * 0.8` and not already triggered → call `handle_reprioritization_trigger("sla_deadline_approaching", ...)`
- [x] T047 [US8] Implement Kafka trigger consumers in `apps/control-plane/src/platform/execution/events.py` — `reasoning_budget_consumer_handler(event, session)`: on `runtime.reasoning` topic with `event_type=budget.threshold_breached` → call `scheduler_service.handle_reprioritization_trigger("budget_threshold_breached", event.execution_id, session)`; `fleet_health_consumer_handler(event, session)`: on `fleet.health` with failed member → find executions linked to `fleet_id` → call `handle_reprioritization_trigger("resource_constraint_changed", ...)`; `attention_consumer_handler(event, session)`: on `interaction.attention` → find execution linked to attention context → call `handle_reprioritization_trigger("external_event", ...)`; register all three consumers in Kafka startup

**Checkpoint**: Re-prioritization fires on all 5 trigger types; queue reordered within tick cycle; events emitted.

---

## Phase 11: Polish and Cross-Cutting Concerns

**Purpose**: Wire routers into main API, configure APScheduler and Kafka in lifespan hooks, verify integration, linting, types, coverage.

- [x] T048 Register `workflows.router` and `execution.router` in `apps/control-plane/src/platform/api/__init__.py` — add `app.include_router(workflows_router, prefix="/api/v1")` and `app.include_router(execution_router, prefix="/api/v1")`
- [x] T049 Wire APScheduler into `apps/control-plane/entrypoints/worker_main.py` lifespan — on startup: create `AsyncIOScheduler`, load all active CRON triggers from DB and register, add `SchedulerService.tick` job (interval 1s), add approval timeout scan job (interval 60s); on shutdown: shutdown scheduler gracefully
- [x] T050 [P] Register `execution/events.py` Kafka consumers in the `worker` profile lifespan — subscribe consumer group to `workflow.runtime` (step completion), `runtime.reasoning` (budget threshold), `fleet.health` (member failure), `interaction.attention` (external event), `workspace.goal` (workspace-goal trigger)
- [x] T051 [P] Add `tests/integration/workflows/__init__.py` and `tests/integration/execution/__init__.py` + shared `conftest.py` with fixtures — async test session, test PostgreSQL DB with migration 029 applied, Redis client, MinIO test bucket `execution-task-plans`, mock gRPC stubs (`RuntimeControlServiceStub`, `ReasoningEngineServiceStub`, `ContextEngineeringServiceStub`), `kafka_mock` fixture
- [X] T052 [P] Run `pytest tests/unit/workflows/ tests/unit/execution/ tests/integration/workflows/ tests/integration/execution/ --cov=platform/workflows --cov=platform/execution --cov-report=term-missing` — confirm ≥95% line coverage; add missing test cases for any uncovered branches
- [X] T053 [P] Run `ruff check apps/control-plane/src/platform/workflows/ apps/control-plane/src/platform/execution/` and `mypy --strict apps/control-plane/src/platform/workflows/ apps/control-plane/src/platform/execution/` — fix all violations; confirm all public functions have docstrings; all signatures fully annotated

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001–T003 sequential then parallel
- **Foundational (Phase 2)**: Depends on Phase 1; T004→T005 (IR before schema); T006–T007 parallel (different models files); T008 depends on T006+T007 (migration needs models); T009–T010 parallel (depends on T006–T007); T011–T012 parallel (depends on T006–T007); T013–T016 parallel (depend on T009–T010)
- **US1 (Phase 3)**: Depends on Foundational; T017+T018+T019+T020 parallelizable; T021 depends on T020
- **US2 (Phase 4)**: Depends on Foundational + Alembic migration (T008); T022+T023+T024+T025 parallelizable; T026 depends on T025
- **US3 (Phase 5)**: Depends on US2 (scheduler reads execution service + projector); T027+T028 parallel (tests can be written before impl); T029 depends on T024 (projector); T030 extends T029
- **US6 (Phase 6)**: Depends on US3 (extends scheduler); T031 parallelizable with tests; T032 depends on T029; T033 depends on T032
- **US4 (Phase 7)**: Depends on US2 + US3 (needs checkpoints from scheduler); T034 parallelizable; T035+T036 parallelizable; T037 depends on T035
- **US5 (Phase 8)**: Depends on Foundational + US1 (cron needs WorkflowService + APScheduler from US1); T038 parallel; T039 depends on US1 workflow service; T040 depends on T026 (execution router); T041 depends on T021 (workflow router)
- **US7 (Phase 9)**: Depends on US3 (hot change needs dispatch lease check) + US1 (needs WorkflowCompiler.validate_compatibility); T042 parallel; T043+T044 parallel
- **US8 (Phase 10)**: Depends on US3 (extends scheduler + re-uses PriorityScorer); T045 parallel; T046+T047 parallel
- **Polish (Phase 11)**: Depends on all user story phases; T051–T053 parallel after T048–T050

### User Story Dependencies

- **US1 (P1)**: Independent after Foundational
- **US2 (P1)**: Independent after Foundational
- **US3 (P1)**: Depends on US2 (scheduler projects state from events)
- **US6 (P2)**: Depends on US3 (extends scheduler.tick)
- **US4 (P2)**: Depends on US2 + US3 (needs checkpoint infrastructure)
- **US5 (P2)**: Depends on US1 (cron registration in WorkflowService) + US2 (ExecutionService.create_execution)
- **US7 (P3)**: Depends on US1 (WorkflowCompiler.validate_compatibility) + US3 (active step detection)
- **US8 (P3)**: Depends on US3 (PriorityScorer, scheduler architecture)

---

## Parallel Examples

### Within US1 (after Foundational):

```bash
# Launch simultaneously:
Task T017: "Create test_compiler.py unit tests"
Task T018: "Create test_workflow_crud.py integration tests"
Task T019: "Implement WorkflowCompiler (compiler.py)"
Task T020: "Implement WorkflowService (service.py)"
# Then:
Task T021: "Create workflow router.py" (depends on T020)
```

### Within US2 (after Foundational):

```bash
# Launch simultaneously:
Task T022: "Create test_projector.py unit tests"
Task T023: "Create test_execution_journal.py integration tests"
Task T024: "Implement ExecutionProjector (projector.py)"
Task T025: "Implement ExecutionService (service.py)"
# Then:
Task T026: "Create execution router.py" (depends on T025)
```

### US1 + US2 in parallel (after Foundational):

```bash
# Developer A: US1 (T017-T021)
# Developer B: US2 (T022-T026)
# Both start simultaneously after Phase 2 completion
```

### US6 + US4 in parallel (after US3):

```bash
# Developer A: US6 — T031-T033 (TaskPlanRecord)
# Developer B: US4 — T034-T037 (Replay/Resume/Rerun)
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 — Workflows can be compiled and versioned
4. Complete Phase 4: US2 — Execution journal and state projection live
5. Complete Phase 5: US3 — **Scheduler dispatches steps — execution pipeline active**
6. **STOP and VALIDATE**: Manual trigger creates execution → scheduler dispatches → runtime controller receives step

### Incremental Delivery

1. Setup + Foundational → skeletons ready
2. + US1 → Workflows can be authored, validated, compiled
3. + US2 → Executions start and journal events record
4. + US3 → **Full dispatch pipeline active (MVP ship point)**
5. + US6 → TaskPlanRecord audit for every dispatch (trust compliance)
6. + US4 → Replay/resume/rerun operational
7. + US5 → All 7 trigger types active
8. + US7 → Hot change + compensation for production resilience
9. + US8 → Dynamic re-prioritization for SLA-critical workloads

### Parallel Team Strategy (3 developers after US3):

- Developer A: US6 (TaskPlanRecord) → US7 (Hot Change)
- Developer B: US4 (Replay/Resume/Rerun)
- Developer C: US5 (Triggers) → US8 (Re-prioritization)

---

## Notes

- [P] tasks = different files, no blocking dependencies — safe to run in parallel
- SC-014 requires ≥95% coverage — all test tasks are required
- **`execution_events` INSERT-only** (T012): `ExecutionRepository.append_event` must be the ONLY path that touches this table. Never expose an update method. Enforce at service layer too.
- **`WorkflowCompiler.compile()` is synchronous** (T019): Call via `asyncio.get_event_loop().run_in_executor(None, compiler.compile, ...)` from `WorkflowService.validate_and_compile()`
- **TaskPlanRecord before dispatch** (T032): The MinIO write and PostgreSQL insert MUST complete before `RuntimeControlService.dispatch()` is called. On MinIO failure: log error, proceed with dispatch (best-effort audit, not blocking guard).
- **`HMAC.compare_digest`** (T041): Use constant-time comparison to prevent timing attacks on webhook signature validation.
- **Approval gate detour** (T029): When `step.step_type == "approval_gate"`, the scheduler MUST NOT call `RuntimeControlService.dispatch()`. It creates `ExecutionApprovalWait` and notifies via `InteractionsService` only.
- **SLA deadline re-prioritization** (T046): Compute threshold per execution, not globally. `threshold = execution.sla_deadline - timedelta(seconds=(sla_deadline - created_at).total_seconds() * 0.2)` — fire when `now > threshold`.
- **Workspace-goal trigger GID** (T040): `correlation_goal_id` on the new Execution MUST be set from `event.goal_id` — this satisfies constitution §X (GID is mandatory).
