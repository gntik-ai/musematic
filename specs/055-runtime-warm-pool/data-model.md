# Data Model: Runtime Warm Pool and Secrets Injection

**Feature**: `specs/055-runtime-warm-pool/spec.md`
**Date**: 2026-04-18

---

## New Database Table: `runtime_warm_pool_targets`

**File**: `apps/control-plane/migrations/versions/043_runtime_warm_pool_targets.py`
**Purpose**: Persist warm pool target sizes per `(workspace_id, agent_type)` key so targets survive Runtime Controller restarts.

```
runtime_warm_pool_targets
├── id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
├── workspace_id    UUID NOT NULL
├── agent_type      VARCHAR(255) NOT NULL
├── target_size     INTEGER NOT NULL DEFAULT 0
├── updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
└── UNIQUE (workspace_id, agent_type)
```

**Notes**:
- `target_size = 0` means pool is disabled for this key (FR-015, backward compatible).
- `updated_at` is set on every upsert; no `created_at` needed (only current state matters).
- Go `WarmPoolConfig` handler uses PostgreSQL `INSERT ... ON CONFLICT (workspace_id, agent_type) DO UPDATE SET target_size = $3, updated_at = now()`.
- Go `WarmPoolStatus` handler JOINs this table against the in-memory manager state for live counts.

---

## Go: New Prometheus Metrics

**File**: `services/runtime-controller/pkg/metrics/metrics.go`
**Modification**: Add 6 new metric fields + constructor initializers (additive; no existing metric changed).

| Metric Name | Type | Labels | Purpose |
|---|---|---|---|
| `warm_pool_available` | GaugeVec | workspace_id, agent_type | Ready pods currently in pool |
| `warm_pool_target` | GaugeVec | workspace_id, agent_type | Configured target size |
| `warm_pool_warming` | GaugeVec | workspace_id, agent_type | Pods being pre-warmed |
| `warm_pool_dispatches_total` | CounterVec | workspace_id, agent_type | Cumulative warm dispatches |
| `cold_start_count_total` | CounterVec | workspace_id, agent_type | Cumulative cold starts |
| `warm_dispatch_latency_ms` | HistogramVec | workspace_id, agent_type | Dispatch-to-running latency (ms); buckets: 100, 250, 500, 1000, 2000, 5000 |

**New methods on `Metrics` struct**:
- `SetWarmPoolAvailable(workspaceID, agentType string, count float64)`
- `SetWarmPoolTarget(workspaceID, agentType string, count float64)`
- `SetWarmPoolWarming(workspaceID, agentType string, count float64)`
- `IncWarmPoolDispatches(workspaceID, agentType string)`
- `IncColdStart(workspaceID, agentType string)`
- `ObserveWarmDispatchLatency(workspaceID, agentType string, ms float64)`

---

## Go: New Proto Messages + RPCs

**File**: `services/runtime-controller/proto/runtime_controller.proto`
**Modification**: Add 5 new messages + 2 new RPCs to `RuntimeControlService` (additive; 7 existing RPCs unchanged).

```protobuf
// New messages (append after existing message definitions)
message WarmPoolStatusRequest {
  string workspace_id = 1;  // empty string = return all keys
  string agent_type   = 2;  // empty string = return all agent types
}

message WarmPoolKeyStatus {
  string workspace_id     = 1;
  string agent_type       = 2;
  int32  target_size      = 3;
  int32  available_count  = 4;
  int32  dispatched_count = 5;
  int32  warming_count    = 6;
  google.protobuf.Timestamp last_dispatch_at = 7;
}

message WarmPoolStatusResponse {
  repeated WarmPoolKeyStatus keys = 1;
}

message WarmPoolConfigRequest {
  string workspace_id = 1;
  string agent_type   = 2;
  int32  target_size  = 3;
}

message WarmPoolConfigResponse {
  bool   accepted = 1;
  string message  = 2;
}
```

**New RPCs**:
```protobuf
service RuntimeControlService {
  // ... existing 7 RPCs ...
  rpc WarmPoolStatus(WarmPoolStatusRequest) returns (WarmPoolStatusResponse);
  rpc WarmPoolConfig(WarmPoolConfigRequest) returns (WarmPoolConfigResponse);
}
```

---

## Go: gRPC Handler Implementation

**File**: `services/runtime-controller/internal/server/server.go` (or `warm_pool_handler.go` if server.go is large)
**Modification**: Implement `WarmPoolStatus` and `WarmPoolConfig` RPC methods on the existing gRPC server struct.

**WarmPoolStatus handler**:
- Query `runtime_warm_pool_targets` for target sizes (filter by workspace_id/agent_type if non-empty).
- For each row, call `manager.Count(key)` for live `available_count`.
- Emit `WarmPoolKeyStatus` entries; return `WarmPoolStatusResponse`.

**WarmPoolConfig handler**:
- Validate `target_size >= 0`.
- Upsert into `runtime_warm_pool_targets` (INSERT ... ON CONFLICT DO UPDATE).
- Signal replenisher to re-read targets on the next tick (channel or atomic flag).
- Return `WarmPoolConfigResponse{accepted: true}`.

