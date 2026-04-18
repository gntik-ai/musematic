# Implementation Plan: Runtime Warm Pool and Secrets Injection

**Branch**: `055-runtime-warm-pool` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/055-runtime-warm-pool/spec.md`

## Summary

The Runtime Controller's warm pool manager, replenisher, idle scanner, and Kubernetes secret resolver are already shipped. The `LaunchRuntimeResponse.warm_start` bool and `RuntimeContract.secret_refs` already exist in the proto. What is missing: (1) Prometheus metrics for pool observability; (2) gRPC `WarmPoolStatus`/`WarmPoolConfig` RPCs for admin control; (3) persistent target storage (new PostgreSQL table via Alembic migration 043); (4) Python gRPC client wrappers and admin REST endpoints; (5) `prefer_warm=True` wired into the execution scheduler's dispatch path; (6) prompt-side secret preflight scanning assembled LLM context before pod dispatch. Total scope: 1 Go metrics file + 1 proto file + 1 Go handler file + 4 Python files + 1 new test directory (Go) + 4 new Python test modules + 1 Alembic migration. No new bounded contexts, no new Kafka topics, no new data stores.

## Technical Context

**Language/Version**: Go 1.22+ (runtime-controller satellite), Python 3.12+ (control plane)
**Primary Dependencies**: `prometheus/promauto` (Go metrics), `google.golang.org/grpc 1.67+` (gRPC), `pgx/v5` (Go PostgreSQL), FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, grpcio 1.65+, pytest + pytest-asyncio 8.x
**Storage**: PostgreSQL — 1 new table `runtime_warm_pool_targets` (additive; no columns added to existing tables)
**Testing**: `go test ./...` (Go unit tests), `pytest + pytest-asyncio 8.x` (Python unit tests), min 95% coverage on modified files
**Target Platform**: Linux / Kubernetes (same as Runtime Controller deployment)
**Project Type**: Brownfield modification — Go satellite service + Python control plane
**Performance Goals**: Warm dispatch p99 < 2s (SC-002); metrics overhead < 1ms per launch
**Constraints**: Brownfield Rules 1–8; no file rewrites; additive + backward-compatible only; `prefer_warm` default `true` in Python (Brownfield Rule 7: existing Go callers unaffected by proto default `false`)
**Scale/Scope**: 1 modified Go metrics file, 1 modified proto, 1 Go handler file, 1 Alembic migration, 4 modified Python files, 4 new Python test modules, 1 new Go test file

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|-----------|--------|-------|
| Modular monolith (Principle I) | ✅ PASS | Changes confined to `execution/` + `common/clients/`; Go changes in `runtime-controller/` only |
| No cross-boundary DB access (Principle IV) | ✅ PASS | Python accesses `runtime_warm_pool_targets` only via gRPC delegation to Go handler; Go handler owns the table |
| Policy is machine-enforced (Principle VI) | ✅ PASS | Prompt preflight is programmatic; no human gate |
| Zero-trust (Principle IX) | ✅ PASS | Admin endpoints require `platform_admin`; no anonymous access |
| Secrets not in LLM context (Principle XI) | ✅ PASS | US3 preserves pod-boundary guarantee (unchanged); US4 adds prompt-level preflight (this feature closes the last gap) |
| Generic S3 storage (Principle XVI) | ✅ PASS | N/A to this feature |
| Brownfield Rule 1 (no rewrites) | ✅ PASS | Line-level additions to existing files only |
| Brownfield Rule 2 (Alembic only) | ✅ PASS | Migration 043 for new `runtime_warm_pool_targets` table |
| Brownfield Rule 3 (preserve tests) | ✅ PASS | 4 new Python test modules + 1 Go test file; no existing tests modified |
| Brownfield Rule 4 (use existing patterns) | ✅ PASS | `promauto` pattern for metrics; `getattr`/`dispatch` client pattern extended; existing `PolicyBlockedActionRecord` reused |
| Brownfield Rule 5 (reference existing files) | ✅ PASS | All modified files cited with exact function names in data-model.md |
| Brownfield Rule 6 (additive enum values) | ✅ PASS | No enum changes in this feature |
| Brownfield Rule 7 (backward-compatible APIs) | ✅ PASS | `prefer_warm` defaults to proto zero value `false` in Go; Python sends `true`; existing Go callers unaffected |
| Brownfield Rule 8 (feature flags) | ✅ PASS | `prefer_warm=True` default can be overridden per step; prompt preflight is safe-to-deploy (no-op on clean prompts) |

**Post-design re-check**: No violations.

## Project Structure

### Documentation (this feature)

```text
specs/055-runtime-warm-pool/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── contracts.md     # Phase 1 output
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code — What Changes

