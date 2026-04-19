# Quickstart & Test Scenarios: Dynamic Re-Prioritization and Checkpoint/Rollback

**Feature**: 063-reprioritization-and-checkpoints  
**Date**: 2026-04-19

---

## Setup Prerequisites

```bash
# Start control plane with test config
cd apps/control-plane
pytest tests/integration/execution/test_reprioritization_integration.py -v
pytest tests/integration/execution/test_checkpoint_integration.py -v
```

All scenarios assume:
- A workspace `workspace-1` exists
- A workflow `workflow-sla-test` with steps: `step-1 (compute)`, `step-2 (compute)`, `step-3 (tool-invoke)`, `step-4 (tool-invoke)`, `step-5 (compute)` 
- The caller is an admin with `execution.rollback` permission

---

## Scenario S1: SLA Approach Trigger Promotes Execution

**Tests**: FR-001, FR-002, FR-003, FR-005, SC-001, SC-002  
**Story**: US1

1. Create SLA trigger:
   ```
   POST /api/v1/reprioritization-triggers
   { "trigger_type": "sla_approach", "condition_config": {"threshold_fraction": 0.15}, "action": "promote_to_front", "priority_rank": 10, "workspace_id": "workspace-1" }
   → 201 { "id": "trigger-1", "enabled": true }
   ```
2. Enqueue three executions (A, B, C) with SLA deadlines in 2h, 8h, 16h respectively:
   ```
   POST /api/v1/executions × 3 with sla_deadline set
   ```
3. Advance time so execution A has < 15% SLA remaining. Wait for next scheduler tick.
4. Verify GET /api/v1/executions?workspace_id=workspace-1 returns A in position 1.
5. Verify Kafka topic `execution.events` received event with `event_type = "execution.reprioritized"`, payload includes `trigger_id = "trigger-1"`, `execution_id = A.id`, `new_position = 1`.

**Expected**: A dispatched first; reprioritized event emitted; B and C retain relative order.

---

## Scenario S2: Idempotent Reprioritization (No Duplicate Events)

**Tests**: FR-004, SC-002  
**Story**: US1

1. Continue from S1. A is already at position 1.
2. On the next scheduler tick with same SLA conditions (A still < 15%), verify no second `execution.reprioritized` event is emitted for A.

**Expected**: Zero duplicate reprioritization events for an already-promoted execution.

---

## Scenario S3: Invalid Trigger Configuration Rejected

**Tests**: FR-006  
**Story**: US1

1. Attempt to create a trigger with threshold_fraction = 1.5 (> 1.0):
   ```
   POST /api/v1/reprioritization-triggers
   { "trigger_type": "sla_approach", "condition_config": {"threshold_fraction": 1.5}, "action": "promote_to_front" }
   → 422 { "detail": "threshold_fraction must be between 0.0 and 1.0" }
   ```
2. Attempt trigger with unknown trigger_type = "budget_approach":
   ```
   → 422 { "detail": "trigger_type 'budget_approach' is not supported in this release" }
   ```

**Expected**: Both rejected at save time with clear validation errors.

---

## Scenario S4: Default Checkpoint Captured Before Tool Invocation

**Tests**: FR-007, FR-008, FR-009, SC-003, SC-004  
**Story**: US2

1. Submit execution of `workflow-sla-test` (no explicit checkpoint policy → default applies).
2. Let scheduler run until step-3 is about to dispatch.
3. Verify: `GET /api/v1/executions/{id}/checkpoints` returns 1 checkpoint with:
   - `checkpoint_number = 1`
   - `completed_step_ids = ["step-1", "step-2"]`
   - `pending_step_ids = ["step-3", "step-4", "step-5"]`
   - `current_context`, `accumulated_costs`, `policy_snapshot` all non-null
   - `superseded = false`
4. Verify step-3 dispatched to runtime only after checkpoint was persisted.

**Expected**: One checkpoint exists; all required fields populated; tool invocation did not precede checkpoint.

---

## Scenario S5: Multiple Tool Invocations → Multiple Sequential Checkpoints

**Tests**: FR-007, FR-008, FR-009, SC-003  
**Story**: US2

1. Submit execution of `workflow-sla-test`. Let it run to completion.
2. `GET /api/v1/executions/{id}/checkpoints` must return exactly 2 checkpoints:
   - Checkpoint 1: before step-3 (tool)
   - Checkpoint 2: before step-4 (tool)
3. Verify checkpoint_number is monotonically increasing (1, 2).

**Expected**: Two checkpoints with ascending numbers; no checkpoint before compute-only steps.

---

## Scenario S6: No Checkpoints for Compute-Only Workflow

**Tests**: FR-009 default policy, SC-010  
**Story**: US2

1. Submit execution of a workflow with no tool-invoke steps (all compute steps).
2. Wait for execution to complete.
3. `GET /api/v1/executions/{id}/checkpoints` → `{ "items": [], "total": 0 }` (not 404).

**Expected**: Empty list returned, execution ran successfully without any checkpoints.

---

