# Implementation Plan: Workflow Definition, Compilation, and Execution

**Branch**: `029-workflow-execution-engine` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/029-workflow-execution-engine/spec.md`

## Summary

Implement two bounded contexts in the Python control plane monolith: `workflows/` (YAML parser + JSON Schema validation + GovernanceCompiler IR + trigger definition CRUD + APScheduler cron registration) and `execution/` (append-only execution journal + state projector with Redis cache + priority-aware scheduler with dispatch lease + TaskPlanRecord persistence to MinIO + replay/resume/rerun + hot change compatibility check + compensation + 7 trigger types + dynamic re-prioritization + approval gates). Dispatch via gRPC to RuntimeControlService and ReasoningEngineService.

## Technical Context

**Language/Version**: Python 3.12+ (async everywhere)
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2.x, SQLAlchemy 2.x (async), Alembic 1.13+, aiokafka 0.11+, redis-py 5.x (async), aioboto3 latest (MinIO), APScheduler 3.x, PyYAML 6.x, jsonschema 4.x, grpcio 1.65+ (RuntimeControlService + ReasoningEngineService clients), pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ (strict)
**Storage**: PostgreSQL 16+ (10 new tables: workflow_definitions, workflow_versions, workflow_trigger_definitions, executions, execution_events, execution_checkpoints, execution_dispatch_leases, execution_task_plan_records, execution_approval_waits, execution_compensation_records), Redis 7+ (dispatch leases + state cache), MinIO (task plan payloads in `execution-task-plans` bucket)
**Testing**: pytest + pytest-asyncio, live PostgreSQL test DB, Redis, MinIO test bucket, mock gRPC stubs for RuntimeControlService + ReasoningEngineService + ContextEngineeringService; Alembic migration tests
**Target Platform**: Linux server, Kubernetes (`platform-control` namespace), scheduler in `worker` runtime profile
**Project Type**: Two backend bounded contexts within Python control plane monolith
**Performance Goals**: Scheduler tick <100ms (runnable step computation + priority scoring for up to 100 queued steps); state projection <5s (SC-003); re-prioritization <500ms (SC-013)
**Constraints**: §I — monolith only. §IV — no cross-boundary DB. §V — append-only journal (no UPDATE/DELETE on execution_events). §XII — TaskPlanRecord before every dispatch. §X — GID is mandatory for workspace-goal triggers. §XI — secrets never in LLM context (tool gateway handles this, not execution engine directly).
**Scale/Scope**: 10 DB tables, ~16 source files across 2 bounded contexts, 28 REST endpoints, 7 Kafka topics consumed/produced, 3 gRPC service calls, 7 trigger types, 21 execution event types

## Constitution Check

| Gate | Requirement | Status |
|------|-------------|--------|
| §I.Monolith | Stay in Python control plane | PASS — `workflows/` + `execution/` bounded contexts in `apps/control-plane/src/platform/` |
| §III.PostgreSQL | System-of-record in PostgreSQL | PASS — 10 tables for workflow definitions, versions, triggers, executions, journal, checkpoints, leases |
| §III.Redis | Hot-state caching in Redis | PASS — dispatch leases (`exec:lease:{execution_id}:{step_id}`), execution state cache (`exec:state:{execution_id}` TTL 30s) |
| §III.MinIO | Large artifact storage in object storage | PASS — TaskPlanRecord full payloads in `execution-task-plans` bucket |
| §III.Kafka | Async events via Kafka | PASS — `execution.events` (lifecycle) + `workflow.triggers` (async trigger dispatch); consume `workflow.runtime`, `runtime.reasoning`, `fleet.health`, `workspace.goal`, `interaction.attention` |
| §III.NoVectorsInPG | No vector search in PostgreSQL | PASS — N/A; no vector operations in this feature |
| §IV.NoCrossBoundaryDB | No direct access to other contexts' tables | PASS — context engineering via in-process service interface; reasoning engine via gRPC; interactions via in-process service interface for approval calls |
| §V.AppendOnlyJournal | execution_events is append-only | PASS — `ExecutionEventRepository` exposes INSERT only; no UPDATE/DELETE; DB-level constraint enforced via application layer |
| §XI.SecretsNeverInLLM | Secrets never in LLM context | PASS — tool gateway (feature 028) handles this; execution engine dispatches to runtime controller which handles secret injection |
| §XII.TaskPlansAreAudit | TaskPlanRecord before every dispatch | PASS — `SchedulerService.tick()` persists TaskPlanRecord to PostgreSQL + MinIO BEFORE calling `RuntimeControlService.dispatch()` |
| §X.GIDFirstClass | Goal ID in CorrelationContext | PASS — `correlation_goal_id` on every Execution and ExecutionEvent; workspace-goal trigger sets GID on creation |
| §VI.PolicyMachineEnforced | Tool gateway enforces policy | PASS — this feature calls tool gateway (feature 028) before dispatching each step; execution engine does not bypass it |
| QualityGates.Coverage | ≥95% line coverage (pytest) | PASS — SC-014 requires ≥95%; integration tests for all 16 scenarios |
| QualityGates.Async | All code async | PASS — all service, repository, router methods use `async def`; WorkflowCompiler.compile() is sync (CPU-bound, called in thread pool executor) |
| QualityGates.Types | mypy strict passes | PASS — all signatures annotated; Pydantic v2 models enforced |

**Post-design re-check**: All 15 gates PASS. Zero constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/029-workflow-execution-engine/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: 14 decisions
├── data-model.md        # Phase 1: SQLAlchemy models, Pydantic schemas, service signatures
├── quickstart.md        # Phase 1: 16 test scenarios
├── checklists/
│   └── requirements.md  # Spec quality checklist (all pass)
└── contracts/
    └── execution-api.md # Phase 1: 28 endpoints + internal interfaces + Kafka events
```

