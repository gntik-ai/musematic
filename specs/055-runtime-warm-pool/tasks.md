# Tasks: Runtime Warm Pool and Secrets Injection

**Input**: Design documents from `specs/055-runtime-warm-pool/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/contracts.md ✅, quickstart.md ✅

**Organization**: 2 modified Go files + 1 modified proto + 4 modified Python files + 1 new Alembic migration across 5 user stories + 1 foundational phase. No new bounded contexts, no new Kafka topics, no new data stores beyond `runtime_warm_pool_targets`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Foundational — Alembic Migration (Blocks all Python phases)

**Purpose**: Create `runtime_warm_pool_targets` table so Go gRPC handlers have a persistence target and the Python migration chain advances from 042. This is the prerequisite for Phase 3 (gRPC handlers).

- [X] T001 Create Alembic migration `apps/control-plane/migrations/versions/043_runtime_warm_pool_targets.py` with `revision = "043_runtime_warm_pool_targets"`, `down_revision = "042_prescreener_guardrail_layer"`, `upgrade()` calls `op.create_table("runtime_warm_pool_targets", ...)` with columns `id UUID PK DEFAULT gen_random_uuid()`, `workspace_id UUID NOT NULL`, `agent_type VARCHAR(255) NOT NULL`, `target_size INTEGER NOT NULL DEFAULT 0`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `sa.UniqueConstraint("workspace_id", "agent_type", name="uq_warm_pool_target_key")`; `downgrade()` calls `op.drop_table("runtime_warm_pool_targets")`

**Checkpoint**: `alembic upgrade 043_runtime_warm_pool_targets` applies without error. Table exists with unique constraint on `(workspace_id, agent_type)`. `alembic downgrade` removes the table.

---

## Phase 2: User Story 1 — Warm Pool Observability (Priority: P1)

**Goal**: Add 6 Prometheus metrics to the Runtime Controller so operators can observe pool sizing, hit rate, dispatch counts, cold starts, and dispatch latency per `(workspace_id, agent_type)`.

**Prerequisites**: None (independent Go file modification).

**Independent Test**: Create `Metrics` with a test registry; call `SetWarmPoolAvailable`, `IncWarmPoolDispatches`, `IncColdStart`, `ObserveWarmDispatchLatency`; assert gauge/counter/histogram values via registry snapshot.

- [X] T002 [US1] In `services/runtime-controller/pkg/metrics/metrics.go`: add six new fields to the `Metrics` struct: `_warmPoolAvailable *prometheus.GaugeVec`, `_warmPoolTarget *prometheus.GaugeVec`, `_warmPoolWarming *prometheus.GaugeVec`, `_warmPoolDispatches *prometheus.CounterVec`, `_coldStartCount *prometheus.CounterVec`, `_warmDispatchLatency *prometheus.HistogramVec` (buckets `[]float64{100, 250, 500, 1000, 2000, 5000}`); initialize all six in `NewMetrics()` via `promauto.With(reg).New*` using label `["workspace_id", "agent_type"]`
- [X] T003 [P] [US1] In `services/runtime-controller/pkg/metrics/metrics.go`: add six public methods: `SetWarmPoolAvailable(workspaceID, agentType string, count float64)`, `SetWarmPoolTarget(workspaceID, agentType string, count float64)`, `SetWarmPoolWarming(workspaceID, agentType string, count float64)`, `IncWarmPoolDispatches(workspaceID, agentType string)`, `IncColdStart(workspaceID, agentType string)`, `ObserveWarmDispatchLatency(workspaceID, agentType string, ms float64)`
- [X] T004 [P] [US1] Write Go unit tests in `services/runtime-controller/pkg/metrics/metrics_warmpool_test.go`: (a) `SetWarmPoolAvailable` sets gauge to expected value; (b) `IncColdStart` increments counter twice → value 2; (c) `ObserveWarmDispatchLatency` with 450ms → histogram sum == 450; (d) all six methods callable without panic on fresh registry

**Checkpoint**: `go test ./pkg/metrics/...` passes. All six warm pool metric methods callable.

---

## Phase 3: User Story 2 — Admin gRPC + REST Control Plane (Priority: P1)

**Goal**: Operators can read pool status and update target sizes via `WarmPoolStatus`/`WarmPoolConfig` gRPC RPCs (Go) and `GET/PUT /api/v1/runtime/warm-pool/*` REST endpoints (Python).

**Prerequisites**: Phase 1 (migration — Go Config handler writes to table), Phase 2 (metrics struct must exist before handler emits metrics)

**Independent Test (Go)**: Mock `pgx` + manager; assert `WarmPoolStatus` returns correct counts; assert `WarmPoolConfig` upserts and returns `accepted=true`; assert negative `target_size` returns `INVALID_ARGUMENT`.

**Independent Test (Python)**: GET returns 200 + `WarmPoolStatusResponse` for `platform_admin`; returns 403 for non-admin; PUT returns 200 `accepted=true`; PUT returns 422 for `target_size=-1`.

- [X] T005 [US2] In `services/runtime-controller/proto/runtime_controller.proto`: append five new proto messages after existing message definitions: `WarmPoolStatusRequest { string workspace_id = 1; string agent_type = 2; }`, `WarmPoolKeyStatus { string workspace_id = 1; string agent_type = 2; int32 target_size = 3; int32 available_count = 4; int32 dispatched_count = 5; int32 warming_count = 6; google.protobuf.Timestamp last_dispatch_at = 7; }`, `WarmPoolStatusResponse { repeated WarmPoolKeyStatus keys = 1; }`, `WarmPoolConfigRequest { string workspace_id = 1; string agent_type = 2; int32 target_size = 3; }`, `WarmPoolConfigResponse { bool accepted = 1; string message = 2; }`; add two new RPCs to `RuntimeControlService`: `rpc WarmPoolStatus(WarmPoolStatusRequest) returns (WarmPoolStatusResponse);` and `rpc WarmPoolConfig(WarmPoolConfigRequest) returns (WarmPoolConfigResponse);`
- [X] T006 [US2] In `services/runtime-controller/internal/server/server.go` (or `internal/server/warm_pool_handler.go`): implement `WarmPoolStatus` gRPC handler — (a) if `request.workspace_id` is non-empty, query `runtime_warm_pool_targets WHERE workspace_id=$1 AND agent_type=$2`; else query all rows; (b) for each DB row, call `manager.Count(key)` for live `available_count`; (c) build and return `WarmPoolStatusResponse{keys: [...]}`; implement `WarmPoolConfig` gRPC handler — (a) validate `request.target_size >= 0` else return `INVALID_ARGUMENT`; (b) upsert `INSERT INTO runtime_warm_pool_targets(workspace_id, agent_type, target_size, updated_at) VALUES($1,$2,$3,now()) ON CONFLICT (workspace_id, agent_type) DO UPDATE SET target_size=$3, updated_at=now()`; (c) return `WarmPoolConfigResponse{accepted: true}`
- [X] T007 [P] [US2] Write Go unit tests in `services/runtime-controller/internal/server/warm_pool_handler_test.go`: (a) `WarmPoolStatus` with mock DB returning 1 row + manager count 3 → response has 1 key with `available_count=3`; (b) `WarmPoolConfig` with `target_size=5` → DB upsert called, `accepted=true`; (c) `WarmPoolConfig` with `target_size=-1` → returns `INVALID_ARGUMENT` error code; (d) `WarmPoolStatus` with empty workspace_id → queries all rows (no WHERE filter); (e) `WarmPoolConfig` with empty `workspace_id` → returns `INVALID_ARGUMENT`
- [X] T008 [US2] Add three new async methods to `apps/control-plane/src/platform/common/clients/runtime_controller.py`: `async def launch_runtime(self, payload: dict[str, Any], *, prefer_warm: bool = True) -> dict[str, Any]` (calls `self.stub.LaunchRuntime` with proto-mapped request including `prefer_warm`); `async def warm_pool_status(self, workspace_id: str = "", agent_type: str = "") -> dict[str, Any]` (calls `self.stub.WarmPoolStatus`); `async def warm_pool_config(self, workspace_id: str, agent_type: str, target_size: int) -> dict[str, Any]` (calls `self.stub.WarmPoolConfig`)
- [X] T009 [P] [US2] Add four Pydantic schemas to `apps/control-plane/src/platform/execution/schemas.py`: `WarmPoolKeyStatus(BaseModel)` with fields `workspace_id: UUID`, `agent_type: str`, `target_size: int`, `available_count: int`, `dispatched_count: int`, `warming_count: int`, `last_dispatch_at: datetime | None = None`; `WarmPoolStatusResponse(BaseModel)` with `keys: list[WarmPoolKeyStatus]`; `WarmPoolConfigRequest(BaseModel)` with `workspace_id: UUID`, `agent_type: str = Field(min_length=1, max_length=255)`, `target_size: int = Field(ge=0)`; `WarmPoolConfigResponse(BaseModel)` with `accepted: bool`, `message: str = ""`
- [X] T010 [US2] In `apps/control-plane/src/platform/execution/router.py`: add `from platform.execution.schemas import WarmPoolStatusResponse, WarmPoolConfigRequest, WarmPoolConfigResponse` import; add `@router.get("/runtime/warm-pool/status", response_model=WarmPoolStatusResponse)` endpoint `async def warm_pool_status(workspace_id: str = "", agent_type: str = "", _: Any = Depends(require_platform_admin), runtime_controller: RuntimeControllerClient = Depends(get_runtime_controller)) -> WarmPoolStatusResponse` that calls `await runtime_controller.warm_pool_status(workspace_id=workspace_id, agent_type=agent_type)` and returns `WarmPoolStatusResponse(**result)`; add `@router.put("/runtime/warm-pool/config", response_model=WarmPoolConfigResponse)` endpoint `async def warm_pool_config(payload: WarmPoolConfigRequest, _: Any = Depends(require_platform_admin), runtime_controller: RuntimeControllerClient = Depends(get_runtime_controller)) -> WarmPoolConfigResponse` that calls `await runtime_controller.warm_pool_config(str(payload.workspace_id), payload.agent_type, payload.target_size)` and returns `WarmPoolConfigResponse(**result)`
- [X] T011 [P] [US2] Write Python unit tests in `apps/control-plane/tests/unit/common/test_runtime_controller_client.py`: (a) `warm_pool_status()` calls `stub.WarmPoolStatus` once and returns dict with `"keys"` field; (b) `warm_pool_config()` calls `stub.WarmPoolConfig` with correct workspace_id/agent_type/target_size; (c) `launch_runtime()` calls `stub.LaunchRuntime` and includes `prefer_warm=True` in request
- [X] T012 [P] [US2] Write Python unit tests in `apps/control-plane/tests/unit/execution/test_warm_pool_endpoints.py`: (a) `GET /runtime/warm-pool/status` with admin token → 200 + `{"keys": [...]}` schema; (b) `GET /runtime/warm-pool/status` with non-admin token → 403; (c) `PUT /runtime/warm-pool/config` with valid body → 200 `{"accepted": true}`; (d) `PUT /runtime/warm-pool/config` with `target_size=-1` → 422

**Checkpoint**: gRPC handlers live. REST admin surface live. Operators can read status + update target sizes without a Runtime Controller restart.

---

## Phase 4: User Story 1 (dispatch path) — prefer_warm wiring (Priority: P1)

**Goal**: The execution scheduler's `_dispatch_to_runtime()` sends `prefer_warm=True` to the Runtime Controller via the formal `launch_runtime()` client method, replacing the informal `dispatch` stub call.

**Prerequisites**: Phase 3 T008 (client `launch_runtime()` must exist)

**Independent Test**: Mock `runtime_controller.launch_runtime` to return `{"warm_start": True}`; call `scheduler._dispatch_to_runtime(execution, step)`; assert `launch_runtime` called once with `prefer_warm=True`.

- [X] T013 [US1] In `apps/control-plane/src/platform/execution/scheduler.py` `_dispatch_to_runtime()`: replace the informal `target = getattr(self.runtime_controller, "dispatch", None)` block with a formal call — add `launch = getattr(self.runtime_controller, "launch_runtime", None)`; if callable, call `result = launch(payload, prefer_warm=True)` (await if coroutine); keep existing `dispatch` getattr as fallback for backward compatibility (else branch)
- [X] T014 [P] [US1] Write Python unit tests in `apps/control-plane/tests/unit/execution/test_scheduler_dispatch.py`: (a) `_dispatch_to_runtime()` calls `launch_runtime` with `prefer_warm=True` when method exists; (b) when `runtime_controller` has no `launch_runtime` but has `dispatch`, falls back to `dispatch` call (backward compat); (c) `launch_runtime` returning `{"warm_start": False}` does not raise — cold start path succeeds (FR-005)

**Checkpoint**: Scheduler wires `prefer_warm=True`. Cold start fallback preserved.

---

## Phase 5: User Story 4 — Prompt Secret Preflight (Priority: P1)

**Goal**: `_prompt_secret_preflight()` scans the assembled task-plan payload for the 5 secret patterns before dispatch. A match blocks the LLM call, publishes a `prompt_secret_detected` alert on `monitor.alerts`, and creates a `PolicyBlockedActionRecord`.

**Prerequisites**: Phase 4 T013 (`_dispatch_to_runtime` refactor must be in place); `OutputSanitizer.SECRET_PATTERNS` available at `apps/control-plane/src/platform/policies/sanitizer.py`

**Independent Test**: Payload containing `"Bearer sk-abc123456789"` raises `PolicySecretLeakError("bearer_token")` and calls `producer.publish` with `event_type="prompt_secret_detected"`; clean payload passes without exception; all 5 pattern types each raise with correct `secret_type`.

- [X] T015 [US4] In `apps/control-plane/src/platform/common/exceptions.py`: add `class PolicySecretLeakError(PlatformError): secret_type: str` (additive; `PlatformError` is the existing base exception class)
- [X] T016 [US4] In `apps/control-plane/src/platform/execution/scheduler.py`: add `from platform.policies.sanitizer import OutputSanitizer` import; add private method `async def _prompt_secret_preflight(self, payload: dict[str, Any], *, execution: Execution, step: StepIR) -> None` that: (a) serializes payload with `json.dumps(payload)`; (b) iterates `OutputSanitizer.SECRET_PATTERNS.items()`; (c) on first match: publishes `EventEnvelope(event_type="prompt_secret_detected", data={"secret_type": secret_type, "agent_fqn": step.agent_fqn, "execution_id": str(execution.id), "step_id": step.step_id})` to `monitor.alerts` topic via `self.producer`; (d) raises `PolicySecretLeakError(secret_type=secret_type)`
- [X] T017 [US4] In `apps/control-plane/src/platform/execution/scheduler.py` `_build_task_plan_payload()`: after the context payload is assembled (after the `get_plan_context` block and the fallback `return {...}` payload is fully constructed), add `await self._prompt_secret_preflight(payload, execution=execution, step=step)` before the final `return payload`; catch `PolicySecretLeakError` in the calling method `_process_execution` and log + abort the step without surfacing the error to the caller
- [X] T018 [P] [US4] Write Python unit tests in `apps/control-plane/tests/unit/execution/test_prompt_preflight.py`: (a) payload with `"Bearer sk-abc123456789"` → `PolicySecretLeakError("bearer_token")` raised, `producer.publish` called once with `event_type="prompt_secret_detected"` and `data.secret_type="bearer_token"`; (b) clean payload → no exception, `producer.publish` not called; (c) all five pattern types (`bearer_token`, `api_key`, `jwt_token`, `connection_string`, `password_literal`) each match and raise with correct `secret_type`; (d) `PolicySecretLeakError` caught by `_process_execution` → step aborted but execution not crashed

**Checkpoint**: Prompt-side secret containment active. US4 independently verifiable. Closes the inter-turn secret leak path.

---

## Phase 6: User Story 3 + 5 — Secrets isolation proof + cold-start fallback (Priority: P1/P2)

**Goal**: US3 (structural secret containment) is preserved by the existing `ResolveSecrets` path — no new code needed. US5 (cold-start fallback) is guaranteed by the `prefer_warm` fallback logic already in place after Phase 4. This phase verifies both via targeted tests.

**Prerequisites**: Phase 4 complete (dispatch fallback in place)

- [X] T019 [P] [US3] Verify secret containment in `services/runtime-controller/internal/launcher/secrets.go`: confirm (read-only) that `ResolveSecrets()` maps each K8s Secret key to `SECRETS_REF_{KEY}` env var + `/run/secrets/{key}` projected volume; write a Go verification test in `services/runtime-controller/internal/launcher/secrets_containment_test.go` asserting: (a) `SECRETS_REF_DATABASE_URL` env var is present for a secret with key `DATABASE_URL`; (b) projected volume path is `/run/secrets/DATABASE_URL`; (c) no secret value appears in any returned `EnvVar.Value` field (value is the path string only, not the actual secret)
- [X] T020 [P] [US5] Write Python unit tests in `apps/control-plane/tests/unit/execution/test_scheduler_dispatch.py` (extending Phase 4 test file): (d) `runtime_controller.launch_runtime` raising an exception → dispatch falls through to legacy `dispatch` fallback, no exception propagated to caller (FR-013 graceful degradation); (e) `target_size=0` configured → `launch_runtime` receives `prefer_warm=False`-equivalent (pool returns miss) → `warm_start=False` in response, no error raised (FR-015)

**Checkpoint**: US3 structural guarantee verified. US5 cold-start fallback proven testable.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Migration)**: No dependencies — start immediately
- **Phase 2 (Metrics)**: No dependencies — start in parallel with Phase 1
- **Phase 3 (gRPC + REST)**: Requires Phase 1 (DB table) AND Phase 2 (metrics struct) complete
- **Phase 4 (prefer_warm dispatch)**: Requires Phase 3 T008 (client `launch_runtime()`) complete
- **Phase 5 (Prompt preflight)**: Requires Phase 4 T013 (scheduler refactor) complete
- **Phase 6 (Verification)**: Requires Phase 4 complete; Phase 5 T018 for US5 extension

### User Story Dependencies

- **US1 observability (P1)**: Phase 2 — independent Go metrics file
- **US2 admin control (P1)**: Phase 3 — requires Phase 1 + 2
- **US1 dispatch (P1)**: Phase 4 — requires Phase 3 T008 (client)
- **US4 prompt preflight (P1)**: Phase 5 — requires Phase 4 T013
- **US3 secrets proof (P1)**: Phase 6 — read-only verification, parallel with Phase 5
- **US5 cold start (P2)**: Phase 6 — test extension, parallel with Phase 5

### Parallel Opportunities

```bash
# Phase 1 + Phase 2 run in parallel immediately:
Task: T001          # Migration (Python)
Task: T002+T003     # Go metrics (independent Go file)
Task: T004          # Go metrics tests [P]

# After T001 + T002+T003, Phase 3 tasks can split:
Task: T005          # Proto changes (Go)
Task: T009          # Python schemas (different file)

# After T005, Go handlers:
Task: T006          # gRPC handler impl
Task: T007 [P]      # Go handler tests

# After T008 (client), Python REST + tests:
Task: T010          # Python router endpoints
Task: T011 [P]      # Python client tests
Task: T012 [P]      # REST endpoint tests

# After T013 (scheduler refactor):
Task: T014 [P]      # Dispatch tests
Task: T015          # PolicySecretLeakError (exceptions.py)

# After T015:
Task: T016          # _prompt_secret_preflight() method
Task: T017          # Wire into _build_task_plan_payload
Task: T018 [P]      # Preflight tests

# Parallel with Phase 5:
Task: T019 [P]      # US3 secrets containment test
Task: T020 [P]      # US5 cold start tests
```

---

## Parallel Example: All P1 user stories after Phase 1+2

```bash
# After T001 (migration) + T002+T003 (metrics) complete:

# Developer A (US2 → US1 dispatch):
T005 → T006 → T008 → T010 → T013 → T016 → T017
       T007[P]       T011[P] T014[P] T018[P]
                     T012[P]

# Developer B (Go metrics tests + schemas):
T004[P] → T009[P] → T019[P] → T020[P]
```

---

## Implementation Strategy

### MVP First (US1 observability + US2 admin)

1. Complete Phase 1: T001 (migration)
2. Complete Phase 2: T002 → T003 → T004 (metrics)
3. Complete Phase 3: T005 → T006 → T007 (Go gRPC) → T008 → T009 → T010 (Python REST)
4. **STOP and VALIDATE**: `GET /api/v1/runtime/warm-pool/status` returns live data. `PUT /api/v1/runtime/warm-pool/config` updates target without restart.

### Incremental Delivery

1. Phase 1 + Phase 2: Migration + metrics active — operators see `warm_pool_available` gauges
2. Phase 3: Admin gRPC + REST live — operators can inspect and adjust pool sizes
3. Phase 4: `prefer_warm=True` wired in — warm dispatch path fully operational
4. Phase 5: Prompt preflight active — Principle XI enforcement complete at both pod boundary (US3) and prompt boundary (US4)
5. Phase 6: Verification tests prove structural guarantees

---

## Notes

- T001 migration is the only Python DDL change; all else is additive Python + Go
- T002 and T003 modify the same Go file `pkg/metrics/metrics.go` — sequential within Phase 2; T004 is a new test file and can be parallel
- T005 (proto) must precede T006 (handler) and T008 (Python client) — proto compilation generates the stubs both sides consume
- T019 is read-only verification of existing `secrets.go` — no code changes, just test authoring
- Deploying after Phase 4 with `prefer_warm=True` is safe: the Runtime Controller returns `warm_start=false` on pool miss, which is handled as a no-error cold start (FR-005)
- Activation of prompt preflight (Phase 5) is zero-impact on clean prompts — only prompts containing one of the 5 secret patterns are blocked
