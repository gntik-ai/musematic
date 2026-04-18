# Feature Specification: Runtime Warm Pool and Secrets Injection

**Feature Branch**: `055-runtime-warm-pool`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "Add warm pool manager to Runtime Controller for <2s agent launch. Inject secrets from vault at pod level, never through LLM context."

**Scope note**: The core warm pool and pod-level secret injection are already in place. The Runtime Controller's `internal/warmpool/` package contains the ready-queue manager (`manager.go`), background replenisher (`replenisher.go`), and idle scanner (`idle_scanner.go`). The `internal/launcher/secrets.go` resolver already fetches Kubernetes Secrets and mounts them as projected volumes + `SECRETS_REF_*` environment variables on the launched pod. The gRPC `LaunchRuntimeResponse` already carries a `warm_start` boolean so callers can tell whether a warm pod was used. What is **not** yet done, and what this feature delivers:

1. The warm pool has **no Prometheus metrics**. The `pkg/metrics` registry today exposes `launches`, `launch_duration`, `active_runtimes`, `reconciliation_duration`, and `heartbeat_timeouts`, but nothing for `warm_pool_size`, `warm_pool_available`, `warm_pool_hit_rate`, or `cold_start_latency`. Operators cannot observe whether the pool is sized correctly, whether hit rate is meeting the sub-2s SLO, or when cold starts are happening.
2. There is **no administrative API** to inspect or configure the warm pool. The replenisher runs against a `targets map[string]int` that is initialized at startup; there is no gRPC or REST surface to read current counts, read target sizes, or update targets per workspace/agent_type without a restart.
3. The **sub-2s dispatch SLO is not measured**. Launch duration is observed globally (cold + warm combined); warm-pool-backed launches have no dedicated latency histogram, and there is no alert when warm dispatch p99 exceeds 2 s.
4. The Python side (execution engine, workflow runtime) **does not pass a warm-start preference** through the existing `RuntimeController` client wrapper, nor does it expose admin endpoints for operators to manage pool targets. Operators have to SSH into the Go service or redeploy to change pool sizing.
5. Pod-level secret injection is structurally correct, but the system has **no guarantee that secrets do not appear in the LLM prompt context**. The `OutputSanitizer` (feature 054) scrubs tool outputs; nothing scrubs the assembled prompt string fed to the LLM. A secret that arrives through a memory lookup, a user-supplied field, or a prior conversation turn can still enter the LLM call. A prompt-side preflight check using the same five secret patterns (bearer token, API key, JWT, connection string, password literal) is missing.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Warm pool hit delivers a sub-2 s agent launch (Priority: P1)

A platform operator running workflows under load wants agent launches to complete in under 2 seconds when the warm pool has available pods. The pool size is configurable per workspace and agent type; when the pool has capacity, the launch is served from a pre-warmed pod. When the pool is empty, the launch falls back to cold start (existing behavior) and the fallback is surfaced to operators.

**Why this priority**: Sub-2s launch is the headline user-visible benefit of the warm pool. Without it, the pool infrastructure already in place provides no measurable value. Operators need to see whether the SLO is met and whether the pool is sized correctly.

**Independent Test**: Configure a workspace pool of 3 pods for agent type `python-3.12`. Issue three concurrent `LaunchRuntime` requests. Measure the time from request receipt to pod-running state. All three complete in under 2 s with `warm_start=true`. Issue a fourth concurrent request; it falls back to cold start with `warm_start=false` and the cold-start latency metric increments.

**Acceptance Scenarios**:

1. **Given** a warm pool configured with 3 ready pods for `(workspace=w1, agent_type=python-3.12)`, **When** a `LaunchRuntime` request arrives for that pair, **Then** the response carries `warm_start=true`, the pod is running within 2 s p99, and the `warm_pool_available` metric for that key decrements by 1.
2. **Given** the pool for `(w1, python-3.12)` is empty and the replenisher has not yet refilled, **When** a `LaunchRuntime` request arrives, **Then** the response carries `warm_start=false`, the launch follows the cold-start path, and the `cold_start_count` metric increments.
3. **Given** warm-pool-backed launches occur, **When** operators query the dashboard, **Then** `warm_pool_hit_rate` (hits / total launches) is observable and `warm_dispatch_latency_ms` histogram is visible with p50, p95, p99 tags per workspace + agent_type.
4. **Given** warm dispatch p99 exceeds 2 s for a sustained window, **When** the alert rule evaluates, **Then** the workspace and agent_type responsible are recoverable from the alert context for operator investigation (SC-003).