### Source Code

```text
apps/control-plane/
├── src/platform/
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── models.py           # WorkflowDefinition, WorkflowVersion, WorkflowTriggerDefinition + enums
│   │   ├── schemas.py          # Pydantic CRUD + response schemas
│   │   ├── ir.py               # WorkflowIR, StepIR, RetryConfigIR, ApprovalConfigIR dataclasses
│   │   ├── compiler.py         # WorkflowCompiler (sync, CPU-bound: parse YAML + validate + produce IR)
│   │   ├── service.py          # WorkflowService (CRUD, compilation, trigger management)
│   │   ├── repository.py       # WorkflowRepository (all DB queries)
│   │   ├── events.py           # Kafka event schemas + publisher functions
│   │   ├── router.py           # FastAPI router (14 endpoints)
│   │   ├── exceptions.py       # WorkflowNotFoundError, WorkflowCompilationError, TriggerNotFoundError
│   │   ├── dependencies.py     # FastAPI DI: get_workflow_service
│   │   └── schemas/
│   │       └── v1.json         # JSON Schema for workflow YAML v1
│   │
│   └── execution/
│       ├── __init__.py
│       ├── models.py           # Execution, ExecutionEvent, Checkpoint, DispatchLease, TaskPlanRecord, ApprovalWait, CompensationRecord + enums
│       ├── schemas.py          # Pydantic request/response schemas
│       ├── projector.py        # ExecutionProjector (stateless: journal events → ExecutionStateResponse)
│       ├── service.py          # ExecutionService (CRUD, replay, resume, rerun, hot change, compensation, approvals, task plans)
│       ├── scheduler.py        # SchedulerService (tick, priority scoring, dispatch lease, gRPC dispatch, re-prioritization)
│       ├── repository.py       # ExecutionRepository (journal insert-only, checkpoint, lease, task plan, approval)
│       ├── events.py           # Kafka event schemas + publisher + consumers (workflow.runtime, runtime.reasoning, fleet.health, workspace.goal, interaction.attention)
│       ├── router.py           # FastAPI router (14 endpoints)
│       ├── exceptions.py       # ExecutionNotFoundError, ExecutionAlreadyRunningError, HotChangeIncompatibleError
│       └── dependencies.py     # FastAPI DI: get_execution_service, get_scheduler_service
│
├── migrations/versions/
│   └── 029_workflow_execution_engine.py  # Alembic migration: 10 new tables
│
└── tests/
    ├── unit/
    │   ├── workflows/
    │   │   ├── test_compiler.py         # WorkflowCompiler unit tests (parse, validate, compile, IR)
    │   │   └── test_projector.py        # ExecutionProjector unit tests (state machine transitions)
    │   └── execution/
    │       └── test_priority_scorer.py  # Priority scoring algorithm unit tests
    └── integration/
        ├── workflows/
        │   └── test_workflow_crud.py             # US1: create, version, archive, triggers
        └── execution/
            ├── test_execution_journal.py         # US2: journal append-only, state projection
            ├── test_scheduler_dispatch.py        # US3: priority ordering, lease, dispatch
            ├── test_replay_resume_rerun.py       # US4: replay, resume, rerun
            ├── test_triggers.py                  # US5: all 7 trigger types
            ├── test_task_plan_records.py         # US6: TaskPlanRecord before dispatch
            ├── test_hot_change_compensation.py   # US7: compatible/incompatible change, compensation
            └── test_reprioritization.py          # US8: dynamic re-prioritization
```

