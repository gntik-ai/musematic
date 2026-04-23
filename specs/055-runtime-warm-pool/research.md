# Research: Runtime Warm Pool and Secrets Injection

**Feature**: `specs/055-runtime-warm-pool/spec.md`
**Date**: 2026-04-18
**Phase**: 0 — Unknowns resolved, no NEEDS CLARIFICATION markers remain

---

## Decision 1: User plan steps 1–2 are no-ops (warm pool + secrets already shipped)

**Decision**: Skip creating `warm_pool.go` and `secrets_injector.go`; they already exist.

**Rationale**: `services/runtime-controller/internal/warmpool/` contains `manager.go` (ready-queue, `Dispatch()`/`RegisterReadyPod()`/`RemoveReadyPod()`), `replenisher.go` (background fill loop), and `idle_scanner.go` (recycle logic). `services/runtime-controller/internal/launcher/secrets.go` resolves Kubernetes Secrets into projected volumes + `SECRETS_REF_{KEY}` env vars. `LaunchRuntimeResponse.warm_start` bool and `RuntimeContract.secret_refs` are already in the proto.

**Alternatives considered**: Regenerating — rejected; wholesale rewrites violate Brownfield Rule 1.

---

## Decision 2: Prometheus metrics gap is genuine — extend `pkg/metrics/metrics.go`

**Decision**: Add 6 warm pool metrics to `services/runtime-controller/pkg/metrics/metrics.go` using the existing `prometheus/promauto` pattern. No new metrics endpoint.

**Rationale**: `pkg/metrics/metrics.go` currently defines `IncLaunches`, `ObserveLaunchDuration`, `SetActiveRuntimes`, `ObserveReconciliationDuration`, `IncHeartbeatTimeouts` — zero warm pool metrics. The file uses `promauto.With(reg).NewCounterVec` / `.NewGaugeVec` / `.NewHistogramVec`. New metrics follow the identical pattern.

**Metrics to add**:
- `warm_pool_available{workspace_id,agent_type}` — Gauge
- `warm_pool_target{workspace_id,agent_type}` — Gauge
- `warm_pool_warming{workspace_id,agent_type}` — Gauge
- `warm_pool_dispatches_total{workspace_id,agent_type}` — Counter
- `cold_start_count_total{workspace_id,agent_type}` — Counter
- `warm_dispatch_latency_ms{workspace_id,agent_type}` — Histogram (buckets: 100, 250, 500, 1000, 2000, 5000)

**Alternatives considered**: Separate metrics file — rejected; single `pkg/metrics` is the existing pattern. New `/metrics` endpoint — rejected; Brownfield Rule 1 + existing endpoint is sufficient.

---

## Decision 3: gRPC WarmPoolStatus + WarmPoolConfig RPCs are genuine gaps

**Decision**: Add two new proto messages + two new RPCs to `services/runtime-controller/proto/runtime_controller.proto` and implement the handlers in the Go gRPC server.

**Rationale**: The proto currently has 7 RPCs (LaunchRuntime, GetRuntime, PauseRuntime, ResumeRuntime, StopRuntime, StreamRuntimeEvents, CollectRuntimeArtifacts). No warm pool admin surface exists. Per Brownfield Rule 7, new RPCs are additive; existing 7 are unchanged.

**New messages**:
```
WarmPoolStatusRequest  { string workspace_id = 1; string agent_type = 2; }  // empty = all keys
WarmPoolKeyStatus      { workspace_id, agent_type, target_size, available_count,
                         dispatched_count, warming_count, last_dispatch_at (Timestamp) }
WarmPoolStatusResponse { repeated WarmPoolKeyStatus keys = 1; }
WarmPoolConfigRequest  { string workspace_id = 1; string agent_type = 2; int32 target_size = 3; }
WarmPoolConfigResponse { bool accepted = 1; string message = 2; }
```

**Alternatives considered**: REST directly on the Go service — rejected; the platform pattern is Python REST → Go gRPC; adding a second HTTP server to the Go service is scope creep.

---

## Decision 4: Target persistence via Alembic migration 043 (shared PostgreSQL)

**Decision**: Persist warm pool targets in a new `runtime_warm_pool_targets` table via `apps/control-plane/migrations/versions/043_runtime_warm_pool_targets.py`. The Go gRPC handlers read/write this table via `pgx/v5`.

**Rationale**: The Go Runtime Controller already uses PostgreSQL (`pgx/v5`) for `TaskPlanRecord` persistence. The platform uses a single shared PostgreSQL cluster (`musematic-postgres-rw:5432`). Adding a table via the existing Alembic pipeline (Python migration 043, `down_revision = "042_prescreener_guardrail_layer"`) keeps all DDL changes in one canonical migration path (Brownfield Rule 2).

**Table schema**:
```sql
runtime_warm_pool_targets (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL,
  agent_type   VARCHAR(255) NOT NULL,
  target_size  INTEGER NOT NULL DEFAULT 0,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, agent_type)
)
```

**Alternatives considered**: Go-managed migration files — rejected; would introduce a second migration system. In-memory only — rejected; target loss on restart violates FR-003.

---

