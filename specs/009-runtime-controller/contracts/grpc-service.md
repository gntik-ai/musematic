# Contract: RuntimeControlService gRPC Interface

**Feature**: 009-runtime-controller  
**Date**: 2026-04-10  
**Type**: gRPC Service Contract  
**Proto source**: `services/runtime-controller/proto/runtime_controller.proto`  
**Go package**: `services/runtime-controller/api/grpc/v1`

---

## 1. Service Endpoint

| Property | Value |
|----------|-------|
| Service name | `musematic-runtime-controller` |
| Namespace | `platform-execution` |
| gRPC endpoint | `musematic-runtime-controller.platform-execution:50051` |
| Protocol | gRPC over TLS (production) / gRPC plaintext (development) |
| Auth | mTLS (production) / none (development) |
| Python client | `apps/control-plane/src/platform/common/clients/runtime_controller.py` (grpcio stub) |

---

## 2. RPC Methods

### 2.1 `LaunchRuntime`

```
LaunchRuntimeRequest  → LaunchRuntimeResponse
```

**Purpose**: Launch an agent runtime pod from a runtime contract. Persists a task plan record before creating the pod. Dispatches from warm pool if available.

**Request fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `contract.agent_revision` | string | ✅ | Agent package version identifier |
| `contract.model_binding` | string | ✅ | Model provider + model ID (JSON) |
| `contract.correlation_context` | CorrelationContext | ✅ | workspace_id, execution_id (required), others optional |
| `contract.resource_limits` | ResourceLimits | ✅ | CPU and memory requests/limits |
| `contract.secret_refs` | string[] | — | Kubernetes Secret names to resolve |
| `contract.env_vars` | map<string,string> | — | Additional environment variables (non-secret) |
| `contract.task_plan_json` | string | — | Serialized task plan payload (persisted before launch) |
| `contract.step_id` | string | — | Step identifier for task plan record |

**Response fields**:

| Field | Type | Description |
|-------|------|-------------|
| `runtime_id` | string (UUID) | Controller-assigned runtime identifier |
| `state` | RuntimeState | `PENDING` (cold start) or `RUNNING` (warm start) |
| `warm_start` | bool | `true` if dispatched from warm pool |

**Error codes**:

| gRPC Code | Condition |
|-----------|-----------|
| `ALREADY_EXISTS` | A runtime already exists for this `execution_id` |
| `INVALID_ARGUMENT` | Missing required fields in contract |
| `UNAVAILABLE` | Kubernetes API unreachable |
| `FAILED_PRECONDITION` | Vault/secret resolution failed |

**Timing**: Cold start < 10s; warm start < 2s.

---

### 2.2 `GetRuntime`

```
GetRuntimeRequest → GetRuntimeResponse
```

**Purpose**: Retrieve current runtime state and metadata.

**Request**: `execution_id` (string, required)

**Response**: `RuntimeInfo` with runtime_id, execution_id, state, failure_reason, pod_name, launched_at, last_heartbeat_at, correlation_context.

**Error codes**: `NOT_FOUND` if no runtime exists for the execution_id.

---

### 2.3 `PauseRuntime`

```
PauseRuntimeRequest → PauseRuntimeResponse
```

**Purpose**: Request graceful pause of a running runtime.

**Request**: `execution_id` (string, required)

**Response**: `state` (RuntimeState) — new state after pause attempt.

**Behavior**: Sends SIGTSTP to the runtime process. If the process does not support pause, the operation is a no-op and the runtime remains `RUNNING`. The response reflects the actual resulting state.

**Error codes**: `NOT_FOUND`, `FAILED_PRECONDITION` (runtime not in `RUNNING` state).

---

### 2.4 `ResumeRuntime`

```
ResumeRuntimeRequest → ResumeRuntimeResponse
```

**Purpose**: Resume a paused runtime.

**Request**: `execution_id` (string, required)

**Error codes**: `NOT_FOUND`, `FAILED_PRECONDITION` (runtime not in `PAUSED` state).

---

### 2.5 `StopRuntime`

```
StopRuntimeRequest → StopRuntimeResponse
```

**Purpose**: Gracefully stop a runtime (SIGTERM + grace period), then force kill if needed.

**Request fields**:

| Field | Type | Description |
|-------|------|-------------|
| `execution_id` | string | Required |
| `grace_period_seconds` | int32 | Override default grace period (default: 30s). 0 = immediate force kill. |

**Response**:

| Field | Description |
|-------|-------------|
| `state` | `STOPPED` (clean) or `FORCE_STOPPED` (force killed) |
| `force_killed` | `true` if grace period was exceeded |

**Behavior**: The stop operation is synchronous — the RPC returns after the pod is confirmed terminated. Timeout: `grace_period_seconds` + 10s buffer.

**Error codes**: `NOT_FOUND`, `DEADLINE_EXCEEDED` if pod termination confirmation times out.