**Structure Decision**: Standard two-bounded-context layout per constitution §5.2. `workflows/` is catalog-oriented (slow write, low volume). `execution/` is hot-path (high write throughput, append-heavy). Compiler and projector as separate files (complex independent logic). Scheduler in `execution/` (tight coupling with journal and dispatch lease). Both contexts in `worker` runtime profile.

## Implementation Phases

### Phase 1 — Workflow Definition and Compiler (US1)

**Goal**: Parse, validate, compile YAML workflows. CRUD for definitions, versions, triggers.

**Tasks**:
1. Create `workflows/__init__.py`, `workflows/exceptions.py`
2. Create `workflows/ir.py` — `WorkflowIR`, `StepIR`, `RetryConfigIR`, `ApprovalConfigIR` dataclasses with `to_dict()`/`from_dict()` for JSONB serialization
3. Create `workflows/schemas/v1.json` — JSON Schema for workflow YAML v1
4. Create `workflows/compiler.py` — `WorkflowCompiler.compile(yaml_source, schema_version) -> WorkflowIR` (sync); validates YAML against jsonschema; raises `WorkflowCompilationError` with field-level errors; builds IR from validated dict; `validate_compatibility(old_ir, new_ir, active_step_ids) -> HotChangeCompatibilityResult`
5. Create `workflows/models.py` — 3 SQLAlchemy models (`WorkflowDefinition`, `WorkflowVersion`, `WorkflowTriggerDefinition`) + enums per data-model.md
6. Create `workflows/schemas.py` — all Pydantic schemas
7. Create `workflows/events.py` — `WorkflowPublishedEvent`, `TriggerFiredEvent` + publisher functions; topic: `workflow.triggers`
8. Create `workflows/repository.py` — `WorkflowRepository` with all CRUD queries
9. Create `workflows/service.py` — `WorkflowService`: `create_workflow`, `update_workflow` (new version), `archive_workflow`, `get_workflow`, `list_workflows`, `get_version`, `list_versions`, `create_trigger`, `update_trigger`, `delete_trigger`, `list_triggers`, `validate_and_compile` (calls compiler in thread pool executor)
10. Create `workflows/dependencies.py` + `workflows/router.py` — 14 endpoints
11. Create `tests/unit/workflows/test_compiler.py` — scenarios 1, 2
12. Create `tests/integration/workflows/test_workflow_crud.py` — scenarios 1, 2, 11, 12

### Phase 2 — Execution Journal and State Projector (US2)

**Goal**: Append-only journal, event types, state projection with Redis cache.