---

### User Story 2 — Operators manage pool sizing without a redeploy (Priority: P1)

An operator needs to adjust the warm pool target size for a specific workspace and agent type in response to load changes. The operator uses an administrative REST endpoint to set target sizes; the change takes effect on the next replenisher tick without restarting the Runtime Controller. A companion status endpoint returns the current target and actual pod counts per `(workspace, agent_type)` key.

**Why this priority**: Without a way to change pool sizing on the fly, operators cannot respond to bursty workloads or recover from a misconfigured deployment. Redeploys are too slow for incident response.

**Independent Test**: Call the status endpoint; confirm it returns per-key target + actual counts. Call the config endpoint to increase the target for `(w1, python-3.12)` from 3 to 5. Wait one replenisher tick; call status again; confirm target is 5 and the replenisher has begun creating the additional pods. Decrease target back to 3; idle scanner removes surplus pods within one idle-scan cycle.

**Acceptance Scenarios**:

1. **Given** the Runtime Controller is running, **When** an operator calls `GET /api/v1/runtime/warm-pool/status`, **Then** the response is a list of per-key records containing `workspace_id`, `agent_type`, `target_size`, `available_count`, `dispatched_count`, `warming_count`.
2. **Given** an operator wants to adjust sizing, **When** the operator calls `PUT /api/v1/runtime/warm-pool/config` with `{"workspace_id": "w1", "agent_type": "python-3.12", "target_size": 5}`, **Then** the request returns 200, the new target is persisted, and the next replenisher tick moves toward the new target (SC-004).
3. **Given** a config update reduces the target size below the current ready-pod count, **When** the idle scanner runs its next cycle, **Then** surplus ready pods are recycled and the `warm_pool_available` metric converges to the new target.
4. **Given** an operator queries status for a workspace with no configured pool, **When** the response is returned, **Then** the workspace appears with `target_size=0` and the system does not error.

---

### User Story 3 — Secrets reach tool code via pod env vars, never the LLM prompt (Priority: P1)

A tool author declares that its pod needs `DATABASE_URL` and `API_KEY` secrets. When the Runtime Controller launches the pod, those secrets arrive in the pod's environment (and as files under `/run/secrets/`) via Kubernetes-native secret mounts. They never pass through the Python control plane's prompt-assembly path, never appear in the LLM context, and never appear in logs, events, or artifacts produced by the agent.

**Why this priority**: Secret containment at the pod boundary is the foundation of Principle XI ("secrets never in the LLM context window"). If secrets leak through the launch path, every downstream sanitizer is patching over a structural hole. This user story proves the structural guarantee.

**Independent Test**: Launch a runtime whose `secret_refs=["db-creds"]` references a Kubernetes Secret. Inside the pod, verify that `/run/secrets/DATABASE_URL` is readable and that `SECRETS_REF_DATABASE_URL=/run/secrets/DATABASE_URL` is present in the environment. Grep the Python control plane's prompt-assembly code path, event stream, and artifact uploads for the secret's value; confirm zero occurrences. Confirm the secret's value never appears in the `RuntimeContract.env_vars` field (which is bounded to non-secret env vars).

**Acceptance Scenarios**:

1. **Given** a `LaunchRuntime` request with `secret_refs=["db-creds"]` where the Kubernetes Secret `db-creds` has keys `DATABASE_URL` and `API_KEY`, **When** the pod starts, **Then** the pod has `SECRETS_REF_DATABASE_URL` and `SECRETS_REF_API_KEY` env vars pointing to `/run/secrets/*` paths, and the files contain the decoded secret values.
2. **Given** a `LaunchRuntime` request with `secret_refs` set, **When** the Python control plane emits any Kafka event related to the launch, **Then** no event payload contains the secret values; only the `secret_refs` names are observable in events and audit logs.
3. **Given** a `LaunchRuntime` request, **When** the gRPC response and all downstream Python-side objects are inspected, **Then** no field of any returned object or logged message contains the secret value.
4. **Given** the Kubernetes Secret `db-creds` is rotated, **When** the next pod launches for a runtime that references it, **Then** the pod receives the new values without requiring a Runtime Controller restart or a cache invalidation step.

