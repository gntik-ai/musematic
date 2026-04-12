# Feature Specification: Workflow Definition, Compilation, and Execution

**Feature Branch**: `029-workflow-execution-engine`
**Created**: 2026-04-12
**Status**: Draft
**Input**: User description: "Implement YAML workflow parser, JSON Schema validation, compiler (YAML to typed IR), append-only execution journal, scheduler with priority and reasoning budget awareness, dispatch via runtime infrastructure, replay/resume/rerun, safe hot change, and compensation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Workflow Definition and Compilation (Priority: P1)

A workflow developer authors a workflow as a YAML document describing steps, data flow between steps, retry/timeout behaviour, branching/parallel paths, compensation handlers, approval gates, reasoning mode hints, and context budget constraints. The system validates the YAML against a versioned schema, producing actionable error messages when validation fails. Upon successful validation the system compiles the YAML into a typed intermediate representation (IR) that preserves step identities, data bindings, and all configuration. Workflow definitions are versioned immutably — each update creates a new version while prior versions remain accessible.

**Why this priority**: Without a valid, compiled workflow nothing else in this feature can operate. The parser and compiler are the entry point for the entire execution pipeline.

**Independent Test**: Author a multi-step YAML workflow with branching, data bindings, and retry config. Submit it. Verify it is parsed, validated, compiled, and a version 1 is created. Update the rules, submit again — verify version 2 exists and version 1 is still retrievable unchanged. Submit deliberately invalid YAML — verify the response contains specific error locations.

**Acceptance Scenarios**:

1. **Given** a valid YAML workflow, **When** the developer submits it, **Then** the system validates it, compiles it to IR, and stores it as version 1 with a unique identifier.
2. **Given** an existing workflow at version N, **When** the developer updates the YAML and submits it, **Then** a new version N+1 is created; version N remains immutable and retrievable.
3. **Given** a YAML workflow with an undefined step reference, **When** the developer submits it, **Then** the system returns a validation error citing the undefined reference and its location.
4. **Given** a YAML workflow with circular step dependencies, **When** the developer submits it, **Then** the system rejects compilation with an error describing the cycle.

---

### User Story 2 — Execution Journal and State Projection (Priority: P1)

When a workflow begins execution every state change is recorded as an immutable, append-only event in the execution journal. Event types cover the full lifecycle: creation, queuing, dispatch, runtime start, sandbox requests, approval waits, resumption, retries, completion, failure, cancellation, compensation, reasoning trace emission, self-correction start/convergence, and context assembly. The current state of any execution is computed by projecting (replaying) its journal events in order — there is no mutable "current state" row.

**Why this priority**: The journal is the single source of truth for all execution state. Scheduling, dispatch, replay, resume, rerun, and compensation all depend on it.

**Independent Test**: Start a workflow execution. Observe journal events as the execution progresses through queued → dispatched → runtime_started → completed. Query the execution's current state — verify it matches the projected result of those events. Verify that no journal entry can be modified or deleted after creation.

**Acceptance Scenarios**:

1. **Given** a new execution, **When** the system creates it, **Then** a `created` event is appended to the journal with execution ID, workflow version reference, and timestamp.
2. **Given** a running execution, **When** a step transitions (e.g., dispatched → runtime_started), **Then** the corresponding event is appended to the journal.
3. **Given** an execution with 10 journal events, **When** a consumer queries the execution's current state, **Then** the state is computed by projecting those 10 events in order.
4. **Given** any existing journal entry, **When** an attempt is made to modify or delete it, **Then** the system rejects the operation.

---

### User Story 3 — Step Scheduling and Dispatch (Priority: P1)

The scheduler continuously identifies runnable steps from the execution DAG (all upstream dependencies satisfied, no active dispatch lease on the step). For each runnable step it computes priority using multiple dimensions: urgency, importance, risk, severity, due date, SLA, dependency position, and remaining reasoning budget. Before dispatching a step the scheduler obtains an exclusive dispatch lease (preventing duplicate execution), requests context assembly from the context engineering service, allocates a reasoning budget from the reasoning engine, and dispatches the step to the runtime controller for execution. Dispatch failures trigger configurable retry schedules.

