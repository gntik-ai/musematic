# Feature Specification: Dynamic Re-Prioritization and Checkpoint/Rollback

**Feature Branch**: `063-reprioritization-and-checkpoints`  
**Created**: 2026-04-19  
**Status**: Draft  
**Input**: Brownfield extension. Adds dynamic re-prioritization to the execution scheduler — rule-based triggers (e.g., SLA approach, priority change, budget approach) that reorder the pending dispatch queue mid-flight. Adds execution checkpoints with configurable capture policies (default: before external tool invocation) that snapshot complete runtime state (completed steps, current context, accumulated costs, pending queue). Adds a rollback capability that restores an execution to a prior checkpoint, allowing operators to recover from faults or exploratory branches without re-running from scratch.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Scheduler re-prioritizes the pending queue when a trigger fires (Priority: P1)

A platform operator defines a re-prioritization trigger — for example, "when an execution's time-to-SLA-deadline is less than 15% of its allotted window, promote it to the front of the dispatch queue." The scheduler evaluates active triggers on each dispatch cycle. When a trigger matches one or more pending executions, the scheduler reorders the pending queue to reflect the new priority ranking and emits a reprioritization event that records the triggering rule, the affected executions, and the resulting order. Operators observing the dashboard see the promoted executions move up in the queue in near-real-time.

**Why this priority**: Without dynamic re-prioritization, the scheduler is static — executions are dispatched in the order they arrived or with a fixed priority set at submission time. That model cannot respond to changing conditions like SLA pressure, budget exhaustion, or externally-signaled urgency. P1 because SLA-sensitive workloads are a hard requirement for enterprise adoption, and the base capability (trigger evaluation + queue reorder + event emission) is the foundation that every other re-prioritization scenario builds upon.

**Independent Test**: Configure a single trigger "SLA approach < 20% remaining → promote to front." Enqueue three executions: A with 10% SLA remaining, B with 50%, C with 80% (all three entered the queue at the same priority). Verify the scheduler dispatches A first, emits a `execution.reprioritized` event referencing the SLA-approach trigger, and the event payload lists the new queue order [A, B, C]. Remove the trigger. Enqueue the same mix. Verify the scheduler returns to default ordering with no reprioritization event.

**Acceptance Scenarios**:

1. **Given** a configured SLA-approach trigger at threshold 15%, **When** a pending execution's remaining SLA falls below 15% during a dispatch cycle, **Then** the scheduler promotes that execution to the front of the pending queue and emits `execution.reprioritized` with the trigger identifier, the execution identifier, and the new queue position.
2. **Given** multiple pending executions and a trigger firing on the same cycle for two of them, **When** the scheduler reorders the queue, **Then** the final order is deterministic (tie-broken by deadline proximity) and a single `execution.reprioritized` event records all promotions in one envelope.
3. **Given** a re-prioritization event was emitted for execution X on cycle N, **When** the trigger re-evaluates on cycle N+1 with identical conditions, **Then** no duplicate event is emitted (idempotent — reprioritization is not re-announced until the queue position actually changes again).
4. **Given** a trigger defined for a condition that no pending execution matches, **When** a dispatch cycle runs, **Then** the queue is unchanged and no reprioritization event is emitted.
5. **Given** a trigger configuration that is syntactically or semantically invalid, **When** the trigger is saved, **Then** the configuration is rejected at save time with a clear validation error identifying the problem.

---

### User Story 2 — Execution captures a checkpoint before invoking an external tool (Priority: P1)

A workflow execution is running and reaches a step that invokes an external tool. Before the tool call is dispatched, the platform captures a checkpoint — a complete snapshot of the execution's runtime state: the list of completed steps, the current working context, the accumulated cost accounting, and the remaining pending queue of steps. The checkpoint is persisted, tagged with the execution identifier and a monotonically increasing checkpoint number, and is retrievable for later inspection or rollback. After the checkpoint is captured, the tool call proceeds. If the tool call later fails catastrophically or produces unexpected results, the operator has a clean restore point without needing to re-run the workflow from scratch.

**Why this priority**: External tool calls are the primary source of non-determinism, cost, and failure in agentic workflows. Without a pre-invocation checkpoint, recovering from a bad tool result requires re-running everything from the start, which is expensive and often impossible for stateful tools. The default "checkpoint before tool invocation" policy is the minimum viable recovery guarantee. P1 because checkpointing must exist before rollback is useful (US3), and the default policy is what every execution gets without explicit configuration.

