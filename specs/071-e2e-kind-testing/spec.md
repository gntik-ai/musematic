# Feature Specification: End-to-End Testing on kind (Kubernetes in Docker)

**Feature Branch**: `071-e2e-kind-testing`
**Created**: 2026-04-20
**Status**: Draft
**Input**: User description: "End-to-End Testing on kind (Kubernetes in Docker) — provide a complete ephemeral E2E testing environment on a local kind cluster, seeded with deterministic test data, covering every bounded context, with chaos injection and performance smoke tests, running on every PR and nightly."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Developer runs the full platform locally on an ephemeral Kubernetes cluster (Priority: P1) 🎯 MVP

A platform developer wants to verify their change works against the real platform stack — not against docker-compose mocks or in-process fakes — before opening a pull request. They run a single command that provisions a complete ephemeral Kubernetes cluster on their laptop, installs the platform using the same Helm charts that production uses, seeds deterministic test data, and leaves the platform reachable at `http://localhost:8080` (UI), `http://localhost:8081` (API), and `ws://localhost:8082` (WebSocket). When finished, another single command destroys the cluster leaving zero artifacts.

**Why this priority**: Without a real-cluster harness, developers cannot detect the class of bugs that only manifest when pods restart, services resolve via DNS, NetworkPolicy enforces isolation, or Helm templating produces subtly different config. This is the MVP — every other user story in this feature depends on having a working ephemeral cluster.

**Independent Test**: On a 16 GB laptop with Docker installed, run `make e2e-up`; verify the platform UI loads at `http://localhost:8080`, the API responds at `http://localhost:8081/api/v1/healthz`, and the WebSocket accepts connections at `ws://localhost:8082`. All 15+ seeded entities (admin user, namespaces, agents per role type, tools, policies, certifiers, fleets, goals) must be retrievable via the API. Run `make e2e-down`; verify `kind get clusters` shows no residual cluster and `docker ps` shows no stray containers.

**Acceptance Scenarios**:

1. **Given** a developer with Docker and kind installed, **When** they run `make e2e-up`, **Then** the cluster is provisioned, the platform installs via Helm, seed data is loaded, and the environment is ready within 10 minutes; a ready banner prints the URLs.
2. **Given** the cluster is running, **When** the developer queries `GET /api/v1/agents`, **Then** at least one agent per role type (executor, planner, orchestrator, observer, judge, enforcer) appears in the list.
3. **Given** the cluster is running, **When** the developer runs `make e2e-down`, **Then** the cluster is deleted, no containers remain, and no local filesystem volumes are left behind.
4. **Given** the developer modifies a platform image and runs `make e2e-up` again, **When** cluster provisioning starts, **Then** the locally-built image is loaded into the cluster before Helm install.
5. **Given** a Helm install failure, **When** the `--wait` timeout elapses, **Then** the error output identifies which subchart or pod failed, and the developer can inspect pod events via `make e2e-logs`.

---

### User Story 2 — Bounded-context test suites validate every vertical slice end-to-end (Priority: P1)

Platform developers and QA engineers want automated tests that exercise each bounded context through the real platform boundaries — HTTP endpoints, WebSocket channels, Kafka topics, PostgreSQL state — instead of mocking those interfaces. A test author writes a test in the relevant suite directory and relies on shared fixtures (authenticated HTTP client, WebSocket client, database session, Kafka consumer, deterministic seeding, mock LLM control). The suite runs against the kind cluster and produces JUnit XML + HTML reports.

**Why this priority**: Every bounded context listed in the platform constitution must have E2E coverage; without it, regressions silently cross boundaries (e.g., an event schema change that breaks a downstream subscriber). This is the core test value delivered by the feature.

**Independent Test**: With a running E2E cluster, run `make e2e-test`; verify that each of the 20+ bounded-context suites (auth, registry, trust, governance, interactions, workflows, fleets, reasoning, evaluation, agentops, discovery, a2a, mcp, runtime, storage, ibor) executes and reports pass/fail. A deliberate breaking change in one bounded context must cause only that suite to fail, not cascade into unrelated suites.

**Acceptance Scenarios**:

