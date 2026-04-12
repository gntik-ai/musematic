# API Contracts: Workflow Definition, Compilation, and Execution

**Branch**: `029-workflow-execution-engine` | **Date**: 2026-04-12 | **Phase**: 1

All endpoints prefixed `/api/v1`. Requires `Authorization: Bearer <access_token>`. Write operations require `platform_admin` or `workspace_admin` role; read operations require any authenticated workspace member.

---

## Workflow Definition Endpoints

### `POST /workflows`

Create a new workflow definition with version 1.

**Request Body**: `WorkflowCreate`
```json
{
  "name": "Invoice Processing Pipeline",
  "description": "Processes invoices end-to-end",
  "yaml_source": "schema_version: 1\nsteps:\n  - id: fetch_invoice ...",
  "change_summary": "Initial version",
  "tags": ["finance", "invoicing"],
  "workspace_id": "uuid"
}
```

**Response**: `201 Created` — `WorkflowResponse`

**Error Codes**:
- `400` — YAML parse error (includes parse location)
- `422` — Schema validation failed (includes field-level errors)
- `409` — Name already exists in workspace

---

### `GET /workflows`

List workflow definitions with filters.

**Query Parameters**: `workspace_id` (required), `status?`, `tags?` (comma-separated), `page?`, `page_size?` (default 20, max 100)

**Response**: `200 OK` — `WorkflowListResponse`

---

### `GET /workflows/{workflow_id}`

**Response**: `200 OK` — `WorkflowResponse` (includes `current_version`)

**Error Codes**: `404`

---

### `PATCH /workflows/{workflow_id}`

Update YAML source — creates new immutable version.

**Request Body**: `WorkflowUpdate`

**Response**: `200 OK` — `WorkflowResponse` (current_version reflects new version)

**Error Codes**: `400`, `404`, `422`

---

### `POST /workflows/{workflow_id}/archive`

**Response**: `200 OK` — `WorkflowResponse`

**Error Codes**: `404`, `409` (already archived)

---

### `GET /workflows/{workflow_id}/versions`

**Response**: `200 OK` — `{ "items": [WorkflowVersionResponse, ...], "total": N }`

---

### `GET /workflows/{workflow_id}/versions/{version_number}`

**Response**: `200 OK` — `WorkflowVersionResponse`

**Error Codes**: `404`

---

## Trigger Definition Endpoints

### `POST /workflows/{workflow_id}/triggers`

**Request Body**: `TriggerCreate`
```json
{
  "trigger_type": "cron",
  "name": "Daily 9AM Europe/Rome",
  "config": { "cron_expression": "0 9 * * *", "timezone": "Europe/Rome" }
}
```

**Response**: `201 Created` — `TriggerResponse`

---

### `GET /workflows/{workflow_id}/triggers`

**Response**: `200 OK` — `{ "items": [TriggerResponse, ...] }`

---

### `PATCH /workflows/{workflow_id}/triggers/{trigger_id}`

**Request Body**: `TriggerCreate` (partial update)

**Response**: `200 OK` — `TriggerResponse`

---

### `DELETE /workflows/{workflow_id}/triggers/{trigger_id}`

**Response**: `204 No Content`

---

### `POST /workflows/{workflow_id}/webhook/{trigger_id}`

Webhook entry point. Validates HMAC-SHA256 signature from `X-Webhook-Signature` header.

**Request Body**: Any JSON payload (passed as `input_parameters` to the new execution)

**Response**: `202 Accepted` — `{ "execution_id": "uuid" }`

**Error Codes**: `401` (invalid signature), `404` (trigger not found), `409` (concurrency limit reached)

---

## Execution Endpoints

### `POST /executions`

Create a new execution (manual, API, orchestrator trigger types).

**Request Body**: `ExecutionCreate`
```json
{
  "workflow_definition_id": "uuid",
  "trigger_type": "manual",
  "input_parameters": { "invoice_id": "INV-001" },
  "workspace_id": "uuid",
  "correlation_goal_id": null,
  "sla_deadline": "2026-04-12T18:00:00Z"
}
```

**Response**: `201 Created` — `ExecutionResponse`

**Error Codes**: `404` (workflow not found), `422` (validation failed), `409` (concurrency limit)

---

### `GET /executions`

List executions.

**Query Parameters**: `workspace_id` (required), `workflow_id?`, `status?`, `trigger_type?`, `goal_id?`, `since?`, `page?`, `page_size?`

**Response**: `200 OK` — `ExecutionListResponse`

---

### `GET /executions/{execution_id}`

**Response**: `200 OK` — `ExecutionResponse`

**Error Codes**: `404`

---

### `POST /executions/{execution_id}/cancel`

Cancel a running or queued execution.

**Response**: `200 OK` — `ExecutionResponse`

**Error Codes**: `404`, `409` (already completed/failed/canceled)

---

### `GET /executions/{execution_id}/state`

Return the current projected execution state (from checkpoint + recent events).

**Response**: `200 OK` — `ExecutionStateResponse`
```json
{
  "execution_id": "uuid",
  "status": "running",
  "completed_step_ids": ["fetch_invoice", "validate_invoice"],
  "active_step_ids": ["classify_invoice"],
  "pending_step_ids": ["approve_invoice", "post_to_ledger"],
  "step_results": {
    "fetch_invoice": { "status": "completed", "output": { "invoice": {...} } }
  },
  "last_event_sequence": 14
}
```

