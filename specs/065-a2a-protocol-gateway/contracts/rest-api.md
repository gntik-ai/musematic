# REST API Contract: A2A Protocol Gateway

**Feature**: 065-a2a-protocol-gateway | **Date**: 2026-04-19  
**Owner**: `a2a_gateway/` bounded context  
**Router file**: `apps/control-plane/src/platform/a2a_gateway/router.py`  
**Mount prefix**: `app.include_router(a2a_gateway_router, prefix="/api/v1/a2a")` in `main.py`

---

## GET /.well-known/agent.json

Fetch the platform's public Agent Card. Anonymous — no authentication required.

**Authorization**: Public (no token required).

**Notes**:
- Generated from active, public AgentProfile + AgentRevision records.
- Archived, revoked, non-public, or incomplete agents are excluded.
- Refreshed automatically when registry state changes; max staleness = 5 minutes (SC-001).

### 200 OK

```json
{
  "name": "Agentic Mesh Platform",
  "description": "Multi-tenant agent orchestration platform exposing platform agents via A2A.",
  "url": "https://platform.example.com/api/v1/a2a",
  "version": "1.0",
  "capabilities": ["streaming", "multi-turn"],
  "authentication": [
    {"scheme": "bearer", "in": "header", "name": "Authorization"}
  ],
  "skills": [
    {
      "id": "finance-ops:kyc-verifier",
      "name": "finance-ops:kyc-verifier",
      "description": "KYC verification agent for financial compliance",
      "tags": ["finance", "compliance"]
    }
  ]
}
```

---

## POST /api/v1/a2a/tasks

Submit an inbound A2A task targeting a platform agent.

**Authorization**: Bearer JWT (required).

**Request body**:
```json
{
  "agent_fqn": "finance-ops:kyc-verifier",
  "message": {
    "role": "user",
    "parts": [{"type": "text", "text": "Verify identity for John Doe, DOB 1990-01-01"}]
  },
  "conversation_id": null
}
```

### 202 Accepted

```json
{
  "task_id": "a2a-task-550e8400",
  "a2a_state": "submitted",
  "agent_fqn": "finance-ops:kyc-verifier",
  "created_at": "2026-04-19T10:00:00.000Z"
}
```

### Error semantics

- `400 Bad Request` — Protocol version mismatch → `{"code": "protocol_version_unsupported", "supported": ["1.0"]}`
- `400 Bad Request` — Payload too large → `{"code": "payload_too_large", "max_bytes": 10485760}`
- `401 Unauthorized` — Missing/invalid/revoked token → `{"code": "authentication_error"}`
- `403 Forbidden` — Principal lacks permission to invoke agent → `{"code": "authorization_error"}`
- `404 Not Found` — Agent FQN not found or non-public → `{"code": "agent_not_found"}`
- `429 Too Many Requests` — Rate limit exceeded → `{"code": "rate_limit_exceeded", "retry_after_ms": 5000}`

---

## GET /api/v1/a2a/tasks/{task_id}

Fetch the current state of an A2A task.

**Authorization**: Bearer JWT (same principal that submitted the task, or platform operator).

### 200 OK

```json
{
  "task_id": "a2a-task-550e8400",
  "a2a_state": "working",
  "agent_fqn": "finance-ops:kyc-verifier",
  "result": null,
  "error_code": null,
  "error_message": null,
  "created_at": "2026-04-19T10:00:00.000Z",
  "updated_at": "2026-04-19T10:00:01.234Z"
}
```

When `a2a_state = "completed"`:
```json
{
  "task_id": "a2a-task-550e8400",
  "a2a_state": "completed",
  "result": {
    "role": "agent",
    "parts": [{"type": "text", "text": "Identity verified. Risk score: 0.12."}]
  }
}
```

When `a2a_state = "failed"`:
```json
{
  "task_id": "a2a-task-550e8400",
  "a2a_state": "failed",
  "error_code": "agent_execution_error",
  "error_message": "The agent was unable to complete the task."
}
```

### Error semantics

- `401 Unauthorized` → `{"code": "authentication_error"}`
- `403 Forbidden` → `{"code": "authorization_error"}`
- `404 Not Found` → `{"code": "task_not_found"}`

---

## DELETE /api/v1/a2a/tasks/{task_id}

Request cancellation of an in-flight A2A task.

**Authorization**: Bearer JWT (same principal or platform operator).

**Notes**:
- If the underlying interaction is mid-step, the task transitions to `cancellation_pending`; it moves to `cancelled` when the interaction reaches a safe point.
- Idempotent: cancelling an already-cancelled task returns 200.

### 200 OK

```json
{
  "task_id": "a2a-task-550e8400",
  "a2a_state": "cancellation_pending"
}
```

### Error semantics