---

### 2.6 `StreamRuntimeEvents`

```
StreamRuntimeEventsRequest → stream RuntimeEvent
```

**Purpose**: Server-side streaming delivery of runtime lifecycle events.

**Request fields**:

| Field | Type | Description |
|-------|------|-------------|
| `execution_id` | string | Required — subscribe to events for this runtime |
| `since` | Timestamp | Optional — replay events from this timestamp (from `runtime_events` table) |

**Stream behavior**:
- The server pushes `RuntimeEvent` messages as state transitions occur.
- The stream remains open until the client cancels or the runtime reaches a terminal state (`STOPPED`, `FORCE_STOPPED`, `FAILED`). After a terminal state event is sent, the server closes the stream.
- Multiple concurrent subscribers for the same `execution_id` are supported.

**Event fields**:

| Field | Description |
|-------|-------------|
| `event_id` | UUID |
| `runtime_id` | Controller-assigned runtime UUID |
| `execution_id` | Execution UUID |
| `event_type` | One of: LAUNCHED, PAUSED, RESUMED, STOPPED, FORCE_STOPPED, FAILED, HEARTBEAT, ARTIFACT_COLLECTED, DRIFT_DETECTED |
| `occurred_at` | Timestamp |
| `new_state` | RuntimeState after the transition |
| `details_json` | Additional context (e.g., failure reason, artifact paths) |

**Error codes**: `NOT_FOUND` (no runtime for execution_id), `CANCELLED` (client cancelled).

---

### 2.7 `CollectRuntimeArtifacts`

```
CollectRuntimeArtifactsRequest → CollectRuntimeArtifactsResponse
```

**Purpose**: Collect output artifacts from the runtime pod and upload to object storage.

**Request**: `execution_id` (string, required)

**Response**:

| Field | Description |
|-------|-------------|
| `artifacts` | List of `ArtifactEntry` (object_key, filename, size_bytes, content_type, collected_at) |
| `complete` | `true` if all artifacts were collected successfully; `false` if partial |

**Object storage path**: `artifacts/{execution_id}/{filename}`

**Error codes**: `NOT_FOUND`, `UNAVAILABLE` (object storage unreachable).

---

## 3. Python Client Stub Usage

```python
# apps/control-plane/src/platform/common/clients/runtime_controller.py
import grpc
from platform.grpc_stubs.runtime_controller_pb2_grpc import RuntimeControlServiceStub
from platform.grpc_stubs.runtime_controller_pb2 import (
    LaunchRuntimeRequest, RuntimeContract, CorrelationContext, ResourceLimits
)

async def launch_runtime(execution_id: str, agent_revision: str) -> str:
    channel = grpc.aio.insecure_channel("musematic-runtime-controller.platform-execution:50051")
    stub = RuntimeControlServiceStub(channel)
    response = await stub.LaunchRuntime(
        LaunchRuntimeRequest(
            contract=RuntimeContract(
                agent_revision=agent_revision,
                correlation_context=CorrelationContext(
                    workspace_id="ws-123",
                    execution_id=execution_id,
                ),
                resource_limits=ResourceLimits(
                    cpu_request="500m", cpu_limit="2",
                    memory_request="256Mi", memory_limit="1Gi",
                ),
            )
        )
    )
    return response.runtime_id
```

---

## 4. Kafka Events

Events emitted to `runtime.lifecycle` topic (lifecycle) and `monitor.alerts` topic (drift).

**Canonical event envelope**:
```json
{
  "event_id": "uuid",
  "event_type": "runtime.launched",
  "source": "runtime-controller",
  "occurred_at": "2026-04-10T05:00:00Z",
  "correlation_context": {
    "workspace_id": "ws-123",
    "execution_id": "exec-uuid",
    "trace_id": "trace-uuid"
  },
  "payload": {
    "runtime_id": "rt-uuid",
    "state": "running",
    "warm_start": false,
    "pod_name": "runtime-exec-uuid-short"
  }
}
```

**Event types on `runtime.lifecycle`**: `runtime.launched`, `runtime.paused`, `runtime.resumed`, `runtime.stopped`, `runtime.force_stopped`, `runtime.failed`, `runtime.heartbeat_timeout`, `runtime.artifact_collected`

**Event types on `monitor.alerts`**: `runtime.drift_detected` (orphan terminated, pod disappeared, state mismatch)

---

## 5. Network Access

| Source Namespace | Port | Purpose |
|-----------------|------|---------|
| `platform-control` | 50051/gRPC | Control plane calls (LaunchRuntime, StopRuntime, etc.) |
| `platform-execution` | 50051/gRPC | Execution engine calls (StreamRuntimeEvents, GetRuntime) |
| `platform-observability` | 8080/HTTP | Prometheus metrics scrape |
| `platform-execution` | internal | Controller → Kubernetes API (pod management) |
| All others | — | Blocked by NetworkPolicy |