1. **Given** the E2E cluster is up, **When** `make e2e-test` runs, **Then** every suite under `tests/e2e/suites/<bounded-context>/` executes and produces a JUnit XML entry.
2. **Given** a test needs authentication, **When** it requests the `http_client` fixture, **Then** the fixture returns a pre-authenticated client using the seeded admin user and injects a valid JWT on every request.
3. **Given** a test needs to verify an event was published, **When** it requests the `kafka_consumer` fixture for a topic, **Then** the consumer returns events published during the test window with correlation IDs matching the test's request.
4. **Given** a test needs deterministic LLM output, **When** it calls a mock-LLM-set-response helper before triggering an LLM-using flow, **Then** the platform returns exactly that response and no real LLM call is made.
5. **Given** two suites run back-to-back, **When** the second suite starts, **Then** it can assume either (a) the seeder has been re-run or (b) explicit test isolation is enforced — no test depends on residual state from another suite.
6. **Given** a test fails, **When** the runner collects artifacts, **Then** the JUnit XML includes the failure message, the HTML report includes the stack trace, and per-pod logs from the failure window are captured.

---

### User Story 3 — Chaos scenarios validate platform recovery under failure (Priority: P2)

Platform reliability engineers want confidence that the platform recovers gracefully when components fail mid-execution: runtime pods killed, reasoning-engine connections dropped, Kafka brokers restarted, S3 credentials revoked, network partitions installed, policy evaluation timed out. They run a chaos suite that injects each failure via admin-only dev endpoints and asserts that the platform returns to a healthy state (checkpoints replay, producers retry, circuit breakers open, fail-closed defaults hold).

**Why this priority**: Recovery-under-failure is the property that distinguishes a production-ready distributed system from a happy-path prototype. These tests cannot run in docker-compose because only a real Kubernetes scheduler exhibits the pod-lifecycle events that the platform depends on. They are P2 because the MVP (US1+US2) delivers core verification value first; chaos layers on correctness-under-perturbation.

**Independent Test**: With a running E2E cluster, run `make e2e-chaos`; verify all 6 chaos scenarios pass — each asserts a specific recovery outcome (checkpoint replay, producer retry without event loss, circuit breaker open then close, fail-closed policy default) rather than merely "the platform didn't crash".

**Acceptance Scenarios**:

1. **Given** a long-running execution is in progress, **When** the runtime pod hosting the execution is killed via the dev chaos endpoint, **Then** the execution resumes from its last checkpoint within the configured recovery window and completes successfully.
2. **Given** the reasoning engine has an active streaming call, **When** the engine pod is killed, **Then** the control plane reconnects, replays the trace from the last acknowledged event, and the caller sees no dropped events.
3. **Given** a Kafka broker is restarted mid-burst, **When** the burst completes, **Then** all events produced during the outage are delivered exactly-once to consumers and none are lost.
4. **Given** S3 credentials are revoked while an artifact upload is in flight, **When** the upload retries, **Then** the platform surfaces a clear, actionable error to the caller rather than an opaque network timeout.
5. **Given** a NetworkPolicy partitions the reasoning engine from PostgreSQL, **When** the control plane tries to fetch state, **Then** the circuit breaker opens within the configured window and requests fail-fast instead of hanging.
6. **Given** a policy evaluation exceeds its timeout, **When** the enforcement gate closes, **Then** the action is denied (fail-closed default) and an audit record captures the timeout reason.

---

### User Story 4 — Performance smoke tests catch latency and throughput regressions (Priority: P2)

Platform developers want early warning when a change regresses the four headline performance properties: warm-pool cold-start latency, trivial-agent round-trip, concurrent-execution throughput, and reasoning overhead. They run a performance suite that exercises each property and fails if the measured value exceeds the target threshold. These are smoke tests, not load tests: they catch order-of-magnitude regressions, not sub-percent drift.

**Why this priority**: Performance regressions accumulate silently. A 200ms regression here, a 500ms regression there, and soon the p95 exceeds the SLO. Catching order-of-magnitude regressions on every PR is cheap insurance. P2 because it is additive to correctness coverage (US1+US2+US3).

**Independent Test**: With a running E2E cluster, run `make e2e-perf`; verify all 4 performance smoke tests pass with measurements within the target thresholds: warm-pool launch < 2 s, cold launch < 10 s, trivial agent round-trip < 5 s, 10 concurrent executions complete successfully, reasoning overhead < 50 ms per step.