**Tasks**:
1. Create `execution/__init__.py`, `execution/exceptions.py`
2. Create `execution/models.py` — 7 SQLAlchemy models + enums per data-model.md
3. Create `execution/schemas.py` — all Pydantic schemas
4. Create Alembic migration `migrations/versions/029_workflow_execution_engine.py` — creates all 10 tables with correct indices, FK constraints, PostgreSQL enum types, INSERT-only policy comment on `execution_events`
5. Create `execution/projector.py` — `ExecutionProjector.project_state(events, checkpoint)` (sync, stateless): applies each `ExecutionEvent` to build `ExecutionStateResponse`; handles all 21 event types via match/case state machine
6. Create `execution/repository.py` — `ExecutionRepository`: INSERT-only `append_event`, `get_events`, `create_execution`, `update_execution_status`, `create_checkpoint`, `get_latest_checkpoint`, `create_dispatch_lease_audit`, `release_dispatch_lease`, `upsert_task_plan`, `get_task_plan`, `create_approval_wait`, `update_approval_wait`, `create_compensation_record`
7. Create `execution/service.py` — `ExecutionService.create_execution`, `get_execution`, `list_executions`, `get_execution_state` (project from checkpoint + events, cache in Redis `exec:state:{id}` TTL 30s), `get_journal`, `cancel_execution`
8. Create `tests/unit/execution/test_projector.py` — all 21 event type transitions
9. Create `tests/integration/execution/test_execution_journal.py` — scenario 3

### Phase 3 — Scheduler, Dispatch, and TaskPlanRecord (US3 + US6)

**Goal**: Priority-aware scheduler, dispatch lease, gRPC dispatch, TaskPlanRecord before every dispatch.

**Tasks**:
1. Create `execution/scheduler.py` — `SchedulerService`: `tick(session)` — query runnable steps from projector → `PriorityScorer.compute(step, execution_context)` → acquire Redis dispatch lease (`exec:lease:{execution_id}:{step_id}` SET NX PX 300000) → `persist_task_plan_record()` (MinIO write + PostgreSQL row) → call `ContextEngineeringService.assemble(...)` → call `ReasoningEngineService.allocate_budget(...)` via gRPC → call `RuntimeControlService.dispatch(...)` via gRPC → append `dispatched` journal event
2. Create `tests/unit/execution/test_priority_scorer.py` — priority algorithm with all 8 inputs
3. Create `tests/integration/execution/test_scheduler_dispatch.py` — scenarios 4, 5
4. Create `tests/integration/execution/test_task_plan_records.py` — scenario 14

### Phase 4 — Replay, Resume, and Rerun (US4)

**Goal**: Reconstruct state from journal, continue from checkpoint, create new lineage.

**Tasks**:
1. Add to `execution/service.py` — `replay_execution` (project all events + reasoning trace refs from journal, return state; no new events written), `resume_execution` (create new Execution with `parent_execution_id`, copy checkpoint data as pre-completed steps, queue new execution), `rerun_execution` (create new Execution with `rerun_of_execution_id`, same workflow_version_id, fresh journal)
2. Add auto-checkpoint logic to `SchedulerService.tick()` — write checkpoint every 100 events
3. Create `tests/integration/execution/test_replay_resume_rerun.py` — scenarios 6, 7, 8

### Phase 5 — Execution Triggers (US5)

**Goal**: All 7 trigger types initiate workflow execution.

**Tasks**:
1. Add trigger handling to `execution/events.py` — Kafka consumers for `workspace.goal` (workspace-goal trigger) and `connector.ingress` (event-bus trigger); APScheduler integration for cron triggers (register/deregister on trigger CRUD)
2. Add webhook endpoint to `execution/router.py` — `POST /workflows/{id}/webhook/{trigger_id}` with HMAC validation
3. Add APScheduler setup to `workflows/service.py` — on `create_trigger(cron)` register `AsyncIOScheduler.add_job`; on `delete_trigger` remove job
4. Create `tests/integration/execution/test_triggers.py` — scenarios 11, 12, 13

### Phase 6 — Hot Change and Compensation (US7)

**Goal**: Validate and apply live workflow updates; invoke and record compensation.

**Tasks**:
1. Add to `execution/service.py` — `validate_hot_change` (project state → get active steps → call `WorkflowCompiler.validate_compatibility(old_ir, new_ir, active_step_ids)`), `apply_hot_change` (update `execution.workflow_version_id` + append `hot_changed` event), `trigger_compensation` (look up compensation handler → dispatch as special step → create `CompensationRecord` → append `compensated`/`compensation_failed` event)
2. Create `tests/integration/execution/test_hot_change_compensation.py` — scenarios 9, 10