## Scenario S7: Checkpoint Capture Failure Pauses Execution

**Tests**: FR-013, SC-012  
**Story**: US2

1. Configure storage to reject writes (inject fault).
2. Submit execution. Let it reach a tool-invoke step.
3. Verify execution transitions to `paused` status with a recoverable error event in the journal.
4. Verify the tool call was NOT dispatched (no `dispatched` event after the failure).

**Expected**: Execution paused; tool invocation did not proceed without checkpoint coverage.

---

## Scenario S8: Successful Rollback Restores State

**Tests**: FR-015, FR-019, SC-006, SC-009  
**Story**: US3

1. Run an execution to completion through 3 checkpoints.
2. Issue rollback to checkpoint 2:
   ```
   POST /api/v1/executions/{id}/rollback/2
   → 200 { "rollback_action_id": "...", "status": "completed", "execution_status": "rolled_back" }
   ```
3. Verify execution state matches checkpoint 2:
   - `GET /api/v1/executions/{id}/state`
   - `completed_step_ids` equals checkpoint-2 `completed_step_ids`
   - `pending_step_ids` equals checkpoint-2 `pending_step_ids`
4. Verify Kafka event `execution.rolled_back` emitted with correct execution_id and checkpoint_number.
5. Verify rollback action record queryable via audit trail.

**Expected**: State exactly matches checkpoint 2; rolled_back event emitted; execution_status = `rolled_back`.

---

## Scenario S9: Superseded Checkpoints Retained After Rollback

**Tests**: FR-020  
**Story**: US3

1. Continue from S8. Checkpoint 3 (which was superseded by rollback to 2) must still exist.
2. `GET /api/v1/executions/{id}/checkpoints` (default: no superseded):
   - Returns checkpoints 1 and 2 only.
3. `GET /api/v1/executions/{id}/checkpoints?include_superseded=true`:
   - Returns all 3 checkpoints. Checkpoint 3 has `superseded = true`.

**Expected**: Superseded checkpoints not deleted; filterable from default listing.

---

## Scenario S10: Rollback Rejected for Active Execution

**Tests**: FR-016, SC-007  
**Story**: US3

1. Submit execution, wait until it is in `running` status (actively dispatching).
2. Issue rollback:
   ```
   POST /api/v1/executions/{id}/rollback/1
   → 409 { "detail": "Rollback rejected: execution is actively dispatching. Pause or wait for completion first." }
   ```
3. Verify execution state unchanged.

**Expected**: 409 returned; no state modification.

---

## Scenario S11: Rollback Rejected Without Permission

**Tests**: FR-018, SC-008  
**Story**: US3

1. Issue rollback request with a token that lacks `execution.rollback` permission.
   ```
   POST /api/v1/executions/{id}/rollback/1
   → 403 { "detail": "Permission 'execution.rollback' required" }
   ```

**Expected**: 403; no state modification.

---

## Scenario S12: Rolled-Back Execution Can Be Resumed

**Tests**: FR-021  
**Story**: US3

1. After successful rollback to checkpoint 2 (from S8), resume the execution:
   ```
   POST /api/v1/executions/{id}/resume
   ```
2. Verify execution transitions to `running` and dispatches steps from the restored pending_queue.

**Expected**: Execution resumes from the checkpoint-2 restore point.

---

## Scenario S13: Custom Policy — Before Every Step

**Tests**: FR-010, FR-011, FR-012  
**Story**: US4

1. Set checkpoint policy on workflow version:
   ```
   PATCH /api/v1/workflows/{id}/versions/{ver}
   { "checkpoint_policy": { "type": "before_every_step" } }
   ```
2. Submit execution. Wait for completion.
3. `GET /api/v1/executions/{id}/checkpoints` → exactly 5 checkpoints (one before each of 5 steps).

**Expected**: 5 checkpoints; policy respected.

---

## Scenario S14: Custom Policy — Disabled

**Tests**: FR-010  
**Story**: US4

1. Set policy to disabled:
   ```
   PATCH /api/v1/workflows/{id}/versions/{ver}
   { "checkpoint_policy": { "type": "disabled" } }
   ```
2. Submit execution. Run to completion including tool steps.
3. `GET /api/v1/executions/{id}/checkpoints` → `{ "items": [], "total": 0 }`

**Expected**: Zero checkpoints created even though tool invocations occurred.

---

## Scenario S15: Custom Policy — Named Steps

**Tests**: FR-010, FR-011  
**Story**: US4

1. Set policy:
   ```
   PATCH /api/v1/workflows/{id}/versions/{ver}
   { "checkpoint_policy": { "type": "named_steps", "step_ids": ["step-3", "step-5"] } }
   ```
2. Submit execution. Let it complete.
3. Verify exactly 2 checkpoints exist (before step-3 and before step-5).

**Expected**: Checkpoints only at named steps.

---

## Scenario S16: Invalid Policy — Unknown Step IDs Rejected

**Tests**: FR-011  
**Story**: US4