**Acceptance Scenarios**:

1. **Given** the warm pool is filled, **When** an execution is dispatched, **Then** the container is ready to accept work within 2 seconds.
2. **Given** the warm pool is empty, **When** an execution is dispatched, **Then** a fresh container is ready within 10 seconds.
3. **Given** a trivial agent that returns a constant response, **When** an end-to-end execution runs, **Then** the round-trip time from request to final response is under 5 seconds.
4. **Given** 10 executions are triggered simultaneously, **When** they all complete, **Then** none fail and the maximum wall-clock time is within the expected concurrency ceiling.
5. **Given** a reasoning-enabled step executes, **When** the step completes, **Then** the reasoning overhead (reasoning-enabled duration minus baseline duration) is under 50 ms.

---

### User Story 5 — CI runs E2E on every PR and nightly on main (Priority: P2)

Release engineers and the engineering team want every PR to run the full E2E suite automatically before merge, and a nightly run on main to catch regressions in dependencies (upstream images, Helm chart updates, base OS patches). Failures surface JUnit XML, HTML reports, per-pod logs, and a cluster state dump as downloadable artifacts so the PR author can debug without reproducing locally.

**Why this priority**: Without CI gating, E2E tests decay into a suite nobody runs. A mandatory PR check forces the tests to stay green and forces test authors to keep them fast and reliable. P2 because the MVP must first work locally (US1+US2) before CI can enforce it.

**Independent Test**: Open a pull request; verify the E2E workflow runs to completion within the allotted timeout; verify that on failure the uploaded artifacts include JUnit XML, HTML reports, per-pod logs, and a state dump sufficient to diagnose the failure without cluster access.

**Acceptance Scenarios**:

1. **Given** a pull request is opened, **When** the CI E2E workflow triggers, **Then** it provisions a kind cluster, installs the platform, runs suites + chaos + performance, and reports pass/fail to the PR check.
2. **Given** the CI workflow fails at any stage, **When** post-step artifact collection runs, **Then** JUnit XML, HTML report, tailed logs, and a state dump are uploaded and downloadable from the workflow run page.
3. **Given** a nightly schedule, **When** it fires on main, **Then** the same workflow runs and posts a summary (pass/fail counts, duration, link to artifacts) to the team's notification channel.
4. **Given** the CI workflow is already running on a PR, **When** a new commit lands on the same branch, **Then** the in-flight run is canceled and a fresh run starts.
5. **Given** an unexpected infrastructure flake (image pull, kind provisioning timeout), **When** the author retries the workflow, **Then** re-runs are idempotent — no leftover state from the previous run affects the new run.

---

### User Story 6 — Parallel clusters, deterministic mocks, and safe production defaults (Priority: P3)

Advanced contributors — power-user developers and the platform team — occasionally need to run two E2E clusters side-by-side (e.g., comparing a release candidate vs. main) without port collisions or cluster-name conflicts. The deterministic mock LLM must behave identically across runs. And any dev-only endpoint exposed for seeding or chaos injection must return 404 in a production deployment so the E2E harness cannot be weaponized against production.

**Why this priority**: These properties guard against specific edge cases rather than delivering primary test value. They are P3 because they matter to advanced users and to production safety but are not required for the day-one workflow.

**Independent Test**:
1. Start two clusters with different `CLUSTER_NAME` values on the same host; both healthy, no port collisions.
2. Run the same mock-LLM-driven test 10 times; every run produces identical LLM outputs.
3. Deploy the platform with `FEATURE_E2E_MODE=false` (production default); verify every `/api/v1/_e2e/*` endpoint returns 404.

**Acceptance Scenarios**:

1. **Given** one cluster `amp-e2e-a` is running on ports 8080/8081/8082, **When** a second cluster `amp-e2e-b` is provisioned with `CLUSTER_NAME=amp-e2e-b` and a different port range, **Then** both run side-by-side with no collision.
2. **Given** a test pre-populates the mock LLM response queue with a fixed sequence, **When** the test is run repeatedly, **Then** the LLM responses and their order are byte-identical across runs.
3. **Given** the platform is deployed with `FEATURE_E2E_MODE=false`, **When** any `/api/v1/_e2e/seed`, `/api/v1/_e2e/reset`, `/api/v1/_e2e/chaos/*`, `/api/v1/_e2e/mock-llm/*`, or `/api/v1/_e2e/kafka/events` endpoint is called, **Then** the response is 404 and no action is taken.
4. **Given** the mock LLM queue is empty and a test triggers an LLM call, **When** the platform processes the call, **Then** a default deterministic response matching the prompt template is returned — no real LLM API is ever called in E2E mode.

