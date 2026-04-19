# REST API Contract: Advanced Reasoning Modes and Trace Export

**Feature**: 064-reasoning-modes-and-trace | **Date**: 2026-04-19  
**Owner**: `execution/` bounded context  
**Router file**: `apps/control-plane/src/platform/execution/router.py`

## GET /api/v1/executions/{execution_id}/reasoning-trace

Fetch the structured reasoning trace for an execution.

**Authorization**: Any caller authorized to view the execution.

**Query Parameters**:
- `step_id` (optional)
- `page` (default 1)
- `page_size` (default 100, max 500)

**Notes**:
- The control plane resolves the effective compute budget before invoking Go runtime APIs.
- Trace export reflects that resolved scope via `effective_budget_scope`.

### 200 OK

```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "technique": "DEBATE",
  "schema_version": "1.0",
  "status": "complete",
  "steps": [
    {
      "step_number": 1,
      "type": "position",
      "agent_fqn": "debate-agents:analyst-a",
      "content": "Latency-first gives the safest UX.",
      "tool_call": null,
      "quality_score": 0.82,
      "tokens_used": 145,
      "timestamp": "2026-04-19T10:00:01.234567Z"
    }
  ],
  "total_tokens": 1842,
  "compute_budget_used": 0.68,
  "effective_budget_scope": "step",
  "compute_budget_exhausted": false,
  "consensus_reached": true,
  "stabilized": null,
  "degradation_detected": null,
  "last_updated_at": null,
  "pagination": {
    "page": 1,
    "page_size": 100,
    "total_steps": 42,
    "has_more": false
  }
}
```

### Error semantics

- `403 Forbidden` -> `{"code": "authorization_error", "message": "Not authorized"}`
- `404 Not Found` for execution missing -> `{"code": "execution_not_found"}`
- `404 Not Found` for trace missing -> `{"code": "trace_not_found"}`
- `410 Gone` for retention-expired artifacts -> `{"code": "trace_not_available"}`

## Runtime contract ownership

The REST surface does not expose DEBATE orchestration directly. Debate and self-correction execution details are driven through the Go gRPC contract; the control plane owns:
- execution/workflow configuration
- effective compute-budget resolution
- authorization
- trace retrieval and pagination
