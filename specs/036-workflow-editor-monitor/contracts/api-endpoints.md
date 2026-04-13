# API Contracts: Workflow Editor and Execution Monitor

All endpoints require `Authorization: Bearer <access_token>` and return JSON.  
Timestamps are ISO 8601 strings. IDs are UUIDs.

---

## Workflow Endpoints

### List Workflows
```
GET /api/v1/workflows?workspace_id={id}&cursor={cursor}&limit={limit}
→ { items: WorkflowDefinition[], nextCursor: string | null }
```

### Get Workflow
```
GET /api/v1/workflows/{workflow_id}
→ WorkflowDefinition
```

### Create Workflow
```
POST /api/v1/workflows
body: { workspace_id, name, description?, yaml_content }
→ WorkflowDefinition  (201 Created)
```

### Update Workflow (creates new version)
```
PATCH /api/v1/workflows/{workflow_id}
body: { yaml_content, description? }
→ WorkflowDefinition  (includes updated currentVersionId)
```

### Get Workflow Version
```
GET /api/v1/workflows/{workflow_id}/versions/{version_id}
→ WorkflowVersion  (includes yaml_content and compiled_ir)
```

### Get Workflow Schema
```
GET /api/v1/workflows/schema
→ JSON Schema object (for Monaco YAML validation + autocomplete)
Cached: stale after 1 hour
```

---

## Execution Endpoints

### Start Execution
```
POST /api/v1/executions
body: { workflow_version_id, input_overrides?: Record<string, unknown>, trigger_type: 'manual' }
→ Execution  (201 Created)
```

### Get Execution
```
GET /api/v1/executions/{execution_id}
→ Execution
```

### Get Execution State (projected)
```
GET /api/v1/executions/{execution_id}/state
→ ExecutionState  (completed/active/pending/failed/skipped/waiting step ID lists + step_results)
```

### Get Execution Journal
```
GET /api/v1/executions/{execution_id}/journal
  ?since_sequence={n}     # for incremental polling / reconnect catch-up
  &event_type={type}      # optional filter
  &step_id={id}           # optional filter
  &limit={n}              # default 50
  &offset={n}
→ { events: ExecutionEvent[], total: number }
```

### Get Step Detail
```
GET /api/v1/executions/{execution_id}/steps/{step_id}
→ StepDetail  (inputs, outputs, timing, context_quality_score, token_usage, error)
```

### Get Task Plan
```
GET /api/v1/executions/{execution_id}/task-plan/{step_id}
→ TaskPlanFullResponse  (candidates, selection, rationale, parameter_provenance)
```

---

## Execution Control Endpoints

### Cancel Execution
```
POST /api/v1/executions/{execution_id}/cancel
body: { reason?: string }
→ 204 No Content
```

### Pause Execution
```
POST /api/v1/executions/{execution_id}/pause
body: {}
→ 204 No Content
```
*Note: Assumed endpoint — inferred from 029 spec functional description. Verify with backend team.*

### Resume Execution
```
POST /api/v1/executions/{execution_id}/resume
body: {}
→ 204 No Content  (or Execution object)
```

### Retry Failed Step
```
POST /api/v1/executions/{execution_id}/steps/{step_id}/retry
body: {}
→ 204 No Content
```
*Note: Assumed endpoint — inferred from 029 retry configuration.*

### Skip Step
```
POST /api/v1/executions/{execution_id}/steps/{step_id}/skip
body: { reason?: string }
→ 204 No Content
```
*Note: Assumed endpoint — inferred from 029 functional description.*

### Inject Variable (Hot Change)
```
POST /api/v1/executions/{execution_id}/hot-change
body: { variable_name: string, value: unknown, reason?: string }
→ 204 No Content
```
*Note: Maps to 029 "hot change" mechanism. Assumed path.*

### Submit Approval Decision
```
POST /api/v1/executions/{execution_id}/approvals/{step_id}/decide
body: { decision: 'approved' | 'rejected', comment?: string }
→ 204 No Content
```

---

## Analytics Endpoints (Cost Tracker)

### Get Execution Cost Summary
```
GET /api/v1/analytics/usage?workspace_id={id}&execution_id={id}
→ { items: [{ agent_fqn, model_id, input_tokens, output_tokens, total_tokens, cost_usd }] }
```
*Aggregated per-step cost breakdown assembled client-side.*

---

## Error Responses

All endpoints return errors in this shape:
```json
{
  "code": "NOT_FOUND",
  "message": "Execution not found",
  "details": {}
}
```

| HTTP Status | code | When |
|-------------|------|------|
| 400 | `VALIDATION_ERROR` | Invalid request body |
| 403 | `AUTHORIZATION_ERROR` | Insufficient permissions |
| 404 | `NOT_FOUND` | Resource doesn't exist |
| 409 | `CONFLICT` | Control action on non-controllable execution |
| 429 | `BUDGET_EXCEEDED` | Rate limit or budget constraint |
| 412 | `PRECONDITION_FAILED` | Stale data (If-Unmodified-Since mismatch) |
