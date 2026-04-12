# Research: Workflow Definition, Compilation, and Execution

**Branch**: `029-workflow-execution-engine` | **Date**: 2026-04-12 | **Phase**: 0

Resolved all design decisions before data-model and contracts phases.

---

## Decision 1 — Bounded Context Split: `workflows/` + `execution/`

**Decision**: Two bounded contexts. `workflows/` owns definition, versioning, compilation, triggers, and the JSON Schema registry. `execution/` owns journal, scheduling, dispatch, checkpoints, leases, approval waits, compensation, replay, resume, rerun, re-prioritization, and TaskPlanRecords.

**Rationale**: Clean separation of concerns. Workflow definition is a slow-changing catalog (editors, deployers). Execution is a high-throughput append-heavy hot path. Different scaling profiles, different tables, different cache lifetimes. Both stay in the Python monolith per §I.

**Alternatives considered**:
- Single `workflows/` context: rejected — mixes catalog CRUD with hot-path journal writes; scheduler and journal have no clean ownership
- Three contexts (workflows + scheduler + journal): over-engineering for this scale; scheduler and journal are deeply coupled (scheduler reads journal to compute runnable steps)

---

## Decision 2 — Database Tables (10 total across 2 contexts)

**Decision**:

`workflows/` owns 3 tables:
- `workflow_definitions` — named workflow, metadata, status
- `workflow_versions` — immutable YAML source + compiled IR (JSONB), JSON Schema version reference, change summary
- `workflow_trigger_definitions` — trigger type + config, linked to workflow_definition

`execution/` owns 7 tables:
- `executions` — execution instance, workflow_version reference, trigger reference, correlation context, status, lineage (parent_execution_id, rerun_of_execution_id)
- `execution_events` — append-only journal events (INSERT only, never UPDATE/DELETE)
- `execution_checkpoints` — state snapshot at a point in time, `last_event_sequence` reference
- `execution_dispatch_leases` — per-step lease record (mirrored from Redis for audit)
- `execution_task_plan_records` — task plan metadata; full payload in MinIO
- `execution_approval_waits` — approval gate record with decision
- `execution_compensation_records` — compensation outcome record

**Rationale**: 10 tables cleanly maps to the 14 spec entities. Redis handles ephemeral hot state (leases, scheduler priority queue). No cross-boundary DB access.

**Alternatives considered**:
- Store IR in MinIO only: rejected — IR needs to be queried for compatibility validation during hot change; JSONB in PostgreSQL is appropriate for structured ~50KB objects
- Combine events and checkpoints: rejected — different access patterns (events are append-only hot writes; checkpoints are occasional reads for resume)

---

## Decision 3 — Compiled IR Format

**Decision**: Store the compiled workflow IR as JSONB in `workflow_versions.compiled_ir`. IR is a typed Python dataclass hierarchy serialized to JSON: `WorkflowIR { schema_version, steps: [StepIR], data_bindings: [BindingIR], dag_edges: [EdgeIR], metadata }`. `StepIR` captures: step_id, step_type, agent_fqn, tool_fqn, retry_config, timeout_config, compensation_handler, approval_config, reasoning_mode, context_budget, parallel_group.

**Rationale**: IR must be queryable (hot change compatibility check) and reconstructable (replay). JSONB satisfies both without needing a separate serialization layer. IR size for typical workflows (50–200 steps) will be 5–100KB — well within PostgreSQL JSONB practical limits.

**Alternatives considered**:
- MinIO only for IR: rejected — requires async round-trip to MinIO for hot change check; JSONB is faster and transactional
- Separate normalized step tables: rejected — schema churn as IR evolves; immutable versioned JSONB is simpler and sufficient

---

## Decision 4 — YAML Parsing and Schema Validation

**Decision**: Use `PyYAML` to parse YAML source → `jsonschema` library for JSON Schema validation against versioned schemas stored as files at `apps/control-plane/src/platform/workflows/schemas/v{N}.json` → Pydantic models to deserialize the validated dict into typed `WorkflowIR`. The Pydantic compiler raises `PolicyCompilationError` (reused from common exceptions) with field-level errors on validation failure. Schema version is declared in the YAML header (`schema_version: 1`).

