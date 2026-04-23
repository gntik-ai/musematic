# REST API Contracts: Dynamic Re-Prioritization and Checkpoint/Rollback

**Feature**: 063-reprioritization-and-checkpoints  
**Base prefix**: `/api/v1`  
**Date**: 2026-04-19

All endpoints require `Authorization: Bearer <JWT>`. Workspace-scoped endpoints require the caller to have access to the workspace. Rollback endpoints additionally require the `execution.rollback` RBAC permission.

---

## 1. Reprioritization Triggers

### POST /api/v1/reprioritization-triggers

Create a configurable re-prioritization trigger.

**Request body:**
```json
{
  "name": "SLA Approach — Critical Queue",
  "trigger_type": "sla_approach",
  "condition_config": {
    "threshold_fraction": 0.15
  },
  "action": "promote_to_front",
  "priority_rank": 10,
  "workspace_id": "uuid | null"
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "name": "SLA Approach — Critical Queue",
  "trigger_type": "sla_approach",
  "condition_config": { "threshold_fraction": 0.15 },
  "action": "promote_to_front",
  "priority_rank": 10,
  "enabled": true,
  "workspace_id": "uuid | null",
  "created_by": "uuid",
  "created_at": "2026-04-19T10:00:00Z",
  "updated_at": "2026-04-19T10:00:00Z"
}
```

**Errors:**  
`422` — invalid trigger_type, threshold out of range (0.0–1.0), missing required condition fields  
`403` — caller not in workspace or lacks admin role

---

### GET /api/v1/reprioritization-triggers

List triggers visible to the caller (workspace-scoped + global).

**Query params:** `workspace_id` (required), `enabled` (optional bool), `page` / `page_size`

**Response 200:**
```json
{
  "items": [ { ... } ],
  "total": 3,
  "page": 1,
  "page_size": 50
}
```

---

### GET /api/v1/reprioritization-triggers/{trigger_id}

**Response 200:** Single trigger object (same shape as POST 201)  
**Errors:** `404` — not found, `403` — workspace mismatch

---

### PATCH /api/v1/reprioritization-triggers/{trigger_id}

Update name, condition_config, action, priority_rank, or enabled flag.

**Request body (all fields optional):**
```json
{
  "name": "Updated name",
  "condition_config": { "threshold_fraction": 0.20 },
  "action": "promote_to_front",
  "priority_rank": 5,
  "enabled": false
}
```

**Response 200:** Updated trigger object  
**Errors:** `422` validation, `404` not found, `403` unauthorized

---

### DELETE /api/v1/reprioritization-triggers/{trigger_id}

**Response 204:** No content  
**Errors:** `404`, `403`

---

## 2. Execution Checkpoints

### GET /api/v1/executions/{execution_id}/checkpoints

List checkpoints for an execution.

**Query params:** `include_superseded` (default: false), `page`, `page_size`

**Response 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "execution_id": "uuid",
      "checkpoint_number": 1,
      "last_event_sequence": 42,
      "completed_step_count": 3,
      "current_step_id": "step-4",
      "accumulated_costs": { "total_tokens": 1200, "total_usd": 0.018 },
      "superseded": false,
      "policy_snapshot": { "type": "before_tool_invocations" },
      "created_at": "2026-04-19T10:05:00Z"
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 50
}
```

**Errors:** `404` execution not found, `403` not authorized to view execution

---

### GET /api/v1/executions/{execution_id}/checkpoints/{checkpoint_number}

Get a single checkpoint with full state detail.

**Response 200:**
```json
{
  "id": "uuid",
  "execution_id": "uuid",
  "checkpoint_number": 2,
  "last_event_sequence": 87,
  "completed_step_ids": ["step-1", "step-2", "step-3"],
  "active_step_ids": [],
  "pending_step_ids": ["step-4", "step-5"],
  "step_results": { "step-1": { "output": "..." } },
  "current_context": { "key": "value" },
  "accumulated_costs": { "total_tokens": 2400, "total_usd": 0.036 },
  "execution_data": { "ir_snapshot": "..." },
  "superseded": false,
  "policy_snapshot": { "type": "before_tool_invocations" },
  "created_at": "2026-04-19T10:10:00Z"
}
```

**Errors:** `404` checkpoint not found, `403`

---

## 3. Rollback

### POST /api/v1/executions/{execution_id}/rollback/{checkpoint_number}

Roll back an execution to a specific checkpoint.

**Required RBAC permission**: `execution.rollback`

**Request body (optional):**
```json
{
  "reason": "Tool call at step 4 returned corrupted data"
}
```

**Response 200:**
```json
{
  "rollback_action_id": "uuid",
  "execution_id": "uuid",
  "target_checkpoint_number": 2,
  "target_checkpoint_id": "uuid",
  "initiated_by": "uuid",
  "cost_delta_reversed": {
    "total_tokens": 1200,
    "total_usd": 0.018,
    "note": "Costs accumulated after checkpoint 2 are reversed in accounting"
  },
  "status": "completed",
  "execution_status": "rolled_back",
  "warning": "External side effects (tool API calls made after checkpoint 2) persist and must be manually reconciled.",
  "created_at": "2026-04-19T10:15:00Z"
}
```

**Errors:**  
`409` — execution is actively dispatching (not paused/rolled_back/waiting_for_approval/failed)  
`404` — checkpoint not found or belongs to different execution  
`403` — missing `execution.rollback` permission  
`410` — checkpoint has been garbage-collected (retention expired)  
`500` — rollback failed mid-operation; execution transitioned to `rollback_failed` quarantine

---

## 4. Workflow Checkpoint Policy (via existing workflow API)

### PATCH /api/v1/workflows/{workflow_id}/versions/{version_number}

Existing endpoint extended with `checkpoint_policy` field (optional, backward-compatible).

**Request body extension (new field):**
```json
{
  "checkpoint_policy": {
    "type": "before_tool_invocations"
  }
}
```

Policy types:
- `{"type": "before_tool_invocations"}` — default behavior
- `{"type": "before_every_step"}` — checkpoint before each step
- `{"type": "named_steps", "step_ids": ["s3", "s5"]}` — specific steps only
- `{"type": "disabled"}` — no checkpoints

**Errors on invalid policy:**  
`422` — invalid type, or `step_ids` references step IDs not in the workflow version IR

---

## Kafka Events

### `execution.reprioritized` (extended payload)

Published on `execution.events` topic. Existing event type — payload extended with new fields (backward-compatible, new fields optional).

```json
{
  "event_type": "execution.reprioritized",
  "payload": {
    "execution_id": "uuid",
    "trigger_id": "uuid",
    "trigger_reason": "sla_approach",
    "trigger_name": "SLA Approach — Critical Queue",
    "steps_affected": ["step-4"],
    "priority_changes": [
      { "execution_id": "uuid", "old_position": 3, "new_position": 1 }
    ],
    "new_queue_order": ["uuid-A", "uuid-B", "uuid-C"]
  }
}
```

### `execution.rolled_back` (new event type)

Published on `execution.events` topic.

```json
{
  "event_type": "execution.rolled_back",
  "payload": {
    "execution_id": "uuid",
    "target_checkpoint_number": 2,
    "target_checkpoint_id": "uuid",
    "initiated_by": "uuid",
    "cost_delta_reversed": { "total_tokens": 1200, "total_usd": 0.018 },
    "rollback_action_id": "uuid"
  }
}
```