**Why this priority**: Scheduling and dispatch are the execution engine's core loop — without them, compiled workflows cannot run.

**Independent Test**: Create a workflow with 3 sequential steps (A → B → C). Start execution. Verify step A is scheduled first (only runnable step). When A completes, verify B becomes runnable and is scheduled. Verify each dispatch includes a lease, context assembly, and reasoning budget allocation. Simulate dispatch failure — verify retry follows the configured schedule.

**Acceptance Scenarios**:

1. **Given** a workflow DAG with steps A → B → C, **When** execution starts, **Then** only step A is identified as runnable (B and C have unmet dependencies).
2. **Given** two runnable steps with different priorities, **When** the scheduler dispatches, **Then** the higher-priority step is dispatched first.
3. **Given** a runnable step, **When** the scheduler dispatches it, **Then** an exclusive dispatch lease is obtained before any dispatch call occurs.
4. **Given** a runnable step, **When** it is dispatched, **Then** context is assembled and quality-scored, a reasoning budget is allocated, and the step is sent to the runtime controller.
5. **Given** a dispatch failure, **When** the retry schedule permits, **Then** the step is re-queued for dispatch after the configured backoff interval.
6. **Given** a step with an active dispatch lease, **When** the same step is identified as runnable again, **Then** it is not scheduled for duplicate dispatch.

---

### User Story 4 — Replay, Resume, and Rerun (Priority: P2)

An operator can reconstruct the exact state of a past or current execution by replaying its journal events and associated reasoning traces — useful for debugging, auditing, and post-mortem analysis. A paused or failed execution can be resumed from its last successful checkpoint without re-executing completed steps. A completed execution can be rerun as a new execution (new ID) linked to the original via lineage, using the same workflow version.

**Why this priority**: Replay and resume are essential operational capabilities, but the platform can function for initial use cases without them.

**Independent Test**: Run a workflow to completion. Replay it — verify the reconstructed state matches the original. Run a workflow that fails at step 3 of 5. Resume it — verify steps 1–2 are not re-executed and step 3 retries from the checkpoint. Rerun a completed execution — verify a new execution ID is created with a lineage link to the original.

**Acceptance Scenarios**:

1. **Given** a completed execution, **When** an operator replays it, **Then** the reconstructed state matches the original execution state exactly, including reasoning traces.
2. **Given** a failed execution with a checkpoint after step 2, **When** the operator resumes it, **Then** execution continues from step 3 without re-running steps 1 and 2.
3. **Given** a completed execution, **When** the operator reruns it, **Then** a new execution is created with a distinct ID, linked to the original via a lineage reference, using the same workflow version.

---

### User Story 5 — Execution Triggers (Priority: P2)

Workflows can be triggered by seven mechanisms: (1) webhook — an external system sends a request to a dedicated endpoint; (2) cron — timezone-aware recurring schedule; (3) orchestrator — a fleet or parent workflow initiates execution; (4) manual — a human user starts execution through the UI or API; (5) API — direct programmatic invocation by an external system; (6) event-bus — a matching event appears on a subscribed topic; (7) workspace-goal — a new goal is posted or an existing goal is updated in a workspace (correlated via Goal ID). Each trigger type carries its own configuration (e.g., cron expression, webhook secret, topic pattern, goal filter).

**Why this priority**: Multiple trigger mechanisms are needed for production use but the core execution engine can operate with manual/API triggers alone for initial testing.

**Independent Test**: Configure a workflow with a cron trigger (e.g., every hour, UTC). Verify it fires at the expected time. Configure a webhook trigger — send a request and verify execution starts. Configure an event-bus trigger — emit a matching event and verify execution starts. Test timezone handling by configuring the same cron in two different timezones.

**Acceptance Scenarios**:

1. **Given** a workflow with a webhook trigger, **When** an external system sends a valid request to the trigger endpoint, **Then** a new execution starts with the webhook payload available as input.
2. **Given** a workflow with a cron trigger set to "every day at 09:00 Europe/Rome", **When** the clock reaches 09:00 in the Europe/Rome timezone, **Then** a new execution starts.
3. **Given** a workflow with an event-bus trigger matching pattern "orders.created", **When** an event with that type appears, **Then** a new execution starts with the event payload as input.
4. **Given** a workflow with a workspace-goal trigger, **When** a matching goal is posted in the workspace, **Then** a new execution starts with the Goal ID correlated.
5. **Given** a workflow with a manual trigger, **When** a user clicks "Run" in the UI, **Then** a new execution starts immediately.

---

### User Story 6 — Task Plan Recording (Priority: P2)

Before dispatching any execution step the system persists a TaskPlanRecord that captures the agent's planning decisions: which agents and tools were considered, which was selected and why, the provenance of every injected parameter, and which alternatives were rejected with reasons. The task plan is persisted BEFORE execution begins — it represents intent, not outcome. It is stored as metadata (small fields) in the primary database and as a full payload in object storage for large plans. Task plans are distinct from reasoning traces and are accessible via a dedicated read endpoint.

**Why this priority**: TaskPlanRecords are required by the trust framework (Layer 4 — Explainability) for every execution. While the platform can technically dispatch without them, compliance requires them before production.

**Independent Test**: Dispatch a step. Before the dispatch completes verify that a TaskPlanRecord exists with: considered agents (list of FQNs), considered tools, selected agent with rationale, parameter sources, and rejected alternatives. Retrieve the task plan via the API endpoint — verify it returns the full record. Verify it is distinct from the reasoning trace.

**Acceptance Scenarios**:

1. **Given** a step about to be dispatched, **When** the scheduler processes it, **Then** a TaskPlanRecord is persisted BEFORE the dispatch call is made.
2. **Given** a persisted TaskPlanRecord, **When** queried via the API, **Then** it returns the full record including considered agents, selected agent with rationale, and parameter provenance.
3. **Given** a completed execution step with both a TaskPlanRecord and a reasoning trace, **When** both are queried, **Then** they are stored separately and accessible via different endpoints.

---

### User Story 7 — Hot Change and Compensation (Priority: P3)

A platform operator can update a running workflow's definition (hot change) — the system validates compatibility before applying the change (e.g., no removal of in-progress steps, no breaking data binding changes to active paths). If the change is incompatible the system rejects it without disrupting the running execution. When a completed step needs to be undone (e.g., due to downstream failure or explicit rollback), the system invokes the step's compensation handler and records the outcome in the journal.

**Why this priority**: Hot change and compensation are advanced operational capabilities needed for production resilience but not for initial deployment.

**Independent Test**: Start a 5-step workflow. While step 2 is running update the workflow to add a step 6 — verify the change applies without interrupting the running execution. Attempt to remove step 2 (in-progress) — verify the change is rejected. Complete all steps. Trigger compensation for step 3 — verify the compensation handler runs and a `compensated` event is recorded.

**Acceptance Scenarios**:

1. **Given** a running execution at step 2 of 5, **When** an operator adds a new step 6 to the workflow, **Then** the change is applied and the execution continues; step 6 is included in remaining execution.
2. **Given** a running execution at step 2 of 5, **When** an operator removes step 2, **Then** the change is rejected with a compatibility error (cannot remove an in-progress step).
3. **Given** a completed step with a compensation handler, **When** compensation is triggered, **Then** the compensation handler executes and a `compensated` event is recorded in the journal.
4. **Given** a completed step without a compensation handler, **When** compensation is triggered, **Then** the system records a `compensation_not_available` outcome.

---

### User Story 8 — Dynamic Re-Prioritization (Priority: P3)

While an execution is in progress the scheduler dynamically re-evaluates and reorders queued (not yet dispatched) steps when certain triggers fire: a new high-urgency step arrives in the same execution, an SLA deadline approaches (configurable threshold), a resource constraint changes (e.g., fleet member failure, model provider throttling), a reasoning budget threshold is breached, or an external event occurs (attention request, goal update). Re-prioritization is lightweight — it reorders the dispatch queue without re-planning.

**Why this priority**: Dynamic re-prioritization is an optimization for production workloads with complex SLA and budget constraints — not needed for initial deployment.

