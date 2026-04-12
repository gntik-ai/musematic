# Quickstart: Workflow Definition, Compilation, and Execution

**Branch**: `029-workflow-execution-engine` | **Date**: 2026-04-12 | **Phase**: 1

Test scenarios for verification. Uses pytest + pytest-asyncio with a live PostgreSQL test database.

---

## Prerequisites

- PostgreSQL test database with migration 029 applied
- Redis available for dispatch leases and state cache
- MinIO available for TaskPlanRecord payloads
- APScheduler running in test mode (tick triggered manually)
- Mock gRPC clients: ReasoningEngineService stub, RuntimeControlService stub, ContextEngineeringService stub
- Test workspace + platform_admin auth token

---

## Scenario 1 — Workflow Create and Version History

**Goal**: Verify valid YAML compiles to IR, creates version 1, and updates create version 2 immutably.

```python
# Create workflow
POST /api/v1/workflows
body = {
  "name": "Test Pipeline",
  "yaml_source": "schema_version: 1\nsteps:\n  - id: step_a\n    agent_fqn: 'ns:agent-a'",
  "workspace_id": workspace_id
}
# → 201, current_version.version_number=1, current_version.is_valid=True

# Update YAML
PATCH /api/v1/workflows/{workflow_id}
body = {"yaml_source": "schema_version: 1\nsteps:\n  - id: step_a ...\n  - id: step_b ..."}
# → 200, current_version.version_number=2

# Version 1 still accessible
GET /api/v1/workflows/{workflow_id}/versions/1
# → 200, version_number=1, original YAML preserved

# List versions
GET /api/v1/workflows/{workflow_id}/versions
# → 200, items has 2 entries in version_number order
```

**Expected**: Version 1 immutable and retrievable. Version 2 has new YAML. Compilation to IR preserves step identity.

---

## Scenario 2 — Invalid YAML Rejected with Field Errors

**Goal**: Verify validation errors include specific locations.

```python
POST /api/v1/workflows
body = {"yaml_source": "schema_version: 1\nsteps:\n  - id: step_a\n    timeout_seconds: -1"}
# → 422, errors list includes:
# [{"path": "steps[0].timeout_seconds", "message": "must be > 0", "value": -1}]

# Circular dependency test
POST /api/v1/workflows
body = {"yaml_source": "... step_a depends_on step_b, step_b depends_on step_a ..."}
# → 422, errors list includes:
# [{"path": "dag_edges", "message": "Circular dependency detected: step_a → step_b → step_a"}]
```

---

## Scenario 3 — Execution Journal Append-Only

**Goal**: Verify journal events accumulate and cannot be modified.

```python
execution = await execution_service.create_execution(ExecutionCreate(...))
# Journal has 1 event: type=created

# Simulate scheduler tick
await scheduler_service.tick(session)
# Journal has 2 events: created, queued

# Verify immutability: attempt direct UPDATE (should fail at DB level)
with pytest.raises(Exception):
    await session.execute(
        text("UPDATE execution_events SET event_type='completed' WHERE execution_id=:id"),
        {"id": str(execution.id)}
    )

# Verify state projection
state = await execution_service.get_execution_state(execution.id, session)
assert state.status == ExecutionStatus.QUEUED
assert state.last_event_sequence == 2
```

---

## Scenario 4 — Scheduler: Priority Ordering and Dispatch

**Goal**: Verify higher-priority steps dispatched before lower-priority.

```python
# Create workflow with 2 independent parallel steps (same priority initially)
# Set execution SLA so step B has approaching deadline → gets higher priority
execution = await execution_service.create_execution(
    ExecutionCreate(sla_deadline=datetime.now() + timedelta(minutes=5), ...)
)

# Tick scheduler
await scheduler_service.tick(session)

# Both steps are runnable; check dispatch order
dispatch_calls = runtime_controller_stub.dispatch_calls
assert dispatch_calls[0].step_id == "step_b"  # higher priority due to SLA proximity

# Verify dispatch lease acquired before dispatch
lease_key = f"exec:lease:{execution.id}:{dispatch_calls[0].step_id}"
assert redis_client.exists(lease_key)

# Verify TaskPlanRecord persisted before dispatch
tpr = await execution_service.get_task_plan(execution.id, dispatch_calls[0].step_id, session)
assert tpr.execution_id == execution.id
assert tpr.selected_agent_fqn is not None
assert tpr.created_at < dispatch_calls[0].dispatched_at
```

---

## Scenario 5 — Dispatch Lease Prevents Duplicate Dispatch

**Goal**: Verify same step cannot be dispatched twice simultaneously.

