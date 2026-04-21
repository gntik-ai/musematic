# Research & Decisions: End-to-End Testing on kind

**Feature**: 071-e2e-kind-testing
**Date**: 2026-04-20

## Context

The platform has never had E2E tests against a real Kubernetes cluster. Existing tests are split across Python unit (`pytest`), integration (docker-compose + `pytest`), and Go unit (`go test`). This feature introduces a third tier — kind-based E2E — that exercises the same Helm chart used in production and validates every bounded context through real HTTP/WebSocket/Kafka/database boundaries. Constitution Reminder 26 explicitly mandates this approach: "E2E tests run on kind, not docker-compose … same Helm charts as production — no test-only bypass paths."

## Existing State (Baseline)

| Component | Location | Status |
|---|---|---|
| Production Helm chart | `deploy/helm/platform/` | ✅ Reuse — no fork |
| Control-plane FastAPI factory | `apps/control-plane/src/platform/main.py` | ✅ Extend: conditionally mount `router_e2e` |
| `testing/` bounded context | `apps/control-plane/src/platform/testing/` | ✅ Extend: add `router_e2e.py`, `service_e2e.py`, `schemas_e2e.py` |
| `common/config.py` Pydantic settings | `apps/control-plane/src/platform/common/config.py` | ✅ Extend: add `feature_e2e_mode: bool = False` |
| `common/llm/` | `apps/control-plane/src/platform/common/llm/` | ✅ Extend: add `mock_provider.py`; modify `router.py` to route when flag on |
| Existing per-context `tests/e2e/` | `apps/control-plane/tests/e2e/` | ⚠️ Rename to `tests/integration/` (D-004) |
| CI workflows | `.github/workflows/` | ✅ Extend: add `e2e.yml` |
| Existing pytest fixtures | `apps/control-plane/tests/conftest.py` | ✅ Reuse patterns; new harness has its own `conftest.py` at repo root |

---

## Decisions

### D-001: Use kind ≥ 0.23 for cluster orchestration — not k3d, not minikube

**Decision**: Kubernetes-in-Docker (`kind`) is the single supported local-cluster tool. Minimum version 0.23 pins the kind-config v1alpha4 API and `kind load docker-image` parallelism fix. The Makefile detects kind < 0.23 and refuses to proceed.