```text
services/runtime-controller/
├── pkg/metrics/
│   └── metrics.go                    MODIFIED — add 6 warm pool metrics + 6 setter/observer methods
├── proto/
│   └── runtime_controller.proto     MODIFIED — add 5 messages + 2 RPCs (WarmPoolStatus, WarmPoolConfig)
├── internal/server/
│   └── server.go                     MODIFIED — implement WarmPoolStatus + WarmPoolConfig gRPC handlers
└── internal/server/
    └── warm_pool_handler_test.go     NEW — Go unit tests for 2 new handlers (6 test cases)

apps/control-plane/
├── migrations/versions/
│   └── 043_runtime_warm_pool_targets.py   NEW — CREATE TABLE runtime_warm_pool_targets
│
├── src/platform/
│   ├── common/
│   │   ├── clients/
│   │   │   └── runtime_controller.py  MODIFIED — add launch_runtime(), warm_pool_status(),
│   │   │                                          warm_pool_config() methods
│   │   └── exceptions.py              MODIFIED — add PolicySecretLeakError(PlatformError)
│   └── execution/
│       ├── schemas.py                 MODIFIED — add WarmPoolKeyStatus, WarmPoolStatusResponse,
│       │                                          WarmPoolConfigRequest, WarmPoolConfigResponse
│       ├── scheduler.py               MODIFIED — _dispatch_to_runtime() uses launch_runtime();
│       │                                          _prompt_secret_preflight() new method
│       └── router.py                  MODIFIED — GET/PUT /runtime/warm-pool/* endpoints
│
└── tests/unit/
    ├── common/
    │   └── test_runtime_controller_client.py   NEW — client wrappers (3 scenarios)
    └── execution/
        ├── test_warm_pool_endpoints.py          NEW — REST endpoint tests (4 scenarios)
        ├── test_scheduler_dispatch.py           NEW — prefer_warm + cold fallback (3 scenarios)
        └── test_prompt_preflight.py             NEW — preflight detection (4 scenarios)
```

**Structure Decision**: Strictly additive changes across two services (Go satellite + Python control plane). Single Alembic migration. No new bounded contexts, no new Kafka topics, no new data stores beyond the 1 new PostgreSQL table.

## Implementation Phases

### Phase 1: Alembic Migration (blocks Python phases)

**Goal**: Create `runtime_warm_pool_targets` table so Go gRPC handlers have a persistence target and the Python migration chain advances from 042.

**Files**:
- `apps/control-plane/migrations/versions/043_runtime_warm_pool_targets.py` — `revision = "043_runtime_warm_pool_targets"`, `down_revision = "042_prescreener_guardrail_layer"`, `upgrade()` creates table with unique constraint on `(workspace_id, agent_type)`, `downgrade()` drops table.

**Independent test**: Apply migration; assert `runtime_warm_pool_targets` table exists; assert upsert and select work; downgrade; assert table gone.

---

### Phase 2: Go Metrics (US1 — P1)

**Goal**: Add 6 Prometheus metrics to `pkg/metrics/metrics.go` so warm pool dispatch and cold start events become observable.