**Rationale**: PyYAML is the standard Python YAML library. jsonschema gives field-level error paths for the spec requirement (FR-002). Pydantic v2 handles type coercion and validation of the deserialized structure.

**Alternatives considered**:
- PyYAML + Pydantic only (no jsonschema): rejected — Pydantic doesn't produce YAML line-number errors; jsonschema gives path-level errors which we map to source locations
- Cerberus or voluptuous: rejected — jsonschema is more widely understood and the schema files can be published as documentation

---

## Decision 5 — Scheduler Implementation

**Decision**: `SchedulerService` in `execution/` bounded context runs in the `worker` runtime profile under APScheduler 3.x (`AsyncIOScheduler`). Every 1 second, `SchedulerService.tick()` is called: (1) query `execution_events` for executions in `queued` or `dispatched` state; (2) project runnable steps (DAG resolution via in-memory projection from checkpoint + recent events); (3) compute priority scores for all runnable steps; (4) acquire dispatch lease in Redis; (5) assemble context via in-process `ContextEngineeringService`; (6) allocate budget via gRPC `ReasoningEngineService`; (7) dispatch to gRPC `RuntimeControlService`; (8) write journal events.

In-memory priority queue: `asyncio.PriorityQueue` per scheduler worker. Rebuilt on startup from journal events for in-flight executions.

**Rationale**: APScheduler provides reliable async tick scheduling with missed-fire policies. Priority queue in memory is fast (sub-millisecond reordering). The scheduler is stateless across restarts — journal is the durable source of truth.

**Alternatives considered**:
- Celery/dramatiq for task queuing: rejected — too heavy; PostgreSQL SKIP LOCKED pattern considered but APScheduler + Redis lease is simpler and faster
- Go scheduler satellite service: rejected — §I requires staying in Python monolith; execution is already gRPC-heavy; adding another satellite increases ops complexity

---

## Decision 6 — Dispatch Lease: Redis + PostgreSQL Audit

**Decision**: Dispatch lease is held in Redis with TTL. Key: `exec:lease:{execution_id}:{step_id}`. TTL = dispatch timeout for that step (default 300s). Acquiring the lease uses a `SET NX PX ttl` command. The `execution_dispatch_leases` table records the lease for audit (acquired_at, released_at, expired_at). When the step completes/fails the runtime controller emits an event on `workflow.runtime` topic; the execution consumer releases the Redis lease and updates the audit record.

**Rationale**: Redis NX (set-if-not-exists) is the correct primitive for distributed locks. The audit table in PostgreSQL provides compliance trail. Redis key expiry naturally handles scheduler worker crashes.

**Alternatives considered**:
- PostgreSQL SELECT FOR UPDATE SKIP LOCKED: rejected — works for queue processing but not for the distributed multi-scheduler scenario; Redis TTL handles crash recovery more cleanly
- Redis only (no PostgreSQL audit): rejected — audit requirement from constitution §XII needs durable records

---

## Decision 7 — TaskPlanRecord Storage

**Decision**: `execution_task_plan_records` table stores: execution_id, step_id, selected_agent_fqn, selected_tool_fqn, rationale, parameter_provenance_summary (compact JSONB), rejected_alternatives_count, storage_key (MinIO path). Full plan payload (all considered agents, full alternatives list, complete provenance) stored in MinIO bucket `execution-task-plans` at path `{execution_id}/{step_id}/task-plan.json`. Written by `SchedulerService` BEFORE dispatch via `aioboto3`.

**Rationale**: Constitution §XII requires TaskPlanRecord persistence. Large plans (many considered agents) can be 10–50KB — MinIO is the right store. PostgreSQL metadata row enables fast API queries (list task plans for execution) without MinIO round-trips.

**Alternatives considered**:
- All in PostgreSQL JSONB: rejected — plan payloads can grow large (hundreds of considered agents); MinIO keeps PostgreSQL rows compact
- All in MinIO: rejected — too slow for API list queries; PostgreSQL metadata enables indexed queries by execution_id and step_id

---

## Decision 8 — Replay vs Resume vs Rerun Implementation