- `401 Unauthorized`, `403 Forbidden`, `404 Not Found` — same codes as above.

---

## POST /api/v1/a2a/tasks/{task_id}/messages

Submit a follow-up message for a multi-turn task in `input_required` state.

**Authorization**: Bearer JWT (same principal that submitted the task).

**Request body**:
```json
{
  "message": {
    "role": "user",
    "parts": [{"type": "text", "text": "Maiden name: Smith. Previous address: 123 Main St."}]
  }
}
```

### 202 Accepted

```json
{
  "task_id": "a2a-task-550e8400",
  "a2a_state": "working"
}
```

### Error semantics

- `400 Bad Request` — Task not in `input_required` state → `{"code": "invalid_task_state", "current_state": "working"}`
- `401`, `403`, `404` — Same as above.

---

## GET /api/v1/a2a/tasks/{task_id}/stream

Subscribe to SSE lifecycle events for an in-flight A2A task.

**Authorization**: Bearer JWT (query param `?token=...` also accepted for SSE clients that cannot set headers).

**Response**: `Content-Type: text/event-stream`

**Notes**:
- Each event is a JSON-serialized A2A lifecycle object.
- The stream closes on terminal state (completed/failed/cancelled).
- Clients MAY reconnect with the `Last-Event-ID` header to resume from the last unseen event (FR-023).

### SSE Event format

```
id: evt-001
event: a2a_task_event
data: {"task_id": "a2a-task-550e8400", "state": "working", "timestamp": "2026-04-19T10:00:01Z"}

id: evt-002
event: a2a_task_event
data: {"task_id": "a2a-task-550e8400", "state": "input_required", "prompt": "Please provide maiden name.", "timestamp": "2026-04-19T10:00:05Z"}

id: evt-003
event: a2a_task_event
data: {"task_id": "a2a-task-550e8400", "state": "completed", "result": {...}, "timestamp": "2026-04-19T10:00:30Z"}
```

### Error semantics

- `401 Unauthorized`, `403 Forbidden`, `404 Not Found` — HTTP error before stream opens.

---

## GET /api/v1/a2a/external-endpoints

List registered external A2A endpoints (operator-only).

**Authorization**: Bearer JWT with platform operator role.

### 200 OK

```json
{
  "items": [
    {
      "id": "550e8400-...",
      "name": "Partner Translation Agent",
      "endpoint_url": "https://partner.example.com/a2a",
      "agent_card_url": "https://partner.example.com/.well-known/agent.json",
      "card_ttl_seconds": 3600,
      "card_is_stale": false,
      "declared_version": "1.0",
      "status": "active",
      "card_cached_at": "2026-04-19T09:00:00Z"
    }
  ],
  "total": 1
}
```

---

## POST /api/v1/a2a/external-endpoints

Register a new external A2A endpoint (operator-only).

**Authorization**: Bearer JWT with platform operator role.

**Request body**:
```json
{
  "name": "Partner Translation Agent",
  "endpoint_url": "https://partner.example.com/a2a",
  "agent_card_url": "https://partner.example.com/.well-known/agent.json",
  "auth_config": {"scheme": "bearer", "credential_ref": "vault:partner-a2a-token"},
  "card_ttl_seconds": 3600
}
```

### 201 Created

```json
{
  "id": "550e8400-...",
  "name": "Partner Translation Agent",
  "endpoint_url": "https://partner.example.com/a2a",
  "status": "active"
}
```

### Error semantics

- `400 Bad Request` — Non-HTTPS endpoint URL → `{"code": "https_required"}`
- `400 Bad Request` — Duplicate endpoint_url in workspace → `{"code": "endpoint_already_registered"}`
- `403 Forbidden` — Not an operator.

---

## DELETE /api/v1/a2a/external-endpoints/{endpoint_id}

Deregister an external A2A endpoint (operator-only). Soft-deletes (status = deleted).

**Authorization**: Bearer JWT with platform operator role.

### 200 OK

```json
{"id": "550e8400-...", "status": "deleted"}
```

---

## Internal Service Interface (not exposed via HTTP)

The `a2a_gateway` bounded context exposes an internal service interface for outbound calls initiated by platform agents:

```python
class A2AGatewayClientService:
    async def invoke_external_agent(
        self,
        *,
        calling_agent_id: UUID,
        calling_agent_fqn: str,
        external_endpoint_id: UUID,
        message: dict,
        workspace_id: UUID,
        execution_id: UUID | None,
        session: AsyncSession,
    ) -> A2ATask:
        """
        Policy-checked outbound A2A call.
        Returns the A2ATask record (caller polls for result or subscribes to stream).
        Raises A2APolicyDeniedError on policy block.
        Raises A2AUnsupportedCapabilityError on Agent Card incompatibility.
        """
```
