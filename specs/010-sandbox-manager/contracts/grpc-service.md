# Contract: SandboxService gRPC Interface

**Feature**: 010-sandbox-manager  
**Date**: 2026-04-10  
**Type**: gRPC Service Contract  
**Proto source**: `services/sandbox-manager/proto/sandbox_manager.proto`  
**Go package**: `services/sandbox-manager/api/grpc/v1`

---

## 1. Service Endpoint

| Property | Value |
|----------|-------|
| Service name | `musematic-sandbox-manager` |
| Namespace | `platform-execution` |
| gRPC endpoint | `musematic-sandbox-manager.platform-execution:50053` |
| Protocol | gRPC over TLS (production) / gRPC plaintext (development) |
| Auth | mTLS (production) / none (development) |
| Python client | `apps/control-plane/src/platform/common/clients/sandbox_manager.py` (grpcio stub) |

---

## 2. RPC Methods

### 2.1 `CreateSandbox`

```
CreateSandboxRequest → CreateSandboxResponse
```

**Purpose**: Create an isolated sandbox pod from a named template with security hardening, resource limits, and optional network access.

**Request fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `template_name` | string | yes | One of: `python3.12`, `node20`, `go1.22`, `code-as-reasoning` |
| `correlation` | CorrelationContext | yes | workspace_id, execution_id (required) |
| `resource_overrides` | ResourceLimits | — | Override template default resource limits |
| `timeout_override` | int32 | — | Override default step timeout (seconds) |
| `network_enabled` | bool | — | Enable network egress (default: false) |
| `egress_allowlist` | string[] | — | Allowed egress domains/CIDRs (only if network_enabled) |
| `env_vars` | map<string,string> | — | Additional environment variables |
| `pip_packages` | string[] | — | Python packages to install (python templates only) |
| `npm_packages` | string[] | — | Node packages to install (node template only) |

**Response fields**:

| Field | Type | Description |
|-------|------|-------------|
| `sandbox_id` | string (UUID) | Controller-assigned sandbox identifier |
| `state` | SandboxState | `CREATING` (pod being created) |

**Behavior**: The RPC returns immediately with `CREATING` state. The caller should poll or stream events to detect `READY` state. If `pip_packages` or `npm_packages` are specified, packages are installed via exec after the pod is running, before transitioning to `READY`.

**Error codes**:

| gRPC Code | Condition |
|-----------|-----------|
| `INVALID_ARGUMENT` | Unknown template name, missing required fields |
| `RESOURCE_EXHAUSTED` | Maximum concurrent sandboxes reached |
| `UNAVAILABLE` | Kubernetes API unreachable |

**Timing**: Pod creation + readiness: < 15 seconds (cold start).

---

### 2.2 `ExecuteSandboxStep`

```
ExecuteSandboxStepRequest → ExecuteSandboxStepResponse
```

**Purpose**: Execute a code snippet inside a ready sandbox and return the result.

**Request fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sandbox_id` | string | yes | Target sandbox |
| `code` | string | yes | Code to execute |
| `timeout_override` | int32 | — | Per-step timeout (seconds); overrides sandbox default |

**Response fields**:

| Field | Type | Description |
|-------|------|-------------|
| `result.stdout` | string | Standard output (truncated at `MAX_OUTPUT_SIZE`) |
| `result.stderr` | string | Standard error (truncated at `MAX_OUTPUT_SIZE`) |
| `result.exit_code` | int32 | Process exit code |
| `result.duration` | Duration | Actual execution time |
| `result.timed_out` | bool | True if execution was killed by timeout |
| `result.oom_killed` | bool | True if process was killed by OOM |
| `result.structured_output` | string | Parsed JSON output (code-as-reasoning template only) |
| `result.output_truncated` | bool | True if stdout/stderr was truncated |
| `step_num` | int32 | Sequential step number (1-based) |

**Behavior**: The RPC blocks until execution completes, times out, or the sandbox fails. The sandbox transitions to `EXECUTING` during execution and back to `READY` after. Multiple concurrent `ExecuteSandboxStep` calls to the same sandbox are serialized — only one step executes at a time; additional calls block.

**Error codes**:

| gRPC Code | Condition |
|-----------|-----------|
| `NOT_FOUND` | No sandbox with this ID |
| `FAILED_PRECONDITION` | Sandbox not in `READY` state |
| `DEADLINE_EXCEEDED` | Execution timeout (also sets `result.timed_out`) |

---

### 2.3 `StreamSandboxLogs`

```
StreamSandboxLogsRequest → stream SandboxLogLine
```

**Purpose**: Server-side streaming of sandbox stdout/stderr in real-time.

**Request fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sandbox_id` | string | yes | Target sandbox |
| `follow` | bool | — | If true, stream continuously; if false, return buffered logs and close |