### Phase 7 — Dynamic Re-Prioritization (US8)

**Goal**: Reorder queued steps on SLA/budget/resource triggers.

**Tasks**:
1. Add to `execution/scheduler.py` — `handle_reprioritization_trigger(trigger_reason, execution_id, session)`: drain current priority queue for execution → re-score all queued steps → re-insert → append `reprioritized` journal event → emit `execution.reprioritized` on `execution.events`
2. Add Kafka consumers in `execution/events.py` — subscribe to `runtime.reasoning` (budget threshold), `fleet.health` (member failure), `interaction.attention` (external event); call `handle_reprioritization_trigger` on matching events
3. Add SLA deadline check to `SchedulerService.tick()` — compare `now` vs `execution.sla_deadline * 0.8` threshold
4. Create `tests/integration/execution/test_reprioritization.py` — scenario 15

### Phase 8 — Approval Gate (US1 partial — approval_gate step type)

**Goal**: Pause execution on approval gates; resume on decision; timeout handling.

**Tasks**:
1. Add approval gate handling to `SchedulerService.tick()` — detect `approval_gate` step type from IR → append `waiting_for_approval` event → create `ExecutionApprovalWait` → call `InteractionsService.create_approval_request(...)` in-process → do NOT dispatch to runtime controller
2. Add APScheduler timeout job — every 60s check for overdue `ExecutionApprovalWait` rows; apply timeout action (fail/skip/escalate)
3. Add `record_approval_decision` to `ExecutionService` — update `ApprovalWait.decision` → append `approved`/`rejected` event → scheduler resumes (or fails) step on next tick
4. Add approval endpoints to `execution/router.py` — `GET /approvals`, `POST /approvals/{step_id}/decide`
5. Create approval scenarios in `tests/integration/execution/test_execution_journal.py` — scenario 16

### Phase 9 — Polish and Integration

**Goal**: Wire routers into main API, full integration test coverage, ruff + mypy pass.

**Tasks**:
1. Wire `workflows.router` and `execution.router` into `apps/control-plane/src/platform/api/__init__.py`
2. Register APScheduler in app lifespan hooks (`main.py`)
3. Register Kafka consumers for `workflow.runtime`, `workspace.goal`, `runtime.reasoning`, `fleet.health`, `interaction.attention`
4. Run `ruff check` and `mypy --strict` on both contexts — fix all violations
5. Run `pytest tests/ --cov=platform/workflows --cov=platform/execution --cov-report=term-missing` — confirm ≥95% coverage

## Key Decisions

See `research.md` for full rationale. Summary:

1. **Two bounded contexts** (`workflows/` + `execution/`) — catalog vs hot-path separation; different scaling profiles
2. **10 PostgreSQL tables** with JSONB for IR and event payloads — immutable versioning without schema churn
3. **WorkflowCompiler is synchronous** (CPU-bound) — called via `asyncio.run_in_executor()` from async service
4. **Append-only journal** — `ExecutionProjector` builds state from events; Redis caches projection (TTL 30s); checkpoint every 100 events for performance
5. **Redis dispatch lease** — `SET NX PX` for distributed duplicate prevention; PostgreSQL audit row for compliance
6. **TaskPlanRecord persisted before dispatch** — MinIO for full payload; PostgreSQL metadata row for API queries
7. **APScheduler** for cron triggers, approval timeouts, and scheduler tick (1s interval in `worker` profile)
8. **7 trigger types** — cron (APScheduler), webhook (HMAC endpoint), event-bus + workspace-goal (Kafka consumers), orchestrator/manual/API (direct service call)
9. **Re-prioritization** — in-memory asyncio.PriorityQueue drain + re-insert; triggered by Kafka events from reasoning engine, fleet health, and attention channel
10. **Hot change** — conservative compatibility (active steps protected); non-blocking (execution continues during validation)