---

### User Story 4 — Secret-pattern detection in the LLM prompt blocks the call and alerts (Priority: P1)

A platform operator wants defense in depth: even if a secret bypasses pod-level isolation (e.g., a prior agent left one in memory, or a user pasted one into an interaction), the system MUST detect the secret pattern in the assembled LLM prompt before the model call and refuse the call. Every such block emits an operator alert and a unified audit record.

**Why this priority**: User Story 3 provides the structural guarantee at launch time. User Story 4 provides the runtime enforcement at prompt-assembly time, closing the inter-turn leak path that structural isolation cannot catch.

**Independent Test**: Construct a prompt assembly input that contains a bearer token pattern. Submit it to the prompt preflight stage. Assert the preflight blocks the LLM call, emits an alert on the existing `monitor.alerts` Kafka topic, and writes a blocked-action record tagged with `guardrail_layer` for the prompt-secret detection. Repeat with an input containing no secret pattern — preflight passes through and the LLM call proceeds.

**Acceptance Scenarios**:

1. **Given** an assembled LLM prompt that contains a bearer token, **When** the prompt preflight runs, **Then** the LLM call does not execute, the preflight returns a denial with the matched secret type, and a blocked-action record with `policy_basis=prompt_secret_detected:{secret_type}` is created.
2. **Given** a denial occurs, **When** the alert path runs, **Then** an alert is published on `monitor.alerts` containing `secret_type`, `agent_fqn`, `workspace_id`, and `correlation_id`.
3. **Given** a clean prompt with no secret patterns, **When** the preflight runs, **Then** no block is raised and the LLM call proceeds; no audit record is created for the pass.
4. **Given** the five existing secret patterns from `OutputSanitizer` (`bearer_token`, `api_key`, `jwt_token`, `connection_string`, `password_literal`), **When** the preflight runs, **Then** all five types are recognized and each produces a distinct `secret_type` label in the audit record.

---

### User Story 5 — Cold-start path stays available as a fallback (Priority: P2)

When the warm pool is empty, sized at zero, or the pool manager itself is unavailable (degraded state), agent launches MUST still succeed via the existing cold-start path. Cold starts are slower than warm starts, but never a hard failure. Operators see `warm_start=false` in the launch response and the `cold_start_count` metric increments.

**Why this priority**: The warm pool is a latency optimization, not a correctness dependency. A degraded pool must never cause agent launches to fail. This story makes the graceful-degradation contract explicit and testable.

**Independent Test**: Set the warm pool target to 0 for `(w1, test-agent)`. Issue five concurrent launches; all five succeed via cold start, `warm_start=false`, and the `cold_start_count` metric increments by five. Force the warm pool manager into a simulated failure state; launches still succeed.

**Acceptance Scenarios**:

1. **Given** the warm pool target is 0 for a key, **When** a launch arrives, **Then** the launch succeeds via cold start with `warm_start=false`; no error is raised due to missing pool capacity.
2. **Given** the warm pool manager returns an error on `Dispatch`, **When** a launch arrives, **Then** the launch falls through to cold start and succeeds; the error is logged but not surfaced to the caller.
3. **Given** the warm pool is at capacity (all ready pods dispatched), **When** another launch arrives before replenisher refills, **Then** the launch takes the cold-start path and completes successfully.

---

### Edge Cases