1. Attempt to save policy referencing non-existent step ID:
   ```
   PATCH /api/v1/workflows/{id}/versions/{ver}
   { "checkpoint_policy": { "type": "named_steps", "step_ids": ["nonexistent-step"] } }
   → 422 { "detail": "step_ids contains unknown step IDs: ['nonexistent-step']" }
   ```

**Expected**: 422 at save time; policy not persisted.

---

## Scenario S17: Policy Snapshot at Execution Start (Mid-Flight Policy Change)

**Tests**: FR-012, SC-011  
**Story**: US4

1. Start execution E1 with policy "before_every_step". E1 is in progress.
2. Change workflow policy to "disabled".
3. E1 continues — must still capture checkpoints before every step (policy at start).
4. Start new execution E2. E2 runs with "disabled" policy (new policy applies).

**Expected**: E1 unaffected by policy change; E2 uses updated policy.

---

## Scenario S18: List Checkpoints for Audit

**Tests**: FR-014, SC-013  
**Story**: US5

1. Run an execution producing 5 checkpoints.
2. `GET /api/v1/executions/{id}/checkpoints`
3. Verify:
   - 5 entries in ascending checkpoint_number order (1, 2, 3, 4, 5)
   - Each entry has: `checkpoint_number`, `created_at`, completed step count, `accumulated_costs` summary
   - Response time < 1 second (SC-013)

**Expected**: Ordered list with summary fields; response within SLA.

---

## Scenario S19: Trigger Evaluation Time-Bounded

**Tests**: FR-025  
**Story**: US1 edge case

1. Configure a computationally expensive trigger that takes > the cycle evaluation budget.
2. Run scheduler tick with pending executions.
3. Verify:
   - Dispatch cycle completes (not blocked)
   - Queue order unchanged (pre-evaluation order used)
   - Warning logged: "trigger evaluation budget exceeded"
   - No execution.reprioritized event emitted

**Expected**: Scheduling correctness not blocked by slow trigger evaluation.

---

## Scenario S20: Contradictory Triggers — Higher Priority Wins

**Tests**: FR-026  
**Story**: US1 edge case

1. Create two triggers for workspace-1:
   - Trigger A (priority_rank=5): "SLA < 15% → promote_to_front"
   - Trigger B (priority_rank=50): "SLA < 15% → demote"
2. Enqueue execution X with < 15% SLA remaining.
3. Run scheduler tick.
4. Verify X is promoted (Trigger A applied).
5. Verify audit log records that Trigger B fired but was not applied due to priority conflict.

**Expected**: Highest-priority trigger wins; other trigger firing recorded in audit.

---

## Scenario S21: Oversized Checkpoint Rejected

**Tests**: FR-022, SC-012  
**Story**: US2 edge case

1. Configure execution with context that produces a checkpoint state > 10 MB.
2. When tool invocation step is about to dispatch, verify:
   - Checkpoint capture fails with `CheckpointSizeLimitExceeded` error
   - Execution pauses with recoverable error
   - Tool call does NOT proceed

**Expected**: Clear error; execution paused; no unchecked tool dispatch.

---

## Scenario S22: Rollback to Expired Checkpoint Rejected

**Tests**: FR-023, SC-007  
**Story**: US3 edge case

1. Run execution. Create checkpoints. Advance time past retention window (or manually expire).
2. Run GC job: expired checkpoints removed.
3. Attempt rollback to expired checkpoint:
   ```
   POST /api/v1/executions/{id}/rollback/1
   → 410 { "detail": "Checkpoint 1 has been removed by retention policy." }
   ```

**Expected**: 410 error; no state modification.

---

## Scenario S23: Failed Rollback → Quarantine State

**Tests**: FR-028  
**Story**: US3 edge case

1. Inject a storage fault mid-rollback (e.g., database connection drops after partial write).
2. Issue rollback request.
3. Verify execution transitions to `rollback_failed` status (not partial restore).
4. Verify rollback action record has `status = "failed"` with `failure_reason` populated.
5. Verify no further rollback or resume is possible until operator resolves.

**Expected**: Execution enters quarantine; state is NOT partially restored; operator intervention required.

---

## Scenario S24: Backward Compatibility — Existing Executions Without Policy

**Tests**: FR-029, SC-010  
**Story**: Cross-cutting

1. Existing executions started before feature deploy have `checkpoint_policy_snapshot = null`.
2. Verify they continue to run without errors (null policy treated as "before_tool_invocations" default).
3. Existing workflows with `checkpoint_policy = null` start new executions with the default policy.

**Expected**: Zero manual configuration required; existing executions unaffected.

---

## Scenario S25: Post-Rollback Checkpoint Numbering Continues Sequence

**Tests**: FR-008 (monotonic), edge case  
**Story**: US3

1. Run execution; produce checkpoints 1, 2, 3.
2. Rollback to checkpoint 2 (checkpoint 3 marked superseded).
3. Resume execution; a new tool invocation occurs.
4. Verify: new checkpoint is numbered 4 (not 3 — sequence does not reset).

**Expected**: Checkpoint numbers always increase; audit trail intact; no number reuse.