**Independent Test**: Submit a workflow execution whose step 3 invokes an external tool. Observe the execution complete steps 1 and 2 successfully. Before step 3 dispatches, verify a checkpoint record is created with `execution_id=X, checkpoint_number=1, completed_steps=[1,2], pending_queue=[3,4,5]`, and the `state_snapshot`, `current_context`, and `accumulated_costs` fields are non-null. Verify the tool call then proceeds. Fetch the list of checkpoints for execution X: the single checkpoint must appear.

**Acceptance Scenarios**:

1. **Given** an execution with default checkpoint policy and step N that invokes an external tool, **When** step N is about to dispatch, **Then** a checkpoint record is created with the complete execution state (completed_steps, current_context, accumulated_costs, pending_queue, state_snapshot), and the tool invocation proceeds after persistence is confirmed.
2. **Given** an execution with no external tool invocations, **When** the execution runs end-to-end, **Then** no checkpoints are created under the default policy (nothing triggered the capture).
3. **Given** multiple tool invocations across steps 3, 7, and 9 of one execution, **When** the execution completes, **Then** three checkpoints exist for that execution numbered 1, 2, 3 in invocation order.
4. **Given** a checkpoint capture fails (storage unavailable), **When** the tool invocation is about to proceed, **Then** the execution pauses with a recoverable error rather than dispatching the tool call without checkpoint coverage.
5. **Given** a completed execution, **When** an operator lists its checkpoints, **Then** the complete list is returned in checkpoint-number order with each record's creation timestamp and a summary of the captured state.

---

### User Story 3 — Operator rolls an execution back to a prior checkpoint (Priority: P2)

An operator is notified that execution X produced an incorrect result — an external tool returned corrupted data that cascaded into bad downstream decisions. The operator selects an earlier checkpoint (e.g., checkpoint number 2, taken before the problematic tool call) and issues a rollback request. The platform validates the rollback is permitted (execution is in a rollback-eligible state, checkpoint belongs to the execution, caller has permission), restores the execution's runtime state from the checkpoint (completed_steps, current_context, accumulated_costs, pending_queue), transitions the execution to a "rolled back" state referencing the checkpoint number, and emits an `execution.rolled_back` audit event. The execution can then be resumed from the restored state — allowing the operator to re-dispatch the problematic tool call (perhaps with an adjusted parameter) without losing the work already completed.

**Why this priority**: Rollback turns checkpoints from passive debugging artifacts into an active recovery mechanism. Without rollback, operators facing a failed execution must either accept the bad result, manually reconstruct state, or re-run the full execution. P2 because the checkpoint capability (US2) must exist before rollback is useful, and rollback is the corrective action that gives checkpointing its return-on-investment.

**Independent Test**: Run execution X through checkpoints 1, 2, and 3, completing all steps. Issue rollback to checkpoint 2. Verify the execution's state matches checkpoint 2: `completed_steps=[1,2,3]` (steps captured at ckpt 2), `pending_queue` restored to the ckpt-2 state, `current_context` equals ckpt-2 context, `accumulated_costs` equals ckpt-2 costs. Verify an `execution.rolled_back` event was emitted referencing `execution_id=X, checkpoint_number=2`. Verify the execution is in a state that allows resumption.

**Acceptance Scenarios**:

1. **Given** a completed execution with three checkpoints, **When** an authorized operator issues rollback to checkpoint 2, **Then** the execution's completed_steps, current_context, accumulated_costs, and pending_queue are restored to the values captured at checkpoint 2; the execution transitions to "rolled_back"; and an `execution.rolled_back` event is emitted.
2. **Given** a rollback to checkpoint N, **When** the rollback succeeds, **Then** checkpoints numbered greater than N are marked as superseded (not deleted — retained for audit) and are excluded from future rollback choices by default.
3. **Given** an active in-flight execution (not yet terminal), **When** rollback is requested, **Then** the rollback is rejected with an error indicating the execution must first be paused or terminated before rollback.
4. **Given** a rollback target checkpoint that does not belong to the specified execution, **When** rollback is requested, **Then** the rollback is rejected with a not-found or mismatch error.
5. **Given** a rollback request from a caller without the rollback permission, **When** the request is received, **Then** the request is denied with an authorization error and no state is modified.
6. **Given** a successfully rolled-back execution, **When** the operator resumes it, **Then** the scheduler dispatches the restored pending queue starting from the restored step sequence — side-effects from the superseded later checkpoints are NOT replayed automatically; the operator decides whether to modify inputs before resumption.