```python
execution = await execution_service.create_execution(...)
await scheduler_service.tick(session)  # dispatches step_a, acquires lease

# Attempt second tick while lease is active
await scheduler_service.tick(session)

# step_a should NOT be in dispatch calls a second time
assert len(runtime_controller_stub.dispatch_calls_for("step_a")) == 1
# Redis lease still active
assert redis_client.exists(f"exec:lease:{execution.id}:step_a")
```

---

## Scenario 6 — Replay Reconstructs Exact State

**Goal**: Verify replay from journal matches observed state.

```python
# Run execution to completion (3 steps)
execution = run_to_completion(workflow_with_3_steps)
original_state = await execution_service.get_execution_state(execution.id, session)

# Replay
replayed_state = await execution_service.replay_execution(execution.id, session)

assert replayed_state.status == original_state.status
assert set(replayed_state.completed_step_ids) == set(original_state.completed_step_ids)
assert replayed_state.step_results == original_state.step_results

# No new events written
event_count_before = await repo.count_events(execution.id)
assert await repo.count_events(execution.id) == event_count_before
```

---

## Scenario 7 — Resume from Checkpoint

**Goal**: Verify resume continues from last checkpoint without re-running completed steps.

```python
# 5-step workflow; steps 1-2 complete, step 3 fails
execution = run_until_failure(workflow_5_steps, fail_at="step_c")
# execution has checkpoint after step_b

new_execution = await execution_service.resume_execution(execution.id, session)
assert new_execution.parent_execution_id == execution.id
assert new_execution.id != execution.id

# Tick scheduler; verify steps a and b NOT dispatched again
await scheduler_service.tick(session)
dispatched_steps = [c.step_id for c in runtime_controller_stub.dispatch_calls_for(new_execution.id)]
assert "step_a" not in dispatched_steps
assert "step_b" not in dispatched_steps
assert "step_c" in dispatched_steps  # resumes from here
```

---

## Scenario 8 — Rerun Creates New Lineage

**Goal**: Verify rerun produces new execution linked to original.

```python
original = run_to_completion(workflow)

new_execution = await execution_service.rerun_execution(original.id, {}, session)
assert new_execution.id != original.id
assert new_execution.rerun_of_execution_id == original.id
assert new_execution.workflow_version_id == original.workflow_version_id

# New journal starts from scratch
events = await execution_service.get_journal(new_execution.id, session)
assert events[0].event_type == ExecutionEventType.CREATED
assert events[0].sequence == 1
```

---

## Scenario 9 — Hot Change: Compatible Change Applies

**Goal**: Verify a compatible hot change applies to a running execution.

```python
# Running execution at step 2 of 5
execution = start_execution_at(step="step_b", total_steps=5)
# Publish new version that adds step_f (not in active path)
new_version = await workflow_service.update_workflow(workflow_id, WorkflowUpdate(...add step_f...), session)

result = await execution_service.validate_hot_change(execution.id, new_version.current_version.id, session)
assert result.compatible is True
assert result.issues == []

await execution_service.apply_hot_change(execution.id, new_version.current_version.id, session)
# Journal contains hot_changed event
events = await execution_service.get_journal(execution.id, session)
assert any(e.event_type == ExecutionEventType.HOT_CHANGED for e in events)
```

---

## Scenario 10 — Hot Change: Incompatible Change Rejected

**Goal**: Verify removal of active step is rejected.

```python
execution = start_execution_at(step="step_b", total_steps=5)
new_version_without_step_b = await workflow_service.update_workflow(
    workflow_id, WorkflowUpdate(...removes step_b...), session
)

result = await execution_service.validate_hot_change(
    execution.id, new_version_without_step_b.id, session
)
assert result.compatible is False
assert "step_b" in result.issues[0]

# Apply returns 409, execution status unchanged
with pytest.raises(PolicyViolationError):
    await execution_service.apply_hot_change(execution.id, new_version_without_step_b.id, session)
```

---

## Scenario 11 — Webhook Trigger

**Goal**: Verify HMAC webhook creates execution.

```python
trigger = await workflow_service.create_trigger(
    workflow_id,
    TriggerCreate(trigger_type=TriggerType.WEBHOOK, name="Payment webhook",
                  config={"secret": "test-secret-123", "validation_method": "hmac_sha256"}),
    session
)

payload = b'{"invoice_id": "INV-999"}'
signature = hmac.new(b"test-secret-123", payload, hashlib.sha256).hexdigest()

response = await client.post(
    f"/api/v1/workflows/{workflow_id}/webhook/{trigger.id}",
    content=payload,
    headers={"X-Webhook-Signature": f"sha256={signature}"}
)
assert response.status_code == 202
execution_id = response.json()["execution_id"]

execution = await execution_service.get_execution(UUID(execution_id), session)
assert execution.trigger_type == TriggerType.WEBHOOK
assert execution.input_parameters["invoice_id"] == "INV-999"
```