**Decision**:
- **Replay**: `ExecutionService.replay_execution(execution_id)` — queries all events ordered by sequence, builds in-memory `ExecutionState` by applying events via state machine. Returns the reconstructed state. No new events written. For large executions: use most recent checkpoint as base, then apply events after `checkpoint.last_event_sequence`.
- **Resume**: Creates a NEW `Execution` record with `status=queued`, `parent_execution_id=original_id`, `resumed_from_checkpoint_id=checkpoint_id`. Loads the checkpoint's `step_results` as pre-completed. Scheduler picks it up and dispatches remaining steps. Journal starts fresh for the new execution.
- **Rerun**: Creates a NEW `Execution` record with `rerun_of_execution_id=original_id`, new trigger context, fresh journal. Uses the same `workflow_version_id`.

**Rationale**: Replay is non-destructive (no new events). Resume and rerun both create new Execution rows to maintain clean lineage. This avoids journal mutation (constitution §V).

**Alternatives considered**:
- Resume by continuing the original execution's journal: rejected — violates §V append-only principle in spirit (state would diverge from original event sequence); new Execution with lineage link is cleaner

---

## Decision 9 — Hot Change Compatibility Algorithm

**Decision**: `WorkflowService.check_hot_change_compatibility(running_execution_id, new_version_id)`:
1. Load current execution state (via projection)
2. Get steps currently in `dispatched` or `waiting_for_approval` state → "active steps"
3. Load new IR from `new_version_id`
4. Compatibility checks: (a) none of the active step IDs are removed in the new IR; (b) data binding changes to active step outputs don't break downstream step inputs; (c) no type changes to parameters that active steps have already injected
5. If passes: update `execution.workflow_version_id` to new_version_id; scheduler picks up new IR for remaining steps; write `execution_events` entry of type `hot_changed` with old and new version IDs.

**Rationale**: Conservative compatibility rules prevent execution corruption. Only active (in-flight) steps are protected; completed steps can be freely changed in the new version.

**Alternatives considered**:
- Allow any change and re-dispatch all queued steps: rejected — could cause data loss if completed step output contracts change
- Require execution to pause before applying change: rejected — defeats the purpose of "hot" change

---

## Decision 10 — Triggers: Cron, Webhook, Event-Bus, Workspace-Goal

**Decision**:
- **Cron**: APScheduler `CronTrigger` with IANA timezone. Trigger definitions loaded at startup from `workflow_trigger_definitions` table. On create/update/delete via API: dynamically add/modify/remove from APScheduler scheduler.
- **Webhook**: `/api/v1/workflows/{workflow_id}/webhook/{trigger_id}` endpoint in `execution/router.py`. HMAC-SHA256 validation against `trigger.config.secret`. Creates execution on validation pass.
- **Orchestrator/Manual/API**: Direct call to `ExecutionService.create_execution()`. Trigger type recorded in the execution.
- **Event-bus**: Kafka consumer group in `execution/` subscribes to `connector.ingress` + `workspace.goal` topics. Consumer checks each event against all active event-bus triggers (topic + optional payload pattern filter). On match: creates execution.
- **Workspace-goal**: Same consumer, separate handler. Filters `workspace.goal` events by `goal_filter` (workspace_id, goal_type pattern). Creates execution with `correlation_context.goal_id` set.

**Rationale**: Cron via APScheduler avoids reinventing scheduling. Webhook endpoints are thin — validation only, no heavy processing. Event-bus triggers via Kafka consumer group maintains §III (no database polling). Workspace-goal is a first-class trigger type per §X.

**Alternatives considered**:
- Separate trigger service: rejected — over-engineering; APScheduler in worker profile handles cron reliably
- Redis pubsub for trigger dispatch: rejected — Kafka is already the event backbone per §III; don't add a second event system

---

## Decision 11 — Kafka Topics (New for This Feature)

**Decision**: Two new topics:
- `execution.events` (key: execution_id) — produced by execution bounded context; consumed by analytics, ws_hub (real-time execution status), audit, monitoring
- `workflow.triggers` (key: workflow_id) — produced by trigger handlers; consumed by execution service to create new executions (allows async trigger processing for event-bus and workspace-goal triggers)

Existing topic `workflow.runtime` is consumed by execution bounded context (runtime controller → execution for step completion events).

`execution.reprioritized` events are published on `execution.events` with event_type `execution.reprioritized`.