---

### Edge Cases

- **Laptop out of memory mid-provisioning**: `make e2e-up` must fail fast with a clear message identifying the constrained component (typically Kafka or ClickHouse requesting > 512 Mi RAM) rather than hanging.
- **kind binary missing or wrong version**: `make e2e-up` detects and prints an actionable error ("kind ≥ 0.23 required; found X; install via…") before attempting cluster creation.
- **Helm install exceeds 10-minute timeout**: the harness captures the state of every non-Ready pod and prints a summary table (pod, status, last event) before exiting non-zero.
- **Seeder rerun on an already-seeded cluster**: all seeders must be idempotent; second run produces no duplicate rows and no errors.
- **Test leaves residual state**: suite-level teardown must detect and either clean up or mark the cluster tainted; next suite starts from a known-good baseline.
- **Mock LLM queue drained mid-test**: if the queue empties unexpectedly, the fallback deterministic response must be emitted and a warning logged — tests should not silently fail.
- **Port already in use on host**: `make e2e-up` detects the collision pre-provision and suggests an alternate `CLUSTER_NAME` + port mapping or prints the offending process.
- **Image pull fails for a locally-built image**: the `load-images` step surfaces which image failed and offers a retry without recreating the cluster.
- **Chaos scenario leaves the cluster in a wedged state**: chaos fixtures must reverse the injected failure in teardown (delete the NetworkPolicy, revert the revoked credential) so downstream suites can run.
- **CI artifact upload fails**: workflow still reports the failure to the PR; a best-effort log dump is embedded in the workflow output as fallback.
- **Concurrent E2E workflows on the same branch**: only the most recent run is retained; earlier runs are canceled to save CI minutes.

## Requirements *(mandatory)*

### Functional Requirements

**Cluster provisioning and teardown**

- **FR-001**: The harness MUST provision an ephemeral Kubernetes cluster using kind with a deterministic topology (one control-plane node, two worker nodes) and published host port mappings for UI, API, and WebSocket.
- **FR-002**: The harness MUST install the platform using the same Helm chart that production uses, with a single scaled-down values overlay; no alternate chart or bypass path may exist.
- **FR-003**: The harness MUST load all locally-built platform images into the cluster before Helm install so uncommitted code changes can be tested.
- **FR-004**: The harness MUST complete provisioning (cluster + Helm install + seeding) within 10 minutes on a 16 GB laptop under nominal conditions.
- **FR-005**: The harness MUST provide a single command that tears down the cluster and leaves zero residual artifacts (no containers, no volumes, no leftover images tied to the cluster).
- **FR-006**: The harness MUST allow multiple clusters to run concurrently on the same host by parameterizing the cluster name and port range.

**Test execution and fixtures**

- **FR-007**: The harness MUST provide test suites organized by bounded context (one directory per context), covering at minimum: auth, registry, trust, governance, interactions, workflows, fleets, reasoning, evaluation, agentops, discovery, a2a, mcp, runtime, storage, ibor.
- **FR-008**: The harness MUST provide shared fixtures for: authenticated HTTP client, WebSocket client, direct database session for assertion-level state checks, Kafka consumer for event assertions, workspace factory, agent factory with FQN, policy attachment factory, mock LLM response control.
- **FR-009**: The harness MUST seed a deterministic set of baseline entities (users with distinct roles; namespaces including default, test-finance, test-eng; agents covering every role type; mock HTTP and code tools; sample policies; internal and third-party certifiers; a small fleet; workspace goals in various lifecycle states) idempotently.
- **FR-010**: The harness MUST produce per-run reports in JUnit XML and HTML formats for each of: bounded-context suites, chaos scenarios, performance smoke tests.

**Chaos injection**