**Rationale**: kind has three properties the competition lacks: (a) first-class GitHub Actions integration via `helm/kind-action@v1` with built-in cluster caching; (b) deterministic control-plane + worker topology (matches production more closely than minikube's single-node); (c) `kind load docker-image` loads a locally-built image into the cluster without pushing to a registry — critical for developer feedback loop. k3d is lighter but its embedded registry story is messier; minikube has too many drivers and too many moving parts.

**Alternatives considered**:
- k3d — rejected: embedded registry would require tagging images with a cluster-specific hostname; slower onboarding for new contributors.
- minikube — rejected: multiple drivers (Docker, VirtualBox, hyperkit) create platform drift; E2E must be reproducible.
- Real cloud Kubernetes (EKS/GKE) — rejected: too slow for PR gating; cost and auth complexity.

---

### D-002: Reuse the production Helm chart; overlay via `values-e2e.yaml` only

**Decision**: All E2E-specific customization lives in `tests/e2e/cluster/values-e2e.yaml`, applied with `helm install … -f values-e2e.yaml`. No fork of the chart. A chart-identity test (`test_no_separate_chart_for_e2e`) enumerates the filesystem under `tests/e2e/` and fails the suite if any `Chart.yaml` appears.

**Rationale**: SC-010 demands identical charts in production and E2E — "no test-only bypass paths" (Constitution Reminder 26). Forking the chart would drift silently and defeat the purpose of E2E. Helm values overlays are the idiomatic way to scale replicas, reduce resources, toggle feature flags, and select storage providers without touching templates.

**Alternatives considered**:
- Fork the chart under `tests/e2e/helm/` — rejected: drift risk, violates Reminder 26.
- Kustomize overlay — rejected: the platform chart is Helm-native; introducing Kustomize adds a second templating engine.
- Separate "lite" chart — rejected: double-maintenance burden.

---

### D-003: Use asyncpg for DB assertion fixtures — not SQLAlchemy

**Decision**: The `db` fixture in `tests/e2e/fixtures/db_session.py` uses `asyncpg.connect()` directly. Tests write raw SQL for assertion-only queries (`SELECT COUNT(*) FROM registry_agent_profiles WHERE namespace = $1`). SQLAlchemy models are not imported into the harness.

**Rationale**: The harness needs to read across bounded-context table boundaries for end-to-end state verification. Importing SQLAlchemy models from the monolith into `tests/e2e/` would (a) create an unwanted coupling from the test repo into the application code, (b) drag the entire async engine initialization (slow for tests that only need one query), (c) force version sync of SQLAlchemy between two locations. Raw SQL via asyncpg is faster, zero-coupling, and appropriate for read-only assertions.

**Alternatives considered**:
- Reuse `apps/control-plane/src/platform/common/database.py` — rejected: imports the whole platform package, slow and entangled.
- Use HTTP API for every assertion — rejected: some state (e.g., Kafka consumer offsets, internal tables not exposed via API) cannot be read via the public API.

---

### D-004: The harness lives at repository-root `tests/e2e/`; rename existing `apps/control-plane/tests/e2e/` to `tests/integration/`

**Decision**: There are currently two "tests/e2e" directories in the project: (a) per-context Python integration suites under `apps/control-plane/tests/e2e/`, and (b) this feature's new harness at repo-root `tests/e2e/`. The existing directory is a misnomer — those tests are integration-level (docker-compose + in-process FastAPI) not true E2E. This feature renames `apps/control-plane/tests/e2e/` → `apps/control-plane/tests/integration/`. The repo-root `tests/e2e/` becomes the single source of truth for "E2E".

**Rationale**: Reduces cognitive load (one name, one meaning); makes the distinction between integration and E2E crisp in CI output and coverage reports. The rename is mechanical — no test logic changes, only file paths.

**Alternatives considered**:
- Keep both directories with distinct names like `apps/control-plane/tests/integration_docker/` vs `tests/e2e/kind/` — rejected: too verbose.
- Move the existing tests into this new tree — rejected: wrong level of coverage; those suites exercise single-process FastAPI without kind.

**Migration plan**: Single PR renames directory; updates `pyproject.toml` test paths; updates CI matrix. No test logic changes.

---

### D-005: Mock LLM provider as an additional `BaseProvider` implementation

**Decision**: `common/llm/mock_provider.py` implements the existing `BaseProvider` interface alongside real providers (OpenAI, Anthropic, Google). The `common/llm/router.py` selects `MockLLMProvider` when `settings.feature_e2e_mode` is true AND `settings.mock_llm_enabled` is true. The provider owns a per-process response queue (FIFO) + a per-prompt-template default-response dictionary for fallback.

**Rationale**: Follows the existing provider pattern; no interface change. Keeps the real providers untouched — the router flip is the only new decision point. Per-prompt-template fallbacks (e.g., `"agent_response" → "OK"`, `"judge_verdict" → '{"verdict": "allow"}'`) ensure tests never silently hang on an empty queue.

**Queue distribution across pods**: Multiple control-plane pods might route LLM calls. Each pod maintains its own queue. Tests set responses via `POST /api/v1/_e2e/mock-llm/set-response` which broadcasts to all pods (via Redis pub/sub — existing infrastructure). This keeps ordering deterministic per prompt template but does not guarantee global FIFO across pods (which is fine: tests assert on prompt-template match, not global order).

**Alternatives considered**:
- Wrap real providers with a wrapper that returns mock responses — rejected: still makes real network calls during init/warmup.
- External mock LLM container (e.g., `mockllm`) — rejected: more infra, more places for drift.

---

### D-006: Dev-only endpoints require BOTH the feature flag AND an admin bearer token

**Decision**: Every `/api/v1/_e2e/*` endpoint has two independent guards: (a) `router_e2e` is only mounted when `settings.feature_e2e_mode=True`; if false, FastAPI never registers the path and it returns 404; (b) each endpoint has a `Depends(require_admin_or_e2e_scope)` dependency that checks the caller's token for either admin role or an explicit `e2e` scope. Defense in depth.

**Rationale**: FR-022 mandates 404 in production — this is satisfied by (a). But even in an E2E deployment, anonymous or low-privilege callers must not be able to wipe data or kill pods — satisfied by (b). Two independent controls guard against the case where the flag is accidentally set in prod.

**Alternatives considered**:
- Rely only on the flag — rejected: single point of failure.
- Rely only on auth — rejected: FR-022 mandates 404, not 401/403.

---

### D-007: Chaos injection uses Kubernetes API via in-cluster ServiceAccount

**Decision**: The `testing/service_e2e.py` module uses the `kubernetes` Python client with in-cluster config. A dedicated ServiceAccount `e2e-chaos-sa` is created by the Helm chart (templated only when `features.e2eMode: true`) with a minimal Role: `delete pods` + `create/delete networkpolicies` scoped to `platform-execution` and `platform-data` namespaces only. The SA is forbidden from touching `kube-system`, `platform-control`, or any other namespace.

**Rationale**: A real Kubernetes API call is the most faithful chaos injection — it exercises the same scheduler paths a real incident would. Namespace-scoped RBAC guards against accidental blast radius. The SA exists only when the feature flag is on (templated).

**Alternatives considered**:
- Exec into pods to kill processes (without K8s API) — rejected: doesn't trigger the scheduler's Pod lifecycle events that the platform actually handles.
- Use `chaos-mesh` operator — rejected: adds a new operator dependency for a feature that needs only `delete pod` + `create networkpolicy`.

---

### D-008: GitHub Actions `ubuntu-latest-8-cores` + `helm/kind-action@v1`; concurrency group cancels stale runs

**Decision**: `.github/workflows/e2e.yml` runs on PR + nightly cron (`0 3 * * *`). Uses `ubuntu-latest-8-cores` (16 GB RAM, 8 vCPU). Uses `helm/kind-action@v1` which handles kind install + cluster creation + teardown. Concurrency group `e2e-${{ github.head_ref || github.run_id }}` with `cancel-in-progress: true` ensures in-flight runs on the same PR cancel when a new commit lands.

**Rationale**: `ubuntu-latest-8-cores` is the reference runner (matches SC-006's 45 min budget). `helm/kind-action` is Kubernetes SIG's official action — well-maintained, configurable. Concurrency groups save CI minutes (FR-028).

**Nightly failure handling**: After 3 consecutive nightly failures, the workflow auto-creates a GitHub issue in the platform repo with the artifact bundle attached. This avoids issue spam while ensuring sustained failures get attention.

**Alternatives considered**:
- Self-hosted runners — rejected: ops burden, not worth it for this scope.
- CircleCI/BuildKite — rejected: project standardizes on GitHub Actions.

---

### D-009: Reports via pytest-html + JUnit XML; state dump on failure

**Decision**: pytest runs with `--junitxml=reports/junit.xml --html=reports/report.html --self-contained-html`. On any test failure, `capture-state.sh` runs as a post-step and writes `reports/state-dump.txt` containing: `kubectl get pods -A -o wide`, `kubectl get events -A --sort-by='.lastTimestamp'`, `helm status amp -n platform`, `kubectl logs -l app.kubernetes.io/part-of=amp --tail=100 --all-containers=true`. All four artifacts (`junit.xml`, `report.html`, `state-dump.txt`, and the per-pod log directory) are uploaded as one GitHub Actions artifact bundle.

**Rationale**: JUnit XML for CI integration (PR status checks); HTML for human reading; state dump for post-failure triage without cluster access. Standard pytest tooling — no custom reporting layer.

**Alternatives considered**:
- Allure reports — rejected: extra dependency; HTML report is sufficient.
- Custom JSON schema — rejected: JUnit XML is the PR-check standard.

---

### D-010: Multi-cluster support via `CLUSTER_NAME` + `PORT_*` env vars

**Decision**: The Makefile's `CLUSTER_NAME` variable (default `amp-e2e`) is substituted into kind-config.yaml and helm release name. `PORT_UI`/`PORT_API`/`PORT_WS` (defaults 8080/8081/8082) are substituted into kind-config's port mappings. Starting a second cluster: `make e2e-up CLUSTER_NAME=amp-e2e-b PORT_UI=9080 PORT_API=9081 PORT_WS=9082`.

**Rationale**: SC-009 requires parallel clusters on the same host. Per-cluster Docker network isolation is handled by kind automatically; only the host port mappings need to be unique. Templating via environment variables is simple and well-supported by kind (`${VAR}` interpolation).

**Alternatives considered**:
- Dynamic port allocation — rejected: non-deterministic, harder to document.
- Different host IP per cluster — rejected: macOS doesn't support 127.0.0.2 routing out of the box.

---

### D-011: Idempotent seeders via upsert; `--reset` wipes only E2E-scoped rows

**Decision**: Seeders use `INSERT … ON CONFLICT (unique_key) DO NOTHING` (PostgreSQL). Every seeded entity has a deterministic unique key (e.g., user.email = `admin@e2e.test`, agent FQN = `default:seeded-executor`). Rerunning `python -m seeders.base --all` is a no-op if all rows already exist. `--reset` uses a namespace prefix filter (`WHERE name LIKE 'test-%'` or similar) to wipe only E2E rows — never affects non-E2E data if the cluster is shared.

**Rationale**: Idempotency is the default in modern platforms; reset scoping prevents the "reset wiped my real data" foot-gun if someone accidentally points a seeder at a real workspace.

**Alternatives considered**:
- Full database truncate — rejected: dangerous outside E2E contexts.
- Per-test isolation via transaction rollback — rejected: doesn't work for tests that trigger async Kafka events.

---

### D-012: Performance thresholds in a single module; measurements as pytest-reported JSON

**Decision**: `tests/e2e/performance/thresholds.py` holds every performance threshold as a named constant (e.g., `WARM_LAUNCH_MAX_SECONDS = 2.0`). Each performance test captures its measurement via `pytest-benchmark` (optional) or manual `time.perf_counter()` wrappers, asserts against the threshold, and appends to `reports/performance.json` (list of `{test_name, measured, threshold, passed}`).

**Rationale**: Centralizing thresholds allows tuning without touching test logic. JSON output supports future dashboarding without coupling to a specific visualization tool.

**Alternatives considered**:
- `pytest-benchmark` historical comparison — rejected: requires checked-in baseline data that drifts with hardware changes.
- Grafana/Prometheus instrumentation for test runs — rejected: overkill for smoke tests.

---

## Resolved Unknowns

None. All spec [NEEDS CLARIFICATION] markers resolved during spec authoring (zero markers were placed).

## Risks

1. **Developer onboarding friction** — kind + Docker + helm prerequisites may surprise new contributors. Mitigation: `make e2e-check` target pre-flight checks all prerequisites and prints install instructions on failure. README quickstart covers common gotchas (Docker Desktop memory, kind version).
2. **CI cost** — 45-min runs on `ubuntu-latest-8-cores` are ~4x more expensive than standard runners. Mitigation: concurrency cancel-on-new-commit saves minutes on rapid pushes; nightly run is decoupled so transient nightly failures don't block PR merges.
3. **Apps/control-plane rename blast radius** — renaming `apps/control-plane/tests/e2e/` → `tests/integration/` may break developer's open branches. Mitigation: land the rename in its own PR ahead of the harness PR; pin a grace period where both directories work via a pytest discovery rule; remove the old path after two weeks.
4. **Mock LLM coverage gap** — some behaviors (e.g., token-probability-driven branching) are impossible to exercise without a real LLM. Mitigation: explicit non-goal — semantic testing lives in a separate feature; E2E validates platform plumbing.