- Pool target set above the Kubernetes namespace's pod quota → replenisher creates as many as quota allows; remaining target is unfulfilled and `warm_pool_warming` metric surfaces the gap.
- Replenisher creates a pod that never reaches `Running` (image pull failure, scheduling failure) → pod is marked as failed and removed from the ready queue; the replenisher retries on the next tick with a fresh pod name.
- Warm pod's lifetime exceeds an idle window without a dispatch → idle scanner recycles it (`ready` → terminated); the replenisher creates a replacement.
- `secret_refs` references a Kubernetes Secret that does not exist → launch fails fast with a structured error; the failure does NOT fall back to a cold start pretending the secret is optional.
- Prompt preflight sees a secret pattern inside a benign context (e.g., the word "Bearer" not followed by a token) → the five patterns are tuned to match realistic token shapes; one-off false positives are preferable to missed detections, and the audit record carries enough detail for operators to tune if needed.
- Two operators issue concurrent `PUT /warm-pool/config` updates for the same key → last-write-wins; both requests return 200; replenisher converges on the latest target.
- Admin REST endpoint is called without the `platform_admin` role → 403.
- Cold-start latency briefly exceeds 2 s under unusual conditions (node scale-up, image pull) → no SLO applies to cold starts; only warm dispatch is bounded by the 2 s target.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Runtime Controller MUST expose Prometheus metrics `warm_pool_available{workspace_id,agent_type}` (gauge, ready pod count), `warm_pool_target{workspace_id,agent_type}` (gauge, configured target), `warm_pool_warming{workspace_id,agent_type}` (gauge, pods in warming state), `warm_pool_dispatches_total{workspace_id,agent_type}` (counter), `cold_start_count_total{workspace_id,agent_type}` (counter), and `warm_dispatch_latency_ms{workspace_id,agent_type}` (histogram).
- **FR-002**: The Runtime Controller MUST expose two new gRPC methods on `RuntimeControlService`: `WarmPoolStatus(WarmPoolStatusRequest) returns (WarmPoolStatusResponse)` and `WarmPoolConfig(WarmPoolConfigRequest) returns (WarmPoolConfigResponse)`. Both are additive; existing seven RPCs are unchanged.
- **FR-003**: The Runtime Controller MUST persist warm-pool target configuration so that targets survive a restart. A restart MUST reconverge to the persisted targets on the next replenisher tick.
- **FR-004**: When a `LaunchRuntime` request is served from a warm pod, the response MUST set `warm_start=true` and the time from request receipt to `pod running` MUST be under 2 seconds at p99 (SC-002).
- **FR-005**: When the warm pool has no available pod for the requested `(workspace_id, agent_type)` key, the launch MUST fall through to the existing cold-start path and return `warm_start=false`; no error is raised solely because of empty pool.
- **FR-006**: Pod launches MUST pass the request's `secret_refs` to the existing `ResolveSecrets` path, mount each referenced Kubernetes Secret as a projected volume under `/run/secrets/`, and set `SECRETS_REF_{KEY}` environment variables pointing to those files (existing behavior; preserved).
- **FR-007**: Secret values MUST never appear in any event payload, gRPC response body, log line, audit record, or artifact produced by the launch path or downstream Python control plane. Only the secret names (not values) appear in `secret_refs`.
- **FR-008**: The Python control plane MUST add a prompt-preflight stage that scans the assembled LLM prompt against the five secret patterns (`bearer_token`, `api_key`, `jwt_token`, `connection_string`, `password_literal`) before the LLM call is issued. A match MUST block the LLM call.
- **FR-009**: A prompt-preflight block MUST produce a blocked-action record tagged with `policy_basis="prompt_secret_detected:{secret_type}"` and publish an alert on the existing `monitor.alerts` Kafka topic carrying `secret_type`, `agent_fqn`, `workspace_id`, and `correlation_id`.
- **FR-010**: The Python control plane MUST expose `GET /api/v1/runtime/warm-pool/status` (returns per-key target + actual counts) and `PUT /api/v1/runtime/warm-pool/config` (updates target for a `(workspace_id, agent_type)` pair). Both endpoints require the `platform_admin` role.
- **FR-011**: The Python admin endpoints MUST delegate to the gRPC `WarmPoolStatus` / `WarmPoolConfig` methods via the existing `RuntimeController` client wrapper; no direct state access.
- **FR-012**: The execution engine's runtime-dispatch call path MUST pass a warm-pool preference through to the `LaunchRuntime` request. The preference MUST default to `prefer_warm=true`; operators or specific workloads MAY opt out.
- **FR-013**: When the warm pool manager returns an error on `Dispatch`, the launch MUST fall through to cold start; the error MUST be logged but NOT surfaced to the caller (graceful degradation; FR-005 generalized).
- **FR-014**: Target-size changes via `WarmPoolConfig` MUST take effect on the next replenisher tick without requiring a Runtime Controller restart (SC-004).
- **FR-015**: Behavior when the warm pool manager is disabled or when no target is configured for a key MUST be identical to the pre-feature cold-start-only behavior (no new failures, backward compatible; SC-006).

