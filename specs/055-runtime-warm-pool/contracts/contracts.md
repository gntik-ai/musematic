# Interface Contracts: Runtime Warm Pool and Secrets Injection

**Feature**: `specs/055-runtime-warm-pool/spec.md`
**Date**: 2026-04-18

---

## Contract 1: GET /api/v1/runtime/warm-pool/status

**Auth**: Bearer JWT, `platform_admin` role required (403 otherwise)

**Request**:
```
GET /api/v1/runtime/warm-pool/status?workspace_id=<uuid>&agent_type=<str>
```
Both query params are optional. Omitting both returns all configured pool keys.

**Response 200**:
```json
{
  "keys": [
    {
      "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
      "agent_type": "python-3.12",
      "target_size": 5,
      "available_count": 3,
      "dispatched_count": 2,
      "warming_count": 0,
      "last_dispatch_at": "2026-04-18T12:00:00Z"
    }
  ]
}
```
Empty `keys` array if no targets are configured.

**Response 403**: `{"detail": "Forbidden"}` — caller lacks `platform_admin`.

---

## Contract 2: PUT /api/v1/runtime/warm-pool/config

**Auth**: Bearer JWT, `platform_admin` role required (403 otherwise)

**Request body**:
```json
{
  "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_type": "python-3.12",
  "target_size": 5
}
```
`target_size` must be ≥ 0. Setting to 0 disables the pool for that key (FR-015).

**Response 200**:
```json
{
  "accepted": true,
  "message": ""
}
```
`accepted=true` means the target has been persisted. The replenisher converges on the next tick (≤30 s).

**Response 422**: Pydantic validation error (negative `target_size`, missing fields).
**Response 403**: Caller lacks `platform_admin`.

---

## Contract 3: gRPC WarmPoolStatus

**Service**: `RuntimeControlService` (port 50051)
**Method**: `WarmPoolStatus(WarmPoolStatusRequest) returns (WarmPoolStatusResponse)`

**Request**:
```protobuf
WarmPoolStatusRequest {
  workspace_id: ""      // empty = all workspaces
  agent_type: ""        // empty = all agent types
}
```

**Response**:
```protobuf
WarmPoolStatusResponse {
  keys: [
    WarmPoolKeyStatus {
      workspace_id: "550e8400..."
      agent_type: "python-3.12"
      target_size: 5
      available_count: 3
      dispatched_count: 2
      warming_count: 0
      last_dispatch_at: { seconds: 1713434400, nanos: 0 }
    }
  ]
}
```

**Error codes**: `NOT_FOUND` if workspace_id/agent_type combination is non-empty and has no configured target.

---

## Contract 4: gRPC WarmPoolConfig

**Service**: `RuntimeControlService` (port 50051)
**Method**: `WarmPoolConfig(WarmPoolConfigRequest) returns (WarmPoolConfigResponse)`

**Request**:
```protobuf
WarmPoolConfigRequest {
  workspace_id: "550e8400..."
  agent_type: "python-3.12"
  target_size: 5      // 0 disables pool for this key
}
```

**Response**:
```protobuf
WarmPoolConfigResponse {
  accepted: true
  message: ""
}
```

**Error codes**: `INVALID_ARGUMENT` if `target_size < 0` or workspace_id/agent_type are empty strings.

---

## Contract 5: LaunchRuntime — extended with `prefer_warm`

**Existing RPC**: `LaunchRuntime(LaunchRuntimeRequest) returns (LaunchRuntimeResponse)`

**Extension** (additive — existing fields unchanged):
- `LaunchRuntimeRequest` gains optional field `bool prefer_warm = <next_field_number>`. Default `false` (proto3 zero value); Python client always sends `true`.
- `LaunchRuntimeResponse.warm_start` (already exists) — returns `true` if served from pool, `false` if cold start.

**No breaking change**: Callers that do not set `prefer_warm` continue to receive cold-start behavior (pool path not invoked).

---

## Contract 6: `monitor.alerts` — Prompt Secret Detection event

**Topic**: `monitor.alerts` (existing Kafka topic)
**Producer**: Python control plane execution scheduler (`_prompt_secret_preflight`)
**Event type**: `"prompt_secret_detected"`

**Payload** (standard `EventEnvelope` format):
```json
{
  "event_id": "<uuid>",
  "event_type": "prompt_secret_detected",
  "correlation_id": "<correlation_id>",
  "workspace_id": "<uuid>",
  "created_at": "<iso8601>",
  "data": {
    "secret_type": "bearer_token",
    "agent_fqn": "acme/agent/summarizer@v1",
    "execution_id": "<uuid>",
    "step_id": "<str>"
  }
}
```

**Consumer**: Operator dashboard WebSocket channel (`monitor.alerts`), existing alert display.

---

## Contract 7: `PolicyBlockedActionRecord` for prompt secret detections

**Existing model**: `apps/control-plane/src/platform/policies/models.py`
**New record created by**: `execution/scheduler._prompt_secret_preflight()`

```python
PolicyBlockedActionRecord(
    policy_basis      = "prompt_secret_detected:bearer_token",
    component         = EnforcementComponent.execution,
    agent_id          = <uuid>,
    agent_fqn         = "acme/agent/summarizer@v1",
    workspace_id      = <uuid>,
    execution_id      = <uuid>,
    policy_basis_detail = json.dumps({"secret_type": "bearer_token", "step_id": step.step_id}),
)
```

Queryable via `GET /api/v1/policies/blocked-actions?component=execution`.