**Independent Test**: Queue 5 steps with different priorities. Before any dispatches, simulate an SLA deadline approaching on the lowest-priority step. Verify that step is promoted in the queue. Verify a re-prioritization event is emitted with the trigger reason and affected steps.

**Acceptance Scenarios**:

1. **Given** 5 queued steps, **When** the SLA deadline for step E approaches 80% of time budget consumed, **Then** step E is re-prioritized to the front of the queue.
2. **Given** 5 queued steps, **When** reasoning budget reaches 90% consumed, **Then** all queued steps are re-evaluated and reordered by the priority algorithm.
3. **Given** a re-prioritization event, **When** queried, **Then** it includes execution ID, trigger reason, affected step IDs, and before/after priority values.
4. **Given** already-dispatched steps, **When** a re-prioritization trigger fires, **Then** only queued (not yet dispatched) steps are affected — dispatched steps continue unchanged.

---

### Edge Cases

- What happens when the scheduler has no runnable steps? (All steps are either dispatched, waiting for approval, or have unmet dependencies.) The scheduler idles and re-evaluates on the next journal event.
- What happens when a dispatch lease expires before the step completes? The step is treated as failed and eligible for retry per its retry schedule.
- What happens when a cron trigger fires while the previous execution of the same workflow is still running? A new execution starts independently unless a concurrency limit is configured on the trigger.
- What happens when a hot change adds a step that depends on an already-completed step? The new step is immediately runnable (dependency already satisfied).
- What happens when compensation fails? The failure is recorded as a `compensation_failed` event in the journal and the operator is notified via the attention channel.
- What happens when the execution journal store is temporarily unavailable? No state changes can be recorded — all in-flight dispatches are paused until the journal is available again (no state changes lost).
- What happens when a step's approval wait times out? The step transitions to `approval_timed_out` and follows the configured timeout action (fail, skip, or escalate).
- What happens when a workflow has no steps? Compilation rejects it with a validation error ("workflow must have at least one step").

## Requirements *(mandatory)*

### Functional Requirements

**Parser and Compiler**

- **FR-001**: System MUST parse YAML workflow definitions and validate them against a versioned schema
- **FR-002**: System MUST produce validation errors that include the specific location (line and path) of each error in the YAML source
- **FR-003**: System MUST compile validated YAML into a typed intermediate representation (IR) that preserves step identities, data bindings, retry/timeout configuration, branching, parallel execution paths, compensation handlers, approval gates, reasoning mode hints, and context budget constraints
- **FR-004**: System MUST version workflow definitions immutably — each update creates a new version while prior versions remain accessible and unchanged
- **FR-005**: System MUST reject compilation when the YAML references undefined steps, contains circular step dependencies, or has invalid data bindings
- **FR-006**: System MUST support listing, retrieving, and comparing workflow versions

**Execution Journal**

- **FR-007**: System MUST record all execution state changes as append-only events (no modification or deletion of journal entries)
- **FR-008**: System MUST support event types: created, queued, dispatched, runtime_started, sandbox_requested, waiting_for_approval, resumed, retried, completed, failed, canceled, compensated, reasoning_trace_emitted, self_correction_started, self_correction_converged, context_assembled
- **FR-009**: System MUST compute current execution state by projecting journal events in timestamp order
- **FR-010**: Each journal event MUST include timestamp, execution ID, step ID (where applicable), event type, correlation context (workspace ID, conversation ID, interaction ID, fleet ID, Goal ID), and event-specific payload

**Scheduling and Dispatch**

- **FR-011**: System MUST identify runnable steps from the execution DAG (all upstream dependencies satisfied, no active dispatch lease)
- **FR-012**: System MUST compute dispatch priority using: urgency, importance, risk, severity, due date, SLA, dependency position, and remaining reasoning budget
- **FR-013**: System MUST obtain an exclusive dispatch lease for each step before dispatch to prevent duplicate execution
- **FR-014**: System MUST request context assembly and quality scoring from the context engineering service before dispatch
- **FR-015**: System MUST allocate a reasoning budget from the reasoning engine before dispatch
- **FR-016**: System MUST dispatch the step to the runtime controller for execution after lease, context, and budget are secured
- **FR-017**: System MUST handle dispatch failures with configurable retry schedules (max retries, backoff strategy, max backoff interval)
- **FR-018**: System MUST handle dispatch lease expiration — expired leases release the step for rescheduling