---

## Scenario 12 — Cron Trigger Fires at Scheduled Time

**Goal**: Verify cron trigger creates execution at correct time with timezone.

```python
trigger = await workflow_service.create_trigger(
    workflow_id,
    TriggerCreate(trigger_type=TriggerType.CRON, name="Daily 9AM",
                  config={"cron_expression": "0 9 * * *", "timezone": "Europe/Rome"}),
    session
)

# Simulate cron fire at 2026-04-12 09:00:00 Europe/Rome
with freeze_time("2026-04-12 07:00:00 UTC"):  # 09:00 Rome is 07:00 UTC
    await cron_trigger_handler(trigger.id, session)

executions = await execution_service.list_executions(workspace_id=workspace_id, session=session)
assert any(e.trigger_type == TriggerType.CRON for e in executions.items)
```

---

## Scenario 13 — Workspace-Goal Trigger

**Goal**: Verify workspace-goal Kafka consumer creates execution on goal event.

```python
trigger = await workflow_service.create_trigger(
    workflow_id,
    TriggerCreate(trigger_type=TriggerType.WORKSPACE_GOAL, name="Goal trigger",
                  config={"workspace_id": str(workspace_id), "goal_type_pattern": "analyze-*"}),
    session
)

# Simulate Kafka event from workspace.goal topic
goal_event = WorkspaceGoalEvent(
    workspace_id=workspace_id, goal_id=UUID("..."), goal_type="analyze-quarterly-spend"
)
await workspace_goal_consumer_handler(goal_event, session)

executions = await execution_service.list_executions(workspace_id=workspace_id, session=session)
new_exec = executions.items[0]
assert new_exec.trigger_type == TriggerType.WORKSPACE_GOAL
assert new_exec.correlation_goal_id == goal_event.goal_id
```

---

## Scenario 14 — TaskPlanRecord Persisted Before Dispatch

**Goal**: Verify TaskPlanRecord exists before runtime controller receives dispatch call.

```python
execution = await execution_service.create_execution(...)

tpr_count_before = await session.scalar(
    select(func.count()).where(ExecutionTaskPlanRecord.execution_id == execution.id)
)
assert tpr_count_before == 0

# Tick with intercepted dispatch (pause before gRPC call)
async with intercept_dispatch() as dispatch_interceptor:
    scheduler_task = asyncio.create_task(scheduler_service.tick(session))
    await dispatch_interceptor.before_dispatch_event.wait()
    
    # TaskPlanRecord MUST exist before dispatch call
    tpr_count_mid = await session.scalar(...)
    assert tpr_count_mid == 1

    dispatch_interceptor.proceed()
    await scheduler_task
```

---

## Scenario 15 — Dynamic Re-Prioritization on Budget Breach

**Goal**: Verify queue reordering on budget threshold event and reprioritized event emitted.

```python
# Queue 3 steps with known priorities
execution = await execution_service.create_execution(...)

# Simulate budget threshold breach Kafka event
breach_event = BudgetThresholdBreachedEvent(execution_id=execution.id, threshold=0.9)
await reasoning_budget_event_consumer(breach_event, session)

# Re-prioritization should have run
reprioritized_events = [
    e for e in await execution_service.get_journal(execution.id, session)
    if e.event_type == ExecutionEventType.REPRIORITIZED
]
assert len(reprioritized_events) == 1
payload = reprioritized_events[0].payload
assert payload["trigger_reason"] == "budget_threshold_breached"
assert len(payload["steps_affected"]) > 0

# Kafka: execution.events topic has reprioritized event
kafka_events = kafka_mock.get_events("execution.events")
assert any(e.event_type == "execution.reprioritized" for e in kafka_events)
```

---

## Scenario 16 — Approval Gate Flow

**Goal**: Verify approval gate pauses execution and resumes on approval.

```python
# Workflow with approval gate at step_b
execution = await execution_service.create_execution(...)
await scheduler_service.tick(session)  # dispatches step_a

# step_a completes; now step_b (approval gate) should not dispatch
simulate_step_completion("step_a", execution.id)
await scheduler_service.tick(session)

state = await execution_service.get_execution_state(execution.id, session)
assert "step_b" in state.active_step_ids
assert state.status == ExecutionStatus.WAITING_FOR_APPROVAL

# Submit approval
await execution_service.record_approval_decision(
    execution.id, "step_b", ApprovalDecision.APPROVED, approver_id=user_id, comment=None, session=session
)

# Scheduler now dispatches step_b as approved
await scheduler_service.tick(session)
dispatched = [c.step_id for c in runtime_controller_stub.dispatch_calls]
assert "step_b" in dispatched
```
