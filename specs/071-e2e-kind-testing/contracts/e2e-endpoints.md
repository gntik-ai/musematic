# HTTP Contracts: `/api/v1/_e2e/*` Dev-Only Endpoints

**Feature**: 071-e2e-kind-testing
**Date**: 2026-04-20
**Module**: `apps/control-plane/src/platform/testing/router_e2e.py`

All endpoints below are mounted **only when `FEATURE_E2E_MODE=true`**. When the flag is false, FastAPI does not register any of these paths and all return HTTP 404 Not Found (FR-022, SC-007). When the flag is true, every endpoint additionally requires an admin bearer token OR a service-account token with the `e2e` scope (FR-023, D-006).

## Common Response Codes

| Code | Meaning |
|---|---|
| 200 | Success |
| 400 | Invalid request (e.g., chaos target outside allowed namespace) |
| 401 | Missing/invalid bearer token |
| 403 | Token lacks admin role and `e2e` scope |
| 404 | Endpoint not registered — `FEATURE_E2E_MODE` is off |
| 422 | Request body validation failure (Pydantic) |
| 500 | Unexpected platform error (seed failure, K8s API error) |

## Authentication

All endpoints depend on `Depends(require_admin_or_e2e_scope)` which:

1. Parses `Authorization: Bearer <token>` header.
2. Validates token via existing JWT middleware.
3. Checks caller has role `platform_admin` OR token scopes contain `e2e`.
4. Returns 401 (missing token) or 403 (insufficient privilege) on failure.

---

## 1. `POST /api/v1/_e2e/seed`

**Purpose**: Trigger idempotent seeding of baseline entities.

**Request body** (`schemas_e2e.SeedRequest`):

```json
{
  "scope": "all"
}
```

- `scope`: one of `"all" | "users" | "namespaces" | "agents" | "tools" | "policies" | "certifiers" | "fleets" | "workspace_goals"`. Default `"all"`.

**Response 200** (`schemas_e2e.SeedResponse`):

```json
{
  "seeded": { "users": 5, "namespaces": 3, "agents": 6, "tools": 2, "policies": 3, "certifiers": 2, "fleets": 1, "workspace_goals": 4 },
  "skipped": { "users": 0, "namespaces": 0, "agents": 0, "tools": 0, "policies": 0, "certifiers": 0, "fleets": 0, "workspace_goals": 0 },
  "duration_ms": 1234
}
```

- `seeded[k]`: count of entities inserted this call
- `skipped[k]`: count of entities that already existed (idempotent skip)

**Notes**: Full `scope=all` run must complete in < 60s on the reference runner.

---

## 2. `POST /api/v1/_e2e/reset`

**Purpose**: Wipe E2E-scoped rows across all stores (workspaces named `test-%`, users emailed `*@e2e.test`, executions linked to seeded workspaces, etc.).

**Request body** (`schemas_e2e.ResetRequest`):

```json
{
  "scope": "all",
  "include_baseline": false
}
```

- `scope`: one of `"all" | "workspaces" | "executions" | "kafka_consumer_offsets"`. Default `"all"`.
- `include_baseline`: when `true`, also deletes seeded users/agents/namespaces. Default `false` (baseline preserved across resets).

**Response 200** (`schemas_e2e.ResetResponse`):

```json
{
  "deleted": { "workspaces": 3, "executions": 12, "interactions": 47, "kafka_consumer_offsets": 0 },
  "preserved_baseline": true,
  "duration_ms": 800
}
```

**Safety**: The reset service layer refuses to execute if any row's scope is not clearly E2E (workspace name without `test-` prefix, user email not ending `@e2e.test`). Returns 500 with error code `E2E_SCOPE_VIOLATION` if detected — this prevents accidental cross-environment resets.

---

## 3. `POST /api/v1/_e2e/chaos/kill-pod`

**Purpose**: Kill one or more pods matching a label selector to simulate mid-execution failure.

**Request body** (`schemas_e2e.ChaosKillPodRequest`):

```json
{
  "namespace": "platform-execution",
  "label_selector": "app.kubernetes.io/name=runtime-controller",
  "count": 1
}
```

**Constraints**:

- `namespace` MUST be one of `platform-execution`, `platform-data` (FR-024). Any other namespace returns 400 with error code `NAMESPACE_NOT_ALLOWED`.
- `count` in range `[1, 3]`.
- If fewer than `count` pods match, kills all that match and returns the actual count.

**Response 200** (`schemas_e2e.ChaosKillPodResponse`):

```json
{
  "killed": [
    { "pod": "runtime-controller-abc123-xyz", "namespace": "platform-execution", "at": "2026-04-20T10:15:00Z" }
  ],
  "not_found": 0
}
```

**Response 400**: namespace outside allowed list.

**Backend**: uses `kubernetes` Python client with in-cluster ServiceAccount `e2e-chaos-sa` (Role: `delete pods` in allowed namespaces only; D-007).