**Files**:
- `services/runtime-controller/pkg/metrics/metrics.go` — Add `_warmPoolAvailable`, `_warmPoolTarget`, `_warmPoolWarming`, `_warmPoolDispatches`, `_coldStartCount`, `_warmDispatchLatency` fields to `Metrics` struct; initialize in `NewMetrics()` via `promauto`; add 6 public methods.

**Independent test**: Create `Metrics` with test registry; call each method; assert gauge/counter/histogram values via registry snapshot.

---

### Phase 3: Proto + gRPC Handlers (US2 — P1)

**Goal**: Add `WarmPoolStatus` and `WarmPoolConfig` RPCs to the proto and implement them in the Go server.

**Prerequisites**: Phase 1 (table must exist for Config handler)

**Files**:
- `services/runtime-controller/proto/runtime_controller.proto` — Append `WarmPoolStatusRequest`, `WarmPoolKeyStatus`, `WarmPoolStatusResponse`, `WarmPoolConfigRequest`, `WarmPoolConfigResponse` messages; add 2 RPCs to `RuntimeControlService`.
- `services/runtime-controller/internal/server/server.go` (or `warm_pool_handler.go`) — Implement `WarmPoolStatus`: query DB for targets, call `manager.Count()` per key, build response. Implement `WarmPoolConfig`: validate args, upsert to DB, signal replenisher.

**Independent test**: Mock `pgx` + manager; assert `WarmPoolStatus` returns correct counts; assert `WarmPoolConfig` upserts and returns `accepted=true`; assert negative `target_size` returns `INVALID_ARGUMENT`.

---

### Phase 4: Python Client Extensions (US2 — P1)

**Goal**: `RuntimeControllerClient` exposes `launch_runtime()`, `warm_pool_status()`, `warm_pool_config()` methods.

**Prerequisites**: Phase 3 (proto must be compiled before client can call new RPCs)

**Files**:
- `apps/control-plane/src/platform/common/clients/runtime_controller.py` — Add 3 async methods.
- `apps/control-plane/src/platform/common/exceptions.py` — Add `PolicySecretLeakError`.

**Independent test**: Mock `stub`; assert each method calls the correct gRPC method with correct request args; assert return value is dict-normalized proto response.

---

### Phase 5: REST Admin Endpoints + Schemas (US2 — P1)

**Goal**: `GET /api/v1/runtime/warm-pool/status` and `PUT /api/v1/runtime/warm-pool/config` are available to `platform_admin` callers.

**Prerequisites**: Phase 4 (client methods must exist)

**Files**:
- `apps/control-plane/src/platform/execution/schemas.py` — Add 4 new Pydantic models.
- `apps/control-plane/src/platform/execution/router.py` — Add 2 endpoints.

**Independent test**: GET returns 200 + correct schema for admin; GET returns 403 for non-admin; PUT returns 200 with `accepted=true`; PUT returns 422 for `target_size=-1`.

---

### Phase 6: Execution Scheduler — `prefer_warm` + prompt preflight (US1 + US4 — P1)

**Goal**: `_dispatch_to_runtime()` sends `prefer_warm=True` to the Runtime Controller. `_prompt_secret_preflight()` blocks dispatch if assembled context contains a secret pattern.

**Prerequisites**: Phase 4 (client `launch_runtime()` must exist), Phase 1 (OutputSanitizer patterns importable)

**Files**:
- `apps/control-plane/src/platform/execution/scheduler.py`:
  1. In `_dispatch_to_runtime()`: replace informal `getattr(self.runtime_controller, "dispatch", None)` with `launch_runtime(payload, prefer_warm=True)` call.
  2. In `_build_task_plan_payload()`: call `await self._prompt_secret_preflight(payload, execution=execution, step=step)` before returning.
  3. Add private `async def _prompt_secret_preflight(self, payload, *, execution, step) -> None`: serialize payload to JSON string; iterate `OutputSanitizer.SECRET_PATTERNS`; on first match publish to `monitor.alerts` and raise `PolicySecretLeakError(secret_type=secret_type)`.