---

## Python: New Schema Definitions

**File**: `apps/control-plane/src/platform/execution/schemas.py`
**Modification**: Add 3 new Pydantic models (additive).

```python
class WarmPoolKeyStatus(BaseModel):
    workspace_id: UUID
    agent_type: str
    target_size: int
    available_count: int
    dispatched_count: int
    warming_count: int
    last_dispatch_at: datetime | None = None

class WarmPoolStatusResponse(BaseModel):
    keys: list[WarmPoolKeyStatus]

class WarmPoolConfigRequest(BaseModel):
    workspace_id: UUID
    agent_type: str = Field(min_length=1, max_length=255)
    target_size: int = Field(ge=0)

class WarmPoolConfigResponse(BaseModel):
    accepted: bool
    message: str = ""
```

---

## Python: RuntimeControllerClient Extensions

**File**: `apps/control-plane/src/platform/common/clients/runtime_controller.py`
**Modification**: Add 3 new async methods (additive; existing `connect()`, `close()`, `health_check()` unchanged).

```python
async def launch_runtime(self, payload: dict[str, Any], *, prefer_warm: bool = True) -> dict[str, Any]:
    """Call RuntimeControlService.LaunchRuntime; returns proto response as dict."""

async def warm_pool_status(self, workspace_id: str = "", agent_type: str = "") -> dict[str, Any]:
    """Call RuntimeControlService.WarmPoolStatus; returns proto response as dict."""

async def warm_pool_config(self, workspace_id: str, agent_type: str, target_size: int) -> dict[str, Any]:
    """Call RuntimeControlService.WarmPoolConfig; returns proto response as dict."""
```

---

## Python: Execution Scheduler Modifications

**File**: `apps/control-plane/src/platform/execution/scheduler.py`
**Modification**: Two targeted changes.

### 1. `_dispatch_to_runtime()` — add `prefer_warm=True`

Replace the informal `getattr(self.runtime_controller, "dispatch", None)` stub call with a formal `launch_runtime()` call:

```python
async def _dispatch_to_runtime(self, execution: Execution, step: StepIR) -> None:
    payload = { ...existing fields... }
    launch = getattr(self.runtime_controller, "launch_runtime", None)
    if callable(launch):
        result = launch(payload, prefer_warm=True)
        if hasattr(result, "__await__"):
            await result
    else:
        # fallback: legacy dispatch stub (no prefer_warm)
        target = getattr(self.runtime_controller, "dispatch", None)
        ...existing fallback logic...
```

### 2. New `_prompt_secret_preflight()` method

Called in `_build_task_plan_payload()` after the context payload is assembled but before returning it to the dispatch path.

```python
async def _prompt_secret_preflight(
    self,
    payload: dict[str, Any],
    *,
    execution: Execution,
    step: StepIR,
) -> None:
    """Scan assembled task-plan payload for secret patterns; block dispatch on match."""
```

**Logic**:
1. Serialize payload to string with `json.dumps(payload)`.
2. Iterate `OutputSanitizer.SECRET_PATTERNS`.
3. On first match: create `PolicyBlockedActionRecord(policy_basis=f"prompt_secret_detected:{secret_type}")` via producer (no DB write needed in scheduler; Kafka event only).
4. Publish to `monitor.alerts` topic via `self.producer`.
5. Raise `PolicySecretLeakError(secret_type=secret_type)` to abort dispatch (caught by `_process_execution`).

---

## Python: Execution Router Additions

**File**: `apps/control-plane/src/platform/execution/router.py`
**Modification**: Add 2 new admin endpoints (additive; existing endpoints unchanged).

```python
@router.get("/runtime/warm-pool/status", response_model=WarmPoolStatusResponse)
async def warm_pool_status(
    workspace_id: str = "",
    agent_type: str = "",
    _: User = Depends(require_platform_admin),
    runtime_controller: RuntimeControllerClient = Depends(get_runtime_controller),
) -> WarmPoolStatusResponse: ...

@router.put("/runtime/warm-pool/config", response_model=WarmPoolConfigResponse)
async def warm_pool_config(
    payload: WarmPoolConfigRequest,
    _: User = Depends(require_platform_admin),
    runtime_controller: RuntimeControllerClient = Depends(get_runtime_controller),
) -> WarmPoolConfigResponse: ...
```

---

## Python: New Exception

**File**: `apps/control-plane/src/platform/common/exceptions.py`
**Modification**: Add `PolicySecretLeakError(PlatformError)` with `secret_type: str` field (additive).

---

## Alembic Migration

**File**: `apps/control-plane/migrations/versions/043_runtime_warm_pool_targets.py`

```python
revision = "043_runtime_warm_pool_targets"
down_revision = "042_prescreener_guardrail_layer"

def upgrade() -> None:
    op.create_table(
        "runtime_warm_pool_targets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("agent_type", sa.String(255), nullable=False),
        sa.Column("target_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("workspace_id", "agent_type", name="uq_warm_pool_target_key"),
    )

def downgrade() -> None:
    op.drop_table("runtime_warm_pool_targets")
```