## Decision 5: Python gRPC client extended additively — `runtime_controller.py`

**Decision**: Add `launch_runtime()`, `warm_pool_status()`, and `warm_pool_config()` methods to `apps/control-plane/src/platform/common/clients/runtime_controller.py`. The existing `dispatch()` call in `scheduler.py` is replaced by `launch_runtime()` with `prefer_warm=True` default.

**Rationale**: The client at `common/clients/runtime_controller.py` currently has only `connect()`, `close()`, and `health_check()` — no RPC wrappers. The `_dispatch_to_runtime()` method in `execution/scheduler.py` calls `getattr(self.runtime_controller, "dispatch", None)` as an informal stub; this becomes a formal `launch_runtime(payload)` wrapper. Brownfield Rule 7: `prefer_warm` defaults to `True`; existing callers that pass no preference are unaffected.

**Alternatives considered**: Direct gRPC stub calls in the router — rejected; consistent with pattern of wrapping gRPC in the `clients/` layer.

---

## Decision 6: Admin REST endpoints in `execution/router.py`

**Decision**: Add `GET /api/v1/runtime/warm-pool/status` and `PUT /api/v1/runtime/warm-pool/config` to `apps/control-plane/src/platform/execution/router.py`. Both require `platform_admin` RBAC role.

**Rationale**: The execution router already owns the `/api/v1/runtime/` prefix and already has the `RuntimeControllerClient` injected via `execution/dependencies.py`. Adding warm-pool admin endpoints here is consistent with the existing router structure. New schemas (`WarmPoolStatusResponse`, `WarmPoolConfigRequest`, `WarmPoolConfigResponse`) go into `execution/schemas.py`.

**Alternatives considered**: Separate `warmpool/` bounded context — rejected; no new bounded context needed for 2 endpoints (Brownfield Rule 1). Adding to `policies/router.py` — rejected; policy router is unrelated to runtime dispatch.

---

## Decision 7: Prompt preflight in `execution/scheduler.py` before dispatch

**Decision**: Add a `_prompt_secret_preflight()` check in `_build_task_plan_payload()` that scans the assembled context payload using `OutputSanitizer.SECRET_PATTERNS` before `_dispatch_to_runtime()` is called. A match raises a `PolicyBlockedActionRecord` with `policy_basis="prompt_secret_detected:{secret_type}"` and publishes to `monitor.alerts`.

**Rationale**: The assembled task-plan payload from `context_engineering_service.get_plan_context()` is the last Python-controlled point before the prompt crosses into the pod environment. `OutputSanitizer.SECRET_PATTERNS` (5 compiled regexes in `policies/sanitizer.py`) already exist and are the authoritative pattern source. Reusing them at the prompt stage ensures a single source of truth (SC-008, avoiding pattern drift).

The preflight is a new private async method `_prompt_secret_preflight(payload: dict, *, execution: Execution, step: StepIR) -> None` that raises `PolicySecretLeakError` on detection, caught by the caller to abort dispatch and record the block.

**Alternatives considered**: Scanning in the Go context-assembler — rejected; `SECRET_PATTERNS` live in Python; cross-language duplication is worse. Adding a new guardrail pipeline layer — rejected; prompt assembly is in the execution bounded context, not the trust bounded context; a cross-bounded-context call for inline Python scanning adds coupling without benefit. Feature flag — not required; this is purely additive and safe-to-deploy (clean prompts are unaffected by the preflight).

---

## Decision 8: No new Kafka topics

**Decision**: Reuse the existing `monitor.alerts` topic for prompt secret detection alerts. No new topics.

**Rationale**: The spec anchor `monitor.alerts` is the platform's authoritative alert channel (Reminder 27 in the constitution). The alert payload format (standard `EventEnvelope` with `event_type="prompt_secret_detected"`) follows the existing envelope format. Per Brownfield Rule 4, new events go on existing topics; `monitor.alerts` is the correct channel.

**Alternatives considered**: New `security.alerts` topic — rejected; one more topic for the same operator audience adds operational overhead. Trust pipeline's `policy.gate.blocked` topic — rejected; that topic is for policy engine blocks; prompt secret detection is an execution-path concern.

---

## Summary: Genuine Scope (User Plan vs Reality)

| User Plan Step | Status | Actual Scope |
|---|---|---|
| 1. Create warm_pool.go | NO-OP | Already in `internal/warmpool/` |
| 2. Create secrets_injector.go | NO-OP | Already in `internal/launcher/secrets.go` |
| 3. Add Prometheus metrics | GENUINE | Extend `pkg/metrics/metrics.go` (6 metrics) |
| 4. Add gRPC endpoints | GENUINE | 2 new RPCs + messages in proto + handler impl |
| 5. Modify Python executor | GENUINE | `scheduler.py` + `runtime_controller.py` client |
| 6. Add REST API proxy | GENUINE | 2 endpoints in `execution/router.py` |
| 7. Write tests | IN SCOPE | Go unit tests + Python unit tests |
| (New) Prompt preflight (US4) | GENUINE | `scheduler._prompt_secret_preflight()` |
| (New) Target persistence | GENUINE | Alembic migration 043 |