---

## 4. `POST /api/v1/_e2e/chaos/partition-network`

**Purpose**: Install a NetworkPolicy that partitions two namespaces; auto-deletes after TTL.

**Request body** (`schemas_e2e.ChaosPartitionRequest`):

```json
{
  "from_namespace": "platform-execution",
  "to_namespace": "platform-data",
  "ttl_seconds": 30
}
```

**Constraints**:

- Both namespaces in `{platform-execution, platform-data}` only.
- `ttl_seconds` in range `[5, 300]`.

**Response 200** (`schemas_e2e.ChaosPartitionResponse`):

```json
{
  "network_policy_name": "e2e-partition-abc123",
  "applied_at": "2026-04-20T10:15:00Z",
  "expires_at": "2026-04-20T10:15:30Z"
}
```

**Teardown**: An APScheduler task running in the control-plane `scheduler` profile scans for `NetworkPolicy` objects with label `e2e-chaos=partition` and deletes those past their `expires_at` annotation. If the scheduler is down, the NetworkPolicy persists — chaos test fixtures MUST also `try/finally` delete the NP by name.

---

## 5. `POST /api/v1/_e2e/mock-llm/set-response`

**Purpose**: Push a response onto the mock LLM FIFO queue for a given prompt template.

**Request body** (`schemas_e2e.MockLLMSetRequest`):

```json
{
  "prompt_pattern": "agent_response",
  "response": "OK",
  "streaming_chunks": ["O", "K"]
}
```

- `prompt_pattern`: must match a key in `common/llm/mock_provider.py::PROMPT_TEMPLATES`. Returns 400 if unknown.
- `response`: the full response text.
- `streaming_chunks`: optional; if present, overrides single-shot with this chunk sequence for SSE streaming.

**Response 200**:

```json
{
  "queue_depth": { "agent_response": 1, "judge_verdict": 0, "tool_selector": 0 }
}
```

**Cross-pod broadcast**: the request publishes to Redis channel `e2e:mock_llm:set` so every control-plane pod's mock provider enqueues the response. This keeps ordering deterministic per prompt template across replicas.

---

## 6. `GET /api/v1/_e2e/kafka/events`

**Purpose**: Read events published to a Kafka topic during a test window for assertion.

**Query params**:

- `topic` (required): Kafka topic name; must be in the registered topic set (constitution's Kafka Topics Registry).
- `since` (required): ISO 8601 timestamp.
- `until` (optional): ISO 8601 timestamp; defaults to now.
- `limit` (optional): 1–1000; defaults to 100.
- `key` (optional): filter by partition key.

**Response 200** (`schemas_e2e.KafkaEventsResponse`):

```json
{
  "events": [
    {
      "topic": "execution.events",
      "partition": 0,
      "offset": 12345,
      "key": "exec-abc",
      "timestamp": "2026-04-20T10:15:05Z",
      "headers": { "correlation_id": "corr-abc" },
      "payload": { "event_type": "execution.started", "execution_id": "exec-abc", "..." : "..." }
    }
  ],
  "count": 1,
  "truncated": false
}
```

**Backend**: uses a dedicated aiokafka consumer with group `e2e-observer-{hostname}` (isolated from production consumers). Consumer seeks to the timestamp, reads up to `limit` events, returns them synchronously. Timeout 10s.

---

## Pod mount & 404 behavior

In `apps/control-plane/src/platform/main.py`:

```python
if settings.feature_e2e_mode:
    from platform.testing.router_e2e import router as e2e_router
    app.include_router(e2e_router, prefix="/api/v1/_e2e", tags=["_e2e"])
```

When `feature_e2e_mode=False`, the router is not imported and FastAPI returns a default 404 for any matching path. This is verified by a static contract test (`tests/unit/testing/test_router_e2e_404_when_flag_off.py`) that enumerates every endpoint above and asserts HTTP 404 via an `httpx.AsyncClient` against a test app with the flag off.

---

## Error shape

All non-2xx responses use the platform's canonical error envelope:

```json
{
  "error": {
    "code": "E2E_SCOPE_VIOLATION",
    "message": "Reset scope violated — row X does not match E2E prefix",
    "details": { "table": "workspaces", "row_id": "..." }
  }
}
```

Error codes introduced by this feature:

| Code | Endpoint | HTTP |
|---|---|---|
| `E2E_SCOPE_VIOLATION` | `/reset` | 500 |
| `NAMESPACE_NOT_ALLOWED` | `/chaos/kill-pod`, `/chaos/partition-network` | 400 |
| `UNKNOWN_PROMPT_PATTERN` | `/mock-llm/set-response` | 400 |
| `TOPIC_NOT_REGISTERED` | `/kafka/events` | 400 |
| `E2E_MODE_DISABLED` | (all) | 404 (via missing route, not this code — listed here for documentation) |