**Independent test**: `_dispatch_to_runtime()` calls `launch_runtime` with `prefer_warm=True`; clean payload passes preflight without exception; bearer-token payload raises `PolicySecretLeakError("bearer_token")` and publishes event; all 5 pattern types each raise with correct `secret_type`.

---

## API Endpoints Used / Modified

| Endpoint | Status | Change |
|----------|--------|--------|
| `POST /api/v1/runtime/dispatch` (via gRPC) | Existing | Now sends `prefer_warm=True` |
| `GET /api/v1/runtime/warm-pool/status` | **NEW** | Admin warm pool status |
| `PUT /api/v1/runtime/warm-pool/config` | **NEW** | Admin target-size update |
| `gRPC WarmPoolStatus` | **NEW** | Runtime Controller admin RPC |
| `gRPC WarmPoolConfig` | **NEW** | Runtime Controller admin RPC |
| `monitor.alerts` topic | Existing | New event type `prompt_secret_detected` |
| `GET /api/v1/policies/blocked-actions` | Existing | Now returns `component=execution` prompt-secret records |

## Dependencies

- **Feature 009 (Runtime Controller)**: Go satellite base; all new metrics/handlers extend this service. Already deployed.
- **Feature 028/054 (Policy Governance + Pre-Screener)**: `OutputSanitizer.SECRET_PATTERNS` (5 compiled regexes) reused for prompt preflight. Migration 042 is `down_revision` for 043.
- **Feature 047 (Observability Stack)**: OTel/Prometheus collector already deployed; `warm_dispatch_latency_ms` histogram consumed by existing Grafana setup without new infrastructure.
- **Feature 029 (Workflow Execution Engine)**: `execution/scheduler.py` (`SchedulerService`) is the call site for `_dispatch_to_runtime` and `_prompt_secret_preflight`.

## Complexity Tracking

No constitution violations. No complexity justification required.

| Category | Count |
|---|---|
| Modified Go source files | 2 (`pkg/metrics/metrics.go`, `internal/server/server.go`) |
| Modified proto files | 1 (`proto/runtime_controller.proto`) |
| Modified Python source files | 4 (`common/clients/runtime_controller.py`, `common/exceptions.py`, `execution/schemas.py`, `execution/scheduler.py`, `execution/router.py`) |
| New Alembic migrations | 1 (`043_runtime_warm_pool_targets.py`) |
| New Go test files | 1 |
| New Python test modules | 4 |
| New bounded contexts | 0 |
| New database tables | 1 (`runtime_warm_pool_targets`) |
| New Kafka topics | 0 |
| New REST API endpoints | 2 |
| New gRPC RPCs | 2 |

User input refinements discovered during research:

1. User steps 1–2 (warm_pool.go, secrets_injector.go) are no-ops — `internal/warmpool/` and `internal/launcher/secrets.go` are already shipped.
2. User step 3 (metrics) is genuine but scoped to 6 metrics added to the existing `pkg/metrics/metrics.go` file.
3. User step 4 (gRPC endpoints) is genuine — 2 new RPCs + 5 new proto messages + handler implementation.
4. User step 5 (Python executor) is genuine — `_dispatch_to_runtime()` gets `prefer_warm=True` wired in via a formal `launch_runtime()` client method replacing an informal `dispatch` stub.
5. User step 6 (REST endpoints) is genuine — 2 admin endpoints in the existing `execution/router.py`.
6. US4 (prompt preflight) adds `_prompt_secret_preflight()` to `scheduler.py`, reusing `OutputSanitizer.SECRET_PATTERNS` — single source of truth for secret detection across tool outputs (feature 054) and LLM prompt context (this feature).