---

### User Story 4 — Admin configures custom checkpoint policies per workflow (Priority: P2)

The default policy ("checkpoint before tool invocation") is a reasonable baseline, but different workflows have different needs. A long-running research workflow may want checkpoints before every step. A cheap deterministic workflow may want no checkpoints at all. A workflow with expensive middle-of-pipeline reasoning may want checkpoints only at specific named steps. A workflow admin configures a per-workflow checkpoint policy that overrides the default: policy options include "before every step", "before tool invocations only", "at named step IDs [s1, s5, s8]", or "disabled". The scheduler/executor honours the policy on every execution of that workflow.

**Why this priority**: The default policy trades safety for cost — every tool call incurs a checkpoint write. Some workflows need more (debugging-intensive or high-value pipelines), some need less (high-throughput fire-and-forget). Without policy configurability, admins are stuck with the default. P2 because the default covers the essential case; custom policies are a refinement.

**Independent Test**: Create workflow W1 with policy "before every step". Run an execution with 5 steps. Verify 5 checkpoints are created (one before each step's dispatch). Create workflow W2 with policy "disabled". Run an execution. Verify zero checkpoints are created. Create workflow W3 with policy "at named step IDs [s3, s5]". Run an execution with steps s1..s7. Verify exactly two checkpoints are created (before s3 and before s5).

**Acceptance Scenarios**:

1. **Given** a workflow with policy "before every step", **When** the execution runs, **Then** a checkpoint is captured before each step dispatches (not counting retries of the same step).
2. **Given** a workflow with policy "disabled", **When** the execution runs including tool calls, **Then** zero checkpoints are created.
3. **Given** a workflow with policy "at named step IDs [s3, s5]", **When** the execution runs all steps, **Then** checkpoints are captured only at the named steps regardless of whether those steps are tool calls.
4. **Given** an invalid policy configuration (e.g., named step IDs that do not exist in the workflow), **When** the policy is saved, **Then** the save is rejected with a validation error naming the missing step IDs.
5. **Given** an execution in progress, **When** the workflow's policy is changed, **Then** the in-flight execution continues under the policy that was in force when it started (policy is snapshotted at execution start).

---

### User Story 5 — Operator lists checkpoints for an execution (Priority: P3)

A compliance or support operator needs to investigate an execution. They query the execution's checkpoint list and receive a time-ordered list of checkpoints with their numbers, creation timestamps, the captured step boundaries, and summary metadata about each checkpoint (e.g., accumulated_cost at that point). From this list they can pick a target for rollback (US3), inspect the state trajectory, or verify the checkpoint policy was applied correctly.

**Why this priority**: Without the ability to list checkpoints, operators cannot pick a rollback target or audit capture behavior. P3 because rollback (US3) can be implemented with the operator passing the checkpoint number from out-of-band knowledge; the list is an observability enhancement rather than a functional prerequisite.

**Independent Test**: Run an execution that captures five checkpoints. Query the checkpoint list for the execution. Verify the response is a sorted list of five entries with unique ascending checkpoint numbers, valid creation timestamps, and summary fields populated (at minimum: checkpoint_number, created_at, completed_step_count, accumulated_cost_summary).

**Acceptance Scenarios**:

1. **Given** an execution with N checkpoints, **When** an authorized user queries the checkpoint list, **Then** the response contains N entries in ascending checkpoint_number order, each with creation timestamp and summary fields.
2. **Given** an execution with no checkpoints (e.g., workflow had "disabled" policy), **When** the checkpoint list is queried, **Then** an empty list is returned, not a 404.
3. **Given** a query by a user without permission to view the execution, **When** the checkpoint list request is made, **Then** the request is denied with an authorization error.

---

### Edge Cases

- **Trigger evaluation takes longer than a dispatch cycle**: Trigger evaluation is time-bounded; if evaluation does not complete within its budget, the dispatch proceeds with the pre-evaluation queue order and a missed-evaluation warning is logged.
- **Two triggers both fire on the same execution with contradictory priorities**: Triggers are ranked by configured priority; the highest-priority trigger's action is applied; the other trigger's firing is recorded for audit but its priority-change is not applied.
- **Checkpoint captured but the tool call never dispatches (orphan checkpoint)**: Orphan checkpoints remain retrievable for audit; a scheduled cleanup process removes orphans older than a retention window.
- **Rollback to a checkpoint for an execution that is currently dispatching a step**: Rollback is rejected until the execution is paused or completed; the API returns 409 with a reason.
- **Rollback after checkpoint N with subsequent checkpoints N+1, N+2**: Later checkpoints are marked superseded but retained; rollback is still possible to N-1 or earlier via subsequent rollback requests.
- **Cost accounting during rollback**: `accumulated_costs` is restored to the checkpoint-captured value; downstream cost reports reflect the pre-rollback spend at the checkpoint and the post-rollback new spend separately — the rollback itself records the delta as a "reversed" cost entry for auditability (but does not refund; external spend is not reversible).
- **External side-effects between checkpoint and rollback**: The system cannot undo external API calls made after the checkpoint; the rollback restores only internal state; operators are warned that external effects persist and must be manually reconciled.
- **Re-prioritization trigger configured at global scope conflicting with per-workspace trigger**: Per-workspace triggers are evaluated after global triggers; a per-workspace promotion can override a global demotion for its scope.
- **Checkpoint state_snapshot grows beyond size limit**: A per-checkpoint size limit (configurable, default 10 MB) is enforced; exceeding it fails the checkpoint capture with a clear error, optionally offloading large components to object storage with pointer references.
- **Execution was rolled back; new checkpoint numbering**: New checkpoints after rollback continue the sequence (e.g., after rollback from 5 to 2, next captured checkpoint is 6, not 3), preserving the audit trail.
- **Reprioritization event consumer downstream is slow**: Event emission is best-effort from the scheduler's perspective; if the event bus is full, the reprioritization still happens (queue is reordered) and a warning is logged, so scheduling correctness is not blocked by observability.
- **Rollback target checkpoint has already been garbage-collected by retention**: Rollback is rejected with a retention-expired error; retention windows are configurable so admins can lengthen them if needed.
- **A rollback itself fails mid-operation**: The execution transitions to a "rollback_failed" quarantine state — it is NOT silently rolled partway back; an operator must manually resolve before any further rollback or resumption.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST support defining re-prioritization triggers with a condition (e.g., SLA threshold, budget threshold, priority change signal) and an action (promote to front, demote, explicit reorder rule).
- **FR-002**: The scheduler MUST evaluate configured triggers on each dispatch cycle and reorder the pending queue when a trigger matches; the reorder MUST be deterministic given equal trigger priorities (tie-break by deadline proximity, then by enqueue order).
- **FR-003**: The scheduler MUST emit an `execution.reprioritized` event whenever a trigger causes a queue change; the event MUST identify the triggering rule, the affected execution(s), and the new queue position(s).
- **FR-004**: Re-prioritization events MUST be idempotent: the same trigger evaluating identically on consecutive cycles MUST NOT emit duplicate events unless the queue position actually changes again.
- **FR-005**: The platform MUST support an SLA-approach trigger type with a configurable threshold expressed as a fraction of remaining SLA time (e.g., 15% → promote).
- **FR-006**: Trigger configurations MUST be validated at save time for syntactic correctness and semantic sanity (e.g., thresholds within valid range, referenced workflows/workspaces exist); invalid configurations MUST be rejected with a clear error.
- **FR-007**: The platform MUST capture an execution checkpoint that records the complete runtime state: completed steps, current context, accumulated costs, pending queue of steps, and a state snapshot sufficient to deterministically restore execution.
- **FR-008**: Each checkpoint MUST be identified by the execution identifier and a monotonically increasing checkpoint number unique per execution.
- **FR-009**: The default checkpoint policy MUST capture a checkpoint before every external tool invocation; tool invocation MUST proceed only after the checkpoint is persisted.
- **FR-010**: The platform MUST support per-workflow checkpoint policies that override the default: "before every step", "before tool invocations only", "at named step IDs [...]", or "disabled".
- **FR-011**: Per-workflow checkpoint policies MUST be validated at save time (e.g., named step IDs must exist in the referenced workflow); invalid policies MUST be rejected with a clear error.
- **FR-012**: Checkpoint policy MUST be snapshotted at execution start; a mid-flight policy change MUST NOT affect in-flight executions.
- **FR-013**: Checkpoint capture failures (e.g., storage unavailable) MUST pause the execution with a recoverable error rather than dispatching the action the checkpoint was meant to cover.
- **FR-014**: The platform MUST support listing all checkpoints for a given execution in ascending checkpoint-number order, each with creation timestamp and summary fields.
- **FR-015**: The platform MUST support rollback of an execution to a specific prior checkpoint; rollback MUST restore completed_steps, current_context, accumulated_costs, and pending_queue from the captured snapshot.
- **FR-016**: Rollback MUST be permitted only on executions that are in a rollback-eligible state (paused, terminated, or awaiting human input); rollback of an actively-dispatching execution MUST be rejected with a 409-equivalent error.
- **FR-017**: Rollback MUST validate that the target checkpoint belongs to the specified execution; mismatches MUST be rejected with an error.
- **FR-018**: Rollback MUST require explicit rollback permission; callers without the permission MUST be denied.
- **FR-019**: On successful rollback, the platform MUST emit an `execution.rolled_back` event identifying the execution, the target checkpoint number, and the actor who initiated the rollback.
- **FR-020**: Checkpoints superseded by a rollback MUST be retained (not deleted) and marked as superseded for audit purposes; superseded checkpoints MUST be excluded from default rollback-target listings but remain accessible via explicit audit queries.
- **FR-021**: Rolled-back executions MUST be resumable; resumption MUST dispatch the restored pending queue starting from the restored step sequence.
- **FR-022**: The platform MUST enforce a configurable per-checkpoint size limit (default 10 MB); captures exceeding the limit MUST fail with a clear error.
- **FR-023**: Checkpoint records MUST be retained for a configurable window; records older than the window MUST be removed by a scheduled garbage-collection process; rollback to a retention-expired checkpoint MUST be rejected with a clear error.
- **FR-024**: Rollback MUST record a compensating cost-audit entry that captures the cost-delta reversed (the accumulated_costs difference between post-rollback state and pre-rollback state) for downstream cost-reporting integrity; external spend is NOT automatically refunded.
- **FR-025**: Re-prioritization trigger evaluation MUST be time-bounded per dispatch cycle; if evaluation exceeds its budget, the dispatch proceeds with the pre-evaluation order and a missed-evaluation warning MUST be logged.
- **FR-026**: When multiple triggers match an execution with contradictory actions, the highest-priority trigger's action MUST be applied; the others MUST be recorded in audit but not applied.
- **FR-027**: Orphan checkpoints (captured but the subsequent dispatch never occurred) MUST be identifiable as orphans and subject to the same retention/garbage-collection as other checkpoints.
- **FR-028**: A failed rollback (e.g., storage read error mid-restore) MUST NOT leave the execution in a partially-restored state; the execution MUST transition to a `rollback_failed` quarantine state requiring manual operator resolution.
- **FR-029**: The platform MUST preserve backward compatibility: existing workflows without an explicit checkpoint policy MUST receive the default "before tool invocations only" policy; existing executions started before the feature deploys MUST continue to run without checkpoints and without error.
- **FR-030**: Re-prioritization triggers and checkpoint policies MUST be scoped to their owning workspace; cross-workspace configuration access MUST be denied.

### Key Entities

- **Re-Prioritization Trigger**: A configured rule consisting of a condition expression (e.g., "SLA remaining < 15%"), an action (promote/demote/reorder), a priority rank (for tie-breaking against other triggers), and a scope (global or workspace). Evaluated by the scheduler on each dispatch cycle.
- **Re-Prioritization Event**: Audit record emitted when a trigger causes a queue change. Carries the trigger identifier, the affected execution(s), the old and new queue positions, and the evaluation timestamp.
- **Execution Checkpoint**: Snapshot of an execution's runtime state at a specific dispatch boundary. Carries execution identifier, a per-execution monotonic checkpoint number, a state snapshot, the completed steps, the current context, the accumulated costs, the remaining pending queue, a creation timestamp, and a "superseded" flag set by later rollbacks.
- **Checkpoint Policy**: Configuration describing when checkpoints are captured for executions of a given workflow. One of: "before every step", "before tool invocations only" (default), "at named step IDs [...]", or "disabled". Snapshotted at execution start.
- **Rollback Action**: Record created when an operator restores an execution to a prior checkpoint. Carries the target checkpoint reference, the actor identifier, the timestamp, the cost-delta reversed, and the resulting execution state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When an SLA-approach trigger is configured with a 15% threshold, 100% of pending executions whose remaining SLA drops below 15% are promoted to the front of the pending queue within one dispatch cycle.
- **SC-002**: 100% of trigger-induced queue reorders emit an `execution.reprioritized` event with the trigger identifier, affected executions, and new queue positions.
- **SC-003**: Under the default checkpoint policy, 100% of external tool invocations are preceded by a persisted checkpoint that captures the pre-invocation state.
- **SC-004**: 100% of checkpoint records contain non-null state_snapshot, completed_steps, current_context, accumulated_costs, and pending_queue fields.
- **SC-005**: Checkpoint capture adds no more than 500 ms of latency at p95 before the subsequent dispatch action.
- **SC-006**: 100% of rollback requests for eligible executions and valid checkpoints complete within 3 seconds at p95; the restored state exactly matches the captured checkpoint state (deterministic restore).
- **SC-007**: 100% of rollback attempts on ineligible executions (actively dispatching) are rejected with a 409-equivalent error and no state is modified.
- **SC-008**: 100% of rollback attempts by callers without rollback permission are denied with an authorization error.
- **SC-009**: 100% of successful rollbacks emit an `execution.rolled_back` event with the execution, target checkpoint number, and actor identifier.
- **SC-010**: 100% of workflows without an explicit checkpoint policy receive the default "before tool invocations only" policy on first execution, with zero manual configuration required.
- **SC-011**: 100% of in-flight executions continue to run under the policy in force at their start even if the workflow's policy is subsequently changed.
- **SC-012**: 100% of checkpoint records exceeding the configured size limit are rejected at capture time with a clear error, and the covered action (e.g., tool invocation) does NOT dispatch unchecked.
- **SC-013**: A compliance query for an execution's checkpoint list returns in under 1 second at p95 for executions with up to 100 checkpoints.

## Assumptions

- The existing scheduler (`workflow/services/scheduler.py`) exposes a dispatch-cycle hook where trigger evaluation can be inserted without a structural rewrite.
- The existing executor (`workflow/services/executor.py`) exposes a pre-step/pre-tool-invocation hook where checkpoint capture can be inserted.
- Trigger condition expressions use the platform-standard expression language already supported by the policy or evaluation subsystems; no new expression language is introduced.
- External tool invocation is the primary point of non-determinism and cost; default "checkpoint before tool invocation" reflects this.
- Complete state-restoration from a checkpoint requires no external coordination (e.g., no pending external callbacks); the captured state is self-sufficient.
- SLA deadlines are already tracked by the execution subsystem; this feature consumes them rather than introducing SLA management.
- Cost accounting (accumulated_costs) is already maintained by the execution subsystem; this feature consumes it rather than defining cost metrics.
- The retention window for checkpoints is operator-configurable with a safe default (e.g., 30 days); the default may be tightened per regulatory need.
- Rollback permission is represented in the existing RBAC/permission model as a discrete permission (e.g., `execution.rollback`) that admins grant to specific roles.
- Operators manually reconcile external side effects (calls already made after the checkpoint); the platform does not attempt automatic compensation of external systems.
- Event emission uses the existing event-envelope infrastructure; `execution.reprioritized` and `execution.rolled_back` are new event types on an existing execution-events channel.

## Dependencies

- Existing workflow execution scheduler (evaluates pending queue, dispatches next action).
- Existing workflow executor (dispatches step actions, invokes external tools).
- Existing execution state model (including SLA deadline tracking, accumulated cost, pending queue representation).
- Existing event bus and envelope infrastructure.
- Existing RBAC / permission system for rollback authorization.
- Existing scheduled-job infrastructure for retention-based checkpoint garbage collection.
- Existing audit trail infrastructure (to persist reprioritization and rollback audit records beyond the event bus).
- Existing object storage (for offloading large checkpoint snapshot components, if enabled).

## Out of Scope

- Building new trigger condition expression languages; triggers use existing condition expression capabilities.
- Automatic compensation of external side effects after rollback; the platform records the restore but does not call external compensating APIs.
- Automatic refund of external spend after rollback; the cost-delta is recorded for audit but no external-provider refund is initiated.
- Cross-execution rollback (rolling back a parent workflow cascades to children); this feature applies to a single execution scope.
- UI surfaces for trigger configuration, checkpoint listing, or rollback initiation; this feature defines the data and API surface that future UI features can consume.
- Non-SLA trigger types beyond the structural definition (e.g., specific budget-approach, priority-signal, dependency-ready triggers); those are separate triggers to be added incrementally on top of the core trigger framework.
- Streaming real-time checkpoint deltas to consumers; checkpoints are durable snapshots, not a streaming change feed.
- Automatic rollback (policy-driven rollback without operator action); all rollbacks in this feature are operator-initiated.