- **FR-011**: The harness MUST include chaos scenarios that validate recovery from: runtime pod kill, reasoning-engine pod kill, Kafka broker restart, S3 credential revocation, network partition, policy evaluation timeout.
- **FR-012**: Each chaos scenario MUST assert a specific recovery outcome (checkpoint replay, event-loss-free retry, circuit-breaker open/close, fail-closed default) rather than merely surviving the perturbation.
- **FR-013**: Chaos scenario teardown MUST reverse any injected failure (delete NetworkPolicies, restore credentials) so downstream suites run against a clean baseline.

**Performance smoke tests**

- **FR-014**: The harness MUST include performance smoke tests for: warm-pool launch latency, cold-start launch latency, trivial-agent round-trip, concurrent-execution throughput, per-step reasoning overhead.
- **FR-015**: Each performance test MUST have a named threshold; a measurement exceeding the threshold MUST cause the test to fail with the measured vs. expected values reported.

**Mock LLM provider**

- **FR-016**: When the E2E feature flag is enabled, the platform MUST route every LLM call through a mock provider that returns deterministic responses; no real LLM API call may occur in E2E mode.
- **FR-017**: The mock LLM provider MUST accept a pre-populated response queue set by tests; responses MUST be returned in FIFO order.
- **FR-018**: When the queue is empty, the mock LLM provider MUST return a default deterministic response matched by prompt template so tests never silently depend on queue state.
- **FR-019**: The mock LLM provider MUST record every call (prompt, metadata, returned response) for post-test assertion.
- **FR-020**: The mock LLM provider MUST support a streaming mode that chunks the queued response into server-sent events for callers that expect streaming.

**Dev-only platform endpoints**

- **FR-021**: The platform MUST expose dev-only endpoints under `/api/v1/_e2e/*` for: triggering full seeding, resetting workspace data, chaos injection (kill-pod, partition-network), mock LLM queue control, reading events from Kafka topics.
- **FR-022**: Every `/api/v1/_e2e/*` endpoint MUST return 404 when the E2E feature flag is off; this MUST be the production default.
- **FR-023**: The seed and reset endpoints MUST require the seeded admin account or a service-account credential with an explicit E2E scope; no anonymous access.
- **FR-024**: The chaos endpoints MUST fail safely if the target pod or resource does not exist; they MUST NOT affect pods or resources outside the E2E namespace.

**CI integration**

- **FR-025**: A CI workflow MUST run the full E2E suite on every pull request and on a nightly schedule against the main branch.
- **FR-026**: The CI workflow MUST complete within a defined maximum runtime (45 minutes) under nominal conditions; a timeout reports the phase that was in progress.
- **FR-027**: The CI workflow MUST upload JUnit XML, HTML reports, per-pod log tails, and a state dump as downloadable artifacts; these MUST be retained long enough for post-failure triage.
- **FR-028**: Concurrent runs on the same pull request branch MUST cancel the in-flight run and start a fresh run.

**Observability and debugging**

- **FR-029**: The harness MUST provide commands to tail platform logs (`e2e-logs`) and to open a shell in the control-plane container (`e2e-shell`) for interactive debugging.
- **FR-030**: On test failure, the harness MUST capture a state dump (pod list, events, Helm release status, last 100 lines of every platform pod) to aid remote triage.

### Key Entities