**Stream behavior**:
- Each `SandboxLogLine` contains the line content, stream name (`stdout` or `stderr`), and timestamp.
- When `follow=true`, the stream remains open until the sandbox reaches a terminal state or the client cancels.
- Multiple concurrent subscribers are supported via fan-out.

**Error codes**: `NOT_FOUND`, `CANCELLED`.

---

### 2.4 `TerminateSandbox`

```
TerminateSandboxRequest → TerminateSandboxResponse
```

**Purpose**: Terminate a sandbox pod and clean up resources.

**Request fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sandbox_id` | string | yes | Target sandbox |
| `grace_period_seconds` | int32 | — | Grace period (default: 5s). 0 = immediate. |

**Response**:

| Field | Description |
|-------|-------------|
| `state` | `TERMINATED` |

**Behavior**: Synchronous — returns after pod deletion is confirmed.

**Error codes**: `NOT_FOUND`, `DEADLINE_EXCEEDED`.

---

### 2.5 `CollectSandboxArtifacts`

```
CollectSandboxArtifactsRequest → CollectSandboxArtifactsResponse
```

**Purpose**: Collect output files from `/output/` in the sandbox pod and upload to object storage.

**Request**: `sandbox_id` (string, required)

**Response**:

| Field | Description |
|-------|-------------|
| `artifacts` | List of `ArtifactEntry` (object_key, filename, size_bytes, content_type, collected_at) |
| `complete` | `true` if all artifacts collected successfully |

**Object storage path**: `sandbox-artifacts/{execution_id}/{sandbox_id}/{filename}`

**Error codes**: `NOT_FOUND`, `UNAVAILABLE` (object storage unreachable), `FAILED_PRECONDITION` (sandbox already terminated, pod gone).

---

## 3. Python Client Stub Usage

```python
# apps/control-plane/src/platform/common/clients/sandbox_manager.py
import grpc
from platform.grpc_stubs.sandbox_manager_pb2_grpc import SandboxServiceStub
from platform.grpc_stubs.sandbox_manager_pb2 import (
    CreateSandboxRequest, ExecuteSandboxStepRequest, CorrelationContext
)

async def execute_code(execution_id: str, code: str) -> dict:
    channel = grpc.aio.insecure_channel("musematic-sandbox-manager.platform-execution:50053")
    stub = SandboxServiceStub(channel)

    # Create sandbox
    create_resp = await stub.CreateSandbox(
        CreateSandboxRequest(
            template_name="python3.12",
            correlation=CorrelationContext(
                workspace_id="ws-123",
                execution_id=execution_id,
            ),
        )
    )

    # Wait for ready (poll or stream events)
    sandbox_id = create_resp.sandbox_id

    # Execute code
    exec_resp = await stub.ExecuteSandboxStep(
        ExecuteSandboxStepRequest(
            sandbox_id=sandbox_id,
            code=code,
        )
    )

    return {
        "stdout": exec_resp.result.stdout,
        "stderr": exec_resp.result.stderr,
        "exit_code": exec_resp.result.exit_code,
    }
```

---

## 4. Kafka Events

Events emitted to `sandbox.events` topic (keyed by `sandbox_id`).

**Canonical event envelope**:
```json
{
  "event_id": "uuid",
  "event_type": "sandbox.created",
  "source": "sandbox-manager",
  "occurred_at": "2026-04-10T05:00:00Z",
  "correlation_context": {
    "workspace_id": "ws-123",
    "execution_id": "exec-uuid",
    "trace_id": "trace-uuid"
  },
  "payload": {
    "sandbox_id": "sb-uuid",
    "template": "python3.12",
    "state": "creating"
  }
}
```

**Event types on `sandbox.events`**: `sandbox.created`, `sandbox.ready`, `sandbox.step_started`, `sandbox.step_completed`, `sandbox.completed`, `sandbox.failed`, `sandbox.terminated`, `sandbox.artifact_collected`

---

## 5. Network Access

| Source Namespace | Port | Purpose |
|-----------------|------|---------|
| `platform-control` | 50053/gRPC | Control plane calls (CreateSandbox, ExecuteSandboxStep, etc.) |
| `platform-execution` | 50053/gRPC | Runtime controller calls (code-as-reasoning) |
| `platform-observability` | 8080/HTTP | Prometheus metrics scrape |
| `platform-execution` | internal | Controller → Kubernetes API (pod management + exec) |
| All others | — | Blocked by NetworkPolicy |