---

### `GET /executions/{execution_id}/journal`

Return the full append-only event journal.

**Query Parameters**: `since_sequence?` (only return events after this sequence), `event_type?`

**Response**: `200 OK` — `{ "items": [ExecutionEventResponse, ...], "total": N }`

---

### `POST /executions/{execution_id}/replay`

Reconstruct execution state from journal + reasoning traces (debug tool).

**Response**: `200 OK` — `ExecutionStateResponse` (exact reconstruction, no new events written)

---

### `POST /executions/{execution_id}/resume`

Create a new execution linked to this one, continuing from the last checkpoint.

**Response**: `201 Created` — `ExecutionResponse` (new execution with `parent_execution_id` set)

**Error Codes**: `404`, `409` (execution still running — cannot resume an active execution)

---

### `POST /executions/{execution_id}/rerun`

Create a new execution with a new ID using the same workflow version.

**Request Body** (optional): `{ "input_overrides": { "param": "new_value" } }`

**Response**: `201 Created` — `ExecutionResponse` (new execution with `rerun_of_execution_id` set)

---

### `POST /executions/{execution_id}/hot-change`

Validate and apply a new workflow version to a running execution.

**Request Body**: `HotChangeRequest` — `{ "new_version_id": "uuid" }`

**Response**: `200 OK` — `{ "result": HotChangeCompatibilityResult, "execution": ExecutionResponse }`

**Error Codes**: `404`, `409` (incompatible — returns 409 with issues list, execution unchanged)

---

### `POST /executions/{execution_id}/compensation/{step_id}`

Trigger compensation for a completed step.

**Response**: `202 Accepted` — `{ "compensation_record_id": "uuid" }`

**Error Codes**: `404` (execution or step not found), `409` (step not completed or already compensated)

---

## Task Plan Endpoints

### `GET /executions/{execution_id}/task-plan`

Return all TaskPlanRecords for an execution (metadata summary, no MinIO payload).

**Response**: `200 OK` — `{ "items": [TaskPlanRecordResponse, ...] }`

---

### `GET /executions/{execution_id}/task-plan/{step_id}`

Return the full TaskPlanRecord for a step (includes MinIO payload).

**Response**: `200 OK` — `TaskPlanFullResponse`

**Error Codes**: `404`

---

## Approval Endpoints

### `GET /executions/{execution_id}/approvals`

List pending approval waits for an execution.

**Response**: `200 OK` — `{ "items": [ApprovalWaitResponse, ...] }`

---

### `POST /executions/{execution_id}/approvals/{step_id}/decide`

Submit an approval decision.

**Request Body**: `ApprovalDecisionRequest` — `{ "decision": "approved", "comment": "Looks good" }`

**Response**: `200 OK`

**Error Codes**: `404`, `409` (already decided or timed out)

---

## Internal Service Interfaces

### `ExecutionService.create_execution(data)` — called by:
- Trigger handlers (cron APScheduler, webhook endpoint, event-bus Kafka consumer, workspace-goal consumer)
- `fleets/` bounded context for orchestrator triggers
- `interactions/` bounded context for manual/user triggers

### `ExecutionService.record_approval_decision(...)` — called by:
- `interactions/` bounded context when user approves/rejects via conversation action

### `SchedulerService.handle_reprioritization_trigger(...)` — called by:
- Kafka consumers in `execution/events.py` watching `runtime.reasoning` (budget threshold), `fleet.health` (resource constraint), `interaction.attention` (external event)

### `WorkflowService.validate_and_compile(yaml_source)` — called by:
- Internal: `WorkflowService.create_workflow()` and `WorkflowService.update_workflow()`
- `policies/` bounded context: workflow governance validation (constitution §VI)

---

## Kafka Events Produced

| Topic | Event Type | Key | Description |
|-------|-----------|-----|-------------|
| `execution.events` | `execution.created` | `execution_id` | New execution created |
| `execution.events` | `execution.status_changed` | `execution_id` | Step or execution status transition |
| `execution.events` | `execution.reprioritized` | `execution_id` | Queue reordered due to trigger |
| `execution.events` | `execution.completed` | `execution_id` | Execution fully completed |
| `execution.events` | `execution.failed` | `execution_id` | Execution failed |
| `workflow.triggers` | `workflow.trigger.fired` | `workflow_id` | Trigger fired (for async dispatch) |
| `workflow.triggers` | `workflow.published` | `workflow_id` | New workflow version published |

## Kafka Events Consumed

| Topic | Event Type | Action |
|-------|-----------|--------|
| `workflow.runtime` | `step.completed` | Release dispatch lease, write journal event, advance scheduler |
| `workflow.runtime` | `step.failed` | Release lease, write failed event, retry if eligible |
| `runtime.reasoning` | `budget.threshold_breached` | Trigger re-prioritization for affected execution |
| `fleet.health` | `member.failed` | Trigger re-prioritization for fleet-linked executions |
| `interaction.attention` | `attention.requested` | Trigger re-prioritization for execution linked to attention target |
| `workspace.goal` | `goal.created` | Check workspace-goal triggers, create executions on match |
| `workspace.goal` | `goal.updated` | Same as above |