**Replay, Resume, and Rerun**

- **FR-019**: System MUST reconstruct the exact state of any execution by replaying its journal events and reasoning traces
- **FR-020**: System MUST resume a paused or failed execution from its last successful checkpoint without re-executing completed steps
- **FR-021**: System MUST create checkpoints at configurable intervals capturing the execution state at that point (completed steps, in-progress data, remaining steps)
- **FR-022**: System MUST support rerun — creating a new execution with a new ID linked to the original via lineage, using the same workflow version

**Triggers**

- **FR-023**: System MUST support webhook triggers with configurable endpoint path and payload validation
- **FR-024**: System MUST support cron triggers with timezone-aware scheduling (IANA timezone identifiers)
- **FR-025**: System MUST support orchestrator triggers (invoked by fleet coordination or parent workflow)
- **FR-026**: System MUST support manual triggers (user-initiated)
- **FR-027**: System MUST support API triggers (direct programmatic invocation)
- **FR-028**: System MUST support event-bus triggers (topic pattern matching against incoming events)
- **FR-029**: System MUST support workspace-goal triggers (new goal posted or goal updated, correlated via Goal ID)
- **FR-030**: Each trigger type MUST carry its own configuration (cron expression, webhook secret, topic pattern, goal filter, etc.)

**Task Plan Recording**

- **FR-031**: System MUST persist a TaskPlanRecord before dispatching every execution step
- **FR-032**: TaskPlanRecord MUST include: execution ID, step ID, considered agents (FQN list), considered tools, selected agent (FQN + rationale), selected tool (if applicable), parameters with provenance, rejected alternatives with reasons, creation timestamp
- **FR-033**: System MUST store task plan metadata in the primary record store and full plan payload in object storage for large plans
- **FR-034**: System MUST provide a read endpoint for retrieving task plans associated with an execution

**Hot Change and Compensation**

- **FR-035**: System MUST validate compatibility before applying a workflow definition change to a running execution (no removal of in-progress steps, no breaking data binding changes to active paths)
- **FR-036**: System MUST reject incompatible hot changes without disrupting the running execution
- **FR-037**: System MUST execute compensation handlers for completed steps when compensation is triggered
- **FR-038**: System MUST record compensation outcomes in the journal as `compensated` or `compensation_failed` events

**Dynamic Re-Prioritization**

- **FR-039**: System MUST re-evaluate priority for all queued (not yet dispatched) steps when a re-prioritization trigger fires
- **FR-040**: System MUST support re-prioritization triggers: high-urgency step arrival, SLA deadline approach (configurable threshold), resource constraint change, reasoning budget threshold breach, external event (attention request, goal update)
- **FR-041**: System MUST emit a re-prioritization event with execution ID, trigger reason, affected step IDs, and priority changes

**Approval and Concurrency**

- **FR-042**: System MUST support approval gates that pause execution until a human approves or rejects the step
- **FR-043**: System MUST record approval decisions in the journal with approver identity, decision, and timestamp
- **FR-044**: System MUST support configurable concurrency limits per trigger (max concurrent executions of the same workflow)

### Key Entities