### Key Entities

- **Warm Pool Target**: A configured `(workspace_id, agent_type, target_size)` triple. The replenisher drives the actual ready-pod count toward the target. Newly persisted by this feature; survives restart.
- **Warm Pool Status Record**: A read-only projection returned by the status API: per-key `target_size`, `available_count`, `dispatched_count`, `warming_count`, `last_dispatch_at`.
- **Warm Dispatch Event**: A metric-only event emitted on each pool hit; records workspace, agent_type, dispatch latency, correlation id. Not a first-class Kafka event.
- **Cold Start Event**: A metric-only event emitted on each pool miss; records the same dimensions plus `reason` (pool empty / pool error / target zero).
- **Prompt Secret Detection Record**: A blocked-action record created when the prompt preflight matches a secret pattern; carries `secret_type`, `agent_fqn`, `workspace_id`, `correlation_id`. Queryable via the existing blocked-actions surface.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Warm-pool-backed launches constitute at least 90% of launches in a workspace whose pool target matches its steady-state concurrency, measured over a 1-hour window.
- **SC-002**: Warm dispatch p99 latency is under 2 seconds, measured from `LaunchRuntime` request receipt to pod `Running` state, across 10 000 consecutive warm-path launches.
- **SC-003**: Operators can identify the workspace and agent_type driving any warm dispatch SLO breach within 5 minutes using the `warm_dispatch_latency_ms` histogram dimensions.
- **SC-004**: A target-size change issued via the admin API takes effect on the next replenisher tick (default ≤30 seconds) without a service restart.
- **SC-005**: 100% of prompt-preflight secret detections produce a blocked-action record and a `monitor.alerts` alert within 60 seconds of the detection.
- **SC-006**: With the warm pool disabled (target=0 on all keys), existing test suites pass unmodified; cold-start behavior is identical to pre-feature (FR-015).
- **SC-007**: Zero occurrences of any `secret_refs` secret value appear in any event payload, log line, or artifact, measured by an automated scan of a sampled 24-hour window of platform output.
- **SC-008**: The five secret patterns currently recognized by `OutputSanitizer` are also recognized at prompt preflight; a verification fixture matching each pattern produces a block for every pattern (100% coverage across the five types).

---

## Assumptions

- The Runtime Controller's warm pool manager (`internal/warmpool/manager.go`), replenisher (`internal/warmpool/replenisher.go`), idle scanner (`internal/warmpool/idle_scanner.go`), and secret resolver (`internal/launcher/secrets.go`) are already implemented and correct. This feature does not re-implement them.
- The `pkg/metrics` registry is the authoritative Prometheus endpoint for the Runtime Controller; adding warm-pool metrics extends the existing `/metrics` endpoint rather than creating a new one.
- The existing `LaunchRuntimeResponse.warm_start` boolean is the canonical signal for warm-vs-cold dispatch and continues to be used.
- Prompt preflight reuses the five `SECRET_PATTERNS` compiled by `OutputSanitizer` (feature 028 / 054). A single source of truth for secret patterns avoids drift.
- The `monitor.alerts` Kafka topic is the authoritative alert channel (per the platform's Kafka topic registry).
- Target-size persistence uses the existing Runtime Controller PostgreSQL schema (add one new table `runtime_warm_pool_targets` via Alembic migration; the exact schema is a plan-phase decision). No new data store is introduced.
- The Python `RuntimeController` client wrapper is extended additively with `warm_pool_status()` and `warm_pool_config()` methods that map to the new gRPC calls.
- Secret mounts follow the existing projected-volume pattern (`/run/secrets/{key}` + `SECRETS_REF_{KEY}` env vars). No change to the in-pod contract.
- Guiding Principle XI ("secrets never in the LLM context window") is the anchor for US3 and US4. US3 enforces the pod-side structural guarantee; US4 enforces the prompt-side runtime detection.