**Rationale**: `execution.events` mirrors the append-only journal as a Kafka stream for downstream consumers. `workflow.triggers` decouples trigger detection from execution creation (useful when trigger events burst). Both stay consistent with §III (Kafka for async coordination, not DB polling).

**Alternatives considered**:
- Inline trigger processing (no `workflow.triggers` topic): acceptable for low-volume triggers; `workflow.triggers` topic added for event-bus triggers that can burst (thousands of events in a short window)
- Separate topic per event type: rejected — `execution.events` with typed payloads is sufficient; consumers filter by event_type

---

## Decision 12 — Re-Prioritization Implementation

**Decision**: `SchedulerService` maintains an `asyncio.PriorityQueue[ScheduledStep]` per execution. Re-prioritization triggers are detected:
1. **SLA approach**: checked on every `tick()` — if `now > execution.sla_deadline * 0.8`, flag steps in that execution for re-prioritization
2. **Budget threshold**: on receiving `runtime.reasoning` Kafka event with `event_type=budget.threshold_breached` (emitted by Go reasoning engine)
3. **High-urgency step arrival**: when a new step is added to the queue with urgency > current queue head
4. **Resource constraint**: on receiving `fleet.health` Kafka event with status indicating member failure or throttling
5. **External event**: on receiving `interaction.attention` Kafka event targeting this execution

On trigger: drain queue, re-score all items via `PriorityScorer.compute(step, execution_context)`, re-insert, emit `execution.reprioritized` event on `execution.events`.

**Rationale**: In-memory priority queue provides O(n log n) reordering within a single scheduler worker. Kafka events are the trigger mechanism (per §III — no polling). Stateless on restart (rebuilt from journal).

**Alternatives considered**:
- PostgreSQL-based priority queue with SKIP LOCKED: rejected — not suitable for dynamic priority updates; can't efficiently re-rank without full table update
- Redis sorted set for priority queue: viable alternative; rejected for now because in-memory asyncio queue is simpler for single-worker scheduler; can migrate to Redis sorted set if multi-worker scheduler is needed

---

## Decision 13 — Approval Gate Implementation

**Decision**: When a step hits an approval gate: (1) write `waiting_for_approval` journal event; (2) create `execution_approval_waits` record; (3) send approval request via in-process `InteractionsService.create_approval_request()` which creates a conversation message with approval actions. When a user approves/rejects: interactions service calls `ExecutionService.record_approval_decision(execution_id, step_id, decision, approver_id)`; service writes `approved`/`rejected` journal event; scheduler resumes (or fails) the step. Timeout: APScheduler checks for overdue approval waits every minute; on timeout writes `approval_timed_out` event and applies the configured timeout action (fail/skip/escalate).

**Rationale**: Approval workflow uses existing `interactions/` bounded context for the human communication layer. No new messaging infrastructure needed. In-process call (not Kafka) for the approval decision since it's a synchronous update to execution state.

**Alternatives considered**:
- Email-based approvals (via connectors): out of scope for this feature; can be added via connector plugin framework
- Kafka-based approval response: rejected — creates a message round-trip for what is essentially a synchronous state mutation; in-process call is simpler

---

## Decision 14 — Execution State Projection Performance

**Decision**: `ExecutionProjector.project_state(execution_id, session)`:
1. Find most recent checkpoint (if any) with `last_event_sequence`
2. Load all events with `sequence > last_event_sequence` (or all events if no checkpoint)
3. Initialize state from checkpoint data (or empty state)
4. Apply events in sequence order via state machine transition function
5. Cache result in Redis: `exec:state:{execution_id}` TTL 30s (invalidated on new event)

For executions with >500 events: always checkpoint before querying (checkpoint created by scheduler after every 100 events).

**Rationale**: Prevents full-table scan of execution_events for long-running executions. 30s Redis cache avoids redundant projections when multiple readers query state simultaneously (scheduler, API, websocket). Checkpoint interval of 100 events keeps projection reads fast.

**Alternatives considered**:
- Materialized view in PostgreSQL: rejected — immutable journal cannot be updated; view would need to recompute on every read for recent events
- Separate `execution_current_state` mutable table: rejected — violates §V (append-only principle); state is always computed, never persisted as mutable state