- **WorkflowDefinition**: A named, reusable workflow with metadata (name, description, owner, status). Parent of all versions.
- **WorkflowVersion**: An immutable snapshot of a specific workflow revision — contains the raw YAML source, the compiled IR, version number, schema version reference, and change summary.
- **CompiledWorkflowIR**: The typed intermediate representation of a workflow — step graph (DAG), data bindings between steps, per-step configuration (retry, timeout, compensation, approval, reasoning mode, context budget), and structural metadata.
- **TriggerDefinition**: Configuration for how a workflow can be triggered. Linked to a workflow. Includes trigger type (webhook/cron/orchestrator/manual/API/event-bus/workspace-goal) and type-specific config.
- **Execution**: A single run instance of a workflow version. Carries workflow version reference, trigger reference, input parameters, correlation context (workspace, conversation, interaction, fleet, Goal ID), status (derived from journal), and lineage reference (for reruns).
- **ExecutionEvent**: An immutable journal entry recording a state change during execution. Carries timestamp, execution ID, step ID, event type, correlation context, and type-specific payload. Never modified or deleted.
- **Checkpoint**: A snapshot of execution state at a point in time. Captures completed steps, in-progress data, and remaining step graph for resume capability.
- **DispatchLease**: An exclusive, time-limited lock on a step preventing duplicate dispatch. Carries step ID, execution ID, lease holder, acquired time, and expiration time.
- **RetrySchedule**: Per-step configuration for failure recovery — max retries, backoff strategy (fixed/exponential/linear), max backoff interval, retry-eligible error categories.
- **ApprovalWait**: A record of a step paused pending human approval — carries step ID, execution ID, required approvers, timeout, and timeout action (fail/skip/escalate).
- **CompensationRecord**: A record of a compensation (undo) operation for a completed step — carries step ID, execution ID, compensation handler reference, outcome, and timestamp.
- **TaskPlanRecord**: An audit record of planning decisions made before dispatch — considered agents and tools, selected agent with rationale, parameter provenance, rejected alternatives with reasons. Metadata in primary store, full payload in object storage.
- **ReasoningTraceRef**: A reference linking an execution step to its reasoning trace (chain-of-thought, tree-of-thought branches) stored in the reasoning engine. Distinct from TaskPlanRecord.
- **SelfCorrectionIterationRef**: A reference linking an execution step to its self-correction iteration data (convergence metrics, iteration count, correction history).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Valid workflow definitions compile to an executable intermediate representation within 2 seconds
- **SC-002**: Invalid workflow definitions produce actionable error messages identifying the specific location and nature of each error
- **SC-003**: Any execution's current state can be reconstructed from its journal events within 5 seconds regardless of execution duration or event count
- **SC-004**: No execution journal entry is modified or deleted after creation — 100% immutability enforcement
- **SC-005**: Higher-priority steps are always dispatched before lower-priority steps when both are runnable simultaneously
- **SC-006**: No step is ever dispatched without an active dispatch lease — 0% duplicate dispatch rate
- **SC-007**: Replayed execution state matches the original execution state exactly, including all intermediate states
- **SC-008**: Resumed execution continues from the last checkpoint without re-executing completed steps — 0% redundant step execution
- **SC-009**: Rerun execution creates a new record linked to the original via lineage, with independent journal events
- **SC-010**: Hot change compatibility validation rejects incompatible changes without disrupting running execution — 0% execution interruption from rejected changes
- **SC-011**: Compensation outcomes are recorded for every triggered undo operation
- **SC-012**: Every dispatched step has a TaskPlanRecord persisted before the dispatch call is made — 100% compliance
- **SC-013**: Re-prioritization reorders queued steps within 500 milliseconds of trigger event
- **SC-014**: Test coverage of at least 95% across all workflow definition and execution components
- **SC-015**: All 7 trigger types can successfully initiate workflow execution

## Assumptions

- Workflow authors write YAML using a well-documented schema; YAML is the sole workflow definition format (no visual builder in this feature's scope)
- The context engineering service, reasoning engine, and runtime controller are available as in-process or remote services — this feature consumes them but does not implement them
- The trust framework's requirement for TaskPlanRecords applies to all dispatched steps regardless of workflow complexity
- Cron scheduling uses IANA timezone identifiers (e.g., "America/New_York", "Europe/Rome")
- Webhook triggers require pre-shared secrets for request validation; secret management is delegated to the existing secrets infrastructure
- Concurrency limits default to "unlimited" when not explicitly configured on a trigger
- Object storage for large task plan payloads and checkpoints is available via the existing S3-compatible interface
- The attention channel (for compensation failure notifications) is available from the interactions bounded context
- Event-bus triggers match on event type patterns, not on event payload content
- Approval gates timeout after a configurable period (default: 24 hours) with a configurable timeout action