- **kind cluster** — an ephemeral Kubernetes-in-Docker cluster identified by name; has a topology (1 control-plane + 2 workers) and a set of host port mappings. Lifecycle: created by `e2e-up`, destroyed by `e2e-down`.
- **Helm release** — a named installation of the platform chart inside the cluster; driven by a values overlay (`values-e2e.yaml`) distinct from production values only in scale and feature-flag settings.
- **Seeded fixtures** — deterministic baseline data (users, namespaces, agents, tools, policies, certifiers, fleets, workspace goals) loaded idempotently before tests run.
- **Test suite** — a directory of pytest modules targeting a single bounded context; each module acquires shared fixtures from `conftest.py`.
- **Chaos scenario** — a test that injects a failure (pod kill, network partition, credential revoke, etc.) and asserts a named recovery outcome.
- **Performance smoke test** — a test that measures a named latency or throughput property against a named threshold.
- **Mock LLM response queue** — a FIFO of pre-populated responses owned by the mock LLM provider; a default deterministic response is returned when the queue is empty.
- **Dev-only endpoint** — an HTTP route under `/api/v1/_e2e/*` that is exposed only when the E2E feature flag is on; returns 404 otherwise.
- **Run artifact bundle** — JUnit XML, HTML report, log tail, state dump uploaded as one logical artifact per CI run for post-failure triage.
- **Feature flag `FEATURE_E2E_MODE`** — a boolean that toggles all dev-only endpoints and the mock LLM provider; defaults to `false` in production deployments.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer on a 16 GB laptop with Docker installed can run `make e2e-up` and reach a fully seeded, healthy platform within 10 minutes on ≥ 95% of attempts under nominal network conditions.
- **SC-002**: `make e2e-down` removes the cluster and all associated resources on 100% of attempts with zero manual cleanup required; no orphaned containers, volumes, or Docker networks remain.
- **SC-003**: Every bounded context in the platform constitution (≥ 16 contexts) has at least one E2E suite that exercises it through the real HTTP/WebSocket/Kafka/database boundaries; a deliberate breaking change in one context fails only that context's suite (no cascade failures in unrelated contexts).
- **SC-004**: All six chaos scenarios (runtime pod kill, reasoning-engine pod kill, Kafka broker restart, S3 credential revoke, network partition, policy timeout) pass on a fresh cluster with the platform recovering to a verifiably healthy state in each case.
- **SC-005**: All four performance smoke tests (warm launch < 2 s, cold launch < 10 s, trivial round-trip < 5 s, 10-concurrent throughput, reasoning overhead < 50 ms/step) pass with headroom on the reference CI runner.
- **SC-006**: Every pull request triggers the E2E workflow automatically; the workflow completes within 45 minutes on ≥ 90% of runs; on failure, downloadable artifacts include JUnit XML, HTML report, log tails, and a state dump sufficient to diagnose the failure without cluster access.
- **SC-007**: On a deployment with `FEATURE_E2E_MODE=false` (production default), every `/api/v1/_e2e/*` endpoint returns 404 — verified by a static contract test that enumerates the endpoints.
- **SC-008**: The mock LLM provider produces byte-identical responses across 10 consecutive runs of the same test with the same pre-populated queue — proven by a determinism test in CI.
- **SC-009**: Two E2E clusters can run on the same host simultaneously with distinct `CLUSTER_NAME` values and distinct port mappings; both remain healthy and neither interferes with the other.
- **SC-010**: The production Helm chart and the E2E Helm chart are the same chart version; E2E differs only via a values overlay — verified by a chart-identity check that fails if a separate `Chart.yaml` is introduced under `tests/e2e/`.

## Assumptions

- Developers running E2E locally have Docker (≥ 24), kind (≥ 0.23), helm (≥ 3.14), and Python (≥ 3.12) installed; the Makefile detects and reports missing prerequisites rather than installing them.
- A 16 GB laptop is the reference development machine; the scaled-down Helm overlay targets this footprint. Laptops with less memory may require further scaling down, which is out of scope.
- CI uses a Linux runner with ≥ 8 CPU cores and ≥ 16 GB RAM (e.g., GitHub `ubuntu-latest-8-cores` or equivalent); smaller runners are not supported.
- MinIO is used for object storage in E2E for convenience via the same generic S3 client path used in production; no AWS S3 bucket or third-party provider is required to run E2E.
- Zero-trust visibility is ENABLED in E2E (default ON per the overlay) to catch regressions; it remains optional per workspace in production.
- The mock LLM provider is the only LLM path active in E2E; semantic and behavioral LLM quality regressions are explicitly out of scope (covered by a separate feature).
- Load and stress testing are NOT in scope; the performance suite catches order-of-magnitude smoke regressions only.
- The E2E harness lives in `tests/e2e/` at the repository root (not inside the control-plane monolith) so it can orchestrate Kubernetes without being part of any deployed service.
- Only admin users and service accounts with an explicit E2E scope can invoke dev-only endpoints; anonymous access is always rejected regardless of feature-flag state.
- CI runner image cache is warmed enough that platform image pulls during provisioning complete within the 10-minute budget; cold-cache runs may exceed the target and are tolerated in CI (not in laptop runs).
