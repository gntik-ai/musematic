# Phase 0 Research: User Journey E2E Tests

**Feature**: 072-user-journey-e2e-tests
**Date**: 2026-04-21

All 10 research decisions consolidated below. No unresolved `NEEDS CLARIFICATION` markers remain.

---

## D-001: Extend feature 071's harness via new `tests/e2e/journeys/` directory

**Decision**: Journey tests live at `tests/e2e/journeys/` alongside the existing `tests/e2e/suites/`, `tests/e2e/chaos/`, `tests/e2e/performance/` trees from feature 071. Journeys import feature 071's fixtures via the shared `tests/e2e/conftest.py` (which is session-visible across all subdirectories). No fork of the cluster, Helm overlay, seeders, or base fixtures.

**Rationale**: FR-025 explicitly mandates reuse of feature 071 without duplication. pytest's session-scoped `conftest.py` at `tests/e2e/` is automatically discoverable from any nested directory, so journey tests can request `http_client`, `ws_client`, `db`, `kafka_consumer`, and `mock_llm` fixtures by simply naming them. Brownfield Rule 1 (never rewrite) reinforces the additive-only approach.

**Alternatives considered**:
- *Parallel tree at `tests/journeys/`*: rejected — would duplicate cluster/seeder/fixture wiring. Violates FR-025 and Brownfield Rule 1.
- *Journeys inside `tests/e2e/suites/` with a `journey_` prefix*: rejected — journey tests are organizationally distinct (persona-driven, multi-context) from bounded-context suites; mixing them confuses selective execution by marker and breaks the reporting separation required by D-010.

---

## D-002: Use pytest-xdist for parallel journey execution

**Decision**: Add `pytest-xdist` to `tests/e2e/pyproject.toml`. The Makefile target `e2e-journeys` invokes `pytest journeys/ -n 3 --dist=loadfile` to run up to 3 journeys concurrently on the same kind cluster. Per-journey isolation is enforced via the `j{NN}-test-{hash}` name prefix (D-005).

**Rationale**: SC-005 requires two concurrent journeys to run on the same cluster without interference. pytest-xdist is the de facto standard for parallel pytest runs, is fully compatible with pytest-asyncio, and requires zero test-side changes when tests are already independent. `--dist=loadfile` distributes at the file level (one journey per worker), avoiding intra-journey parallelism (which would violate journey sequential state).

**Alternatives considered**:
- *pytest sessions per journey*: rejected — each session pays full fixture teardown/setup cost (≥ 30 s per journey for authenticated clients + pre-baked fixtures); 9 journeys × 30 s = 4.5 minutes of pure overhead.
- *Manual pytest invocations in parallel via Makefile `&`*: rejected — harder to aggregate reports; race conditions around the shared `reports/` directory.
- *Asyncio.gather inside a single pytest session*: rejected — defeats pytest's per-test isolation guarantees; mixing `asyncio.gather` with pytest-asyncio fixtures is a known source of flaky teardown.

---

## D-003: `@journey_step("description")` decorator + pytest plugin for narrative reports

**Decision**: Every assertion point in a journey is wrapped by `@journey_step("human-readable sentence")` (a context manager or function decorator). A lightweight pytest plugin (`plugins/narrative_report.py`) captures the decorator calls and emits them into `journeys-report.html` as an ordered, per-journey list of verified actions. On failure, the plugin prints the narrative up to and including the failing step.

**Rationale**: SC-010 requires reviewers unfamiliar with the codebase to read the report as a story. `-v` pytest verbose output prints test function names only; it does not express the per-step narrative within a single test function. A lightweight decorator + plugin keeps the tests readable (inline description where the action happens) and emits a rich HTML report without adopting a second framework.

**Alternatives considered**:
- *Behave / Gherkin*: rejected — introduces a second testing framework alongside pytest; violates consistency with feature 071.
- *pytest-bdd*: rejected — imposes separate `.feature` files which reviewers would have to read alongside the `.py` file; adds cognitive cost for test authors.
- *Docstring-only narrative*: rejected — docstrings can't be captured per-step; only per-function.
- *Extended logging*: rejected — logging is per-line, not per-step; no ordered narrative structure.

---

## D-004: Mock Google OIDC + GitHub OAuth servers as additive Helm overlays

**Decision**: Add two in-cluster deployments (`mock-google-oidc` + `mock-github-oauth`) via additive Helm overlay entries in `tests/e2e/cluster/values-e2e.yaml`. Both mount only when `FEATURE_E2E_MODE=true`, inheriting feature 071's production-safety guard. Each mock server is a minimal FastAPI or Flask app exposing the OIDC/OAuth endpoints needed for the admin (US1), creator (US2), and consumer (US3) journey flows.

**Rationale**: Journeys 1, 2, 3 require OAuth login; without in-cluster mocks, journeys would either (a) require external network calls to Google/GitHub (non-deterministic, slow, requires secrets) or (b) only work on specific developer machines. In-cluster mocks are deterministic, keyed by correlation ID (D-004-sub), and maintain feature 071's Reminder 26 principle (same Helm charts as production — just additional optional values).

**Alternatives considered**:
- *Host-side Docker containers*: rejected — breaks kind isolation, can't be reached from pods without host.docker.internal hacks that are OS-dependent.
- *External OAuth playground services*: rejected — requires network access and secrets in CI; non-deterministic.
- *Pure python stub using `unittest.mock`*: rejected — OAuth flows require redirects and multi-request state; mocking inside the test process breaks the integration property the journey is meant to validate.
- *Reuse of existing OAuth2 test libraries (oauth2-mock-server)*: rejected — adds a third-party dependency for a small, well-scoped need; writing ~200 lines of FastAPI is simpler and lets us shape the endpoints exactly to the platform's OAuth adapter.

**OAuth correlation state design**: Each mock server keys state by the OAuth `state` parameter. The journey test generates a per-call UUID state. Mock server retains state ≤ 5 minutes (in-memory TTL). Parallel journeys using the same mock server never share state because every call uses a unique state.

---

## D-005: Per-journey isolation via `j{NN}-test-{hash}` name prefix

**Decision**: Every resource created by a journey (workspace, user, agent, namespace, policy, fleet, goal) uses a name prefix `j{NN}-test-{uuid4().hex[:8]}-{resource_type}-{local_name}` where `NN` is the journey number. Helper functions (`register_full_agent`, `create_workspace`, etc.) enforce this prefix via a mandatory first-argument `journey_id: str`. Feature 071's `/api/v1/_e2e/reset` endpoint already scopes to `test-%` prefix, which matches this feature's prefix (`j01-test-`, `j02-test-`, etc.).

**Rationale**: SC-005 requires parallel journey execution. The only way two journeys can coexist on a single cluster is via resource-name isolation. Per-journey UUIDs within the prefix ensure even re-runs of the same journey don't collide.

**Alternatives considered**:
- *Per-journey kind cluster*: rejected — 16 GB laptop and CI runner can't host 2+ full platform clusters simultaneously.
- *Per-journey PostgreSQL schema*: rejected — would require changing the platform's connection logic; violates Brownfield Rule 1.
- *Global test workspace shared across journeys*: rejected — violates FR-007 (journey independence).

**Safety net**: `make e2e-reset` also sweeps all rows with `name LIKE 'j%-test-%'` in case a journey crashes without teardown.

---

## D-006: Pre-baked fixtures import feature 071 seeder functions directly

**Decision**: Pre-baked fixtures (`workspace_with_agents`, `published_agent`, `workspace_with_goal_ready`, `running_workload`) import feature 071's seeder functions from `tests/e2e/seeders/` and call them with a per-journey scope prefix. They do NOT call feature 071's dev-only `/_e2e/seed` HTTP endpoint — that endpoint seeds the **shared baseline** entities, not per-journey ones.

**Rationale**: Shared baseline (from `/_e2e/seed`) is loaded once per pytest session by feature 071's `ensure_seeded` autouse fixture. Per-journey state is per-test and uses different names. Calling the HTTP endpoint would duplicate the baseline, not create per-journey resources. Direct Python imports avoid a network hop and give journeys the same seeding fidelity as the baseline.

**Alternatives considered**:
- *Add new `/_e2e/seed-journey` endpoint*: rejected — adds surface area to the platform for a need fully satisfiable in the harness.
- *Duplicate seeder logic inside journey fixtures*: rejected — violates FR-025 (no duplication).

---

## D-007: Meta-test `test_journey_structure.py` enforces FR-003 + FR-004

**Decision**: A meta-test parses every `tests/e2e/journeys/test_j*.py` file using Python's `ast` module, extracts a mandatory header comment block named `# Cross-context inventory:` that lists the bounded contexts the journey exercises, counts the union of `@journey_step` decorators + `assert` statements + AST-visible state checks (fixture usage patterns), and fails if any journey has:
- fewer than 4 listed bounded contexts (FR-003)
- fewer than 15 assertion points (FR-004)

The meta-test runs as part of `make e2e-journeys` and in CI.

**Rationale**: FR-003 and FR-004 are numeric thresholds that a human reviewer cannot reliably verify; automation is the only scalable enforcement. AST inspection is brittle to aggressive refactoring but covers 90% of patterns journey tests will actually use. The `# Cross-context inventory:` convention makes the count machine-parseable.

**Alternatives considered**:
- *Pre-commit hook*: rejected — journey tests evolve after the initial commit; per-commit enforcement misses later drift.
- *Manual review checklist*: rejected — SC-003 requires "verifiable" coverage; manual process is not verifiable.
- *Runtime counter via `@journey_step` only*: rejected — some assertions may be `assert` statements without decorator wrap; better to count both.

**Comment format**:
```python
# Cross-context inventory:
# - auth
# - workspaces
# - registry
# - policies
# - trust
# - governance
```

---

## D-008: Per-journey pytest timeouts with documented thresholds

**Decision**: Each journey declares an explicit `@pytest.mark.timeout(N)` at the module or function level:
- J01 (admin bootstrap): 180 s (3 min)
- J02 (creator to publication): 300 s (5 min — includes package upload + certification + eval run)
- J03 (consumer): 300 s (5 min — includes WebSocket streaming + execution completion)
- J04 (workspace goal): 300 s (5 min — multi-agent coordination)
- J05 (trust governance): 300 s (5 min — governance pipeline + contract breach + third-party cert)
- J06 (operator): 600 s (10 min — checkpoint recovery + re-prioritization + canary)
- J07 (evaluator): 600 s (10 min — 10-case evaluation + calibration + re-eval)
- J08 (external A2A/MCP): 300 s (5 min)
- J09 (scientific discovery): 300 s (5 min — generation + debate rounds + tournament)

Global ceiling: `pytest --timeout=900` (15 min) as a safety net.

**Rationale**: Without per-journey timeouts, a single hung journey consumes the full 30-minute SC-004 budget. Per-journey timeouts convert hangs into immediate failures with a clear cause.

**Alternatives considered**:
- *Single global timeout*: rejected — would either be too short for J06/J07 or too long for J01; no single value fits all journeys.
- *No timeout*: rejected — violates SC-004 (30-minute CI budget).

---

## D-009: CI extension via one new step after bounded-context suites

**Decision**: `.github/workflows/e2e.yml` gets one new step `- name: Run E2E journey tests` after `make e2e-test` and before `make e2e-chaos`. The step invokes `make e2e-journeys`, which runs pytest-xdist with 3 workers against the already-provisioned kind cluster. Separate JUnit XML + HTML reports (`journeys-junit.xml`, `journeys-report.html`) are written to the same `tests/e2e/reports/` directory feature 071 uploads as a single artifact.

**Rationale**: Journeys run on the same cluster as bounded-context suites (D-001). Reusing the provisioned cluster saves the 10-minute cost of a second cluster creation. Running journeys after bounded-context suites (but before chaos) means a baseline regression is caught by the faster suites first. Chaos tests after journeys ensures chaos doesn't poison journey state (chaos fixtures revert their perturbations, but journey-scoped resources added by chaos could interact with journeys if order were reversed).

**Alternatives considered**:
- *Separate CI job*: rejected — wastes 10 minutes on redundant cluster provisioning; CI budget is 45 minutes for feature 071 alone.
- *Run journeys before bounded-context suites*: rejected — journey failures would hide bounded-context bugs; bounded-context suites are faster and catch regressions sooner.
- *Run journeys only nightly (not per-PR)*: rejected — violates SC-005 CI continuity; developers would learn of journey breaks hours after causing them.

---

## D-010: Separate journey reports alongside bounded-context reports

**Decision**: Write `journeys-junit.xml` and `journeys-report.html` to `tests/e2e/reports/` (same directory as feature 071's `junit.xml` and `report.html`). Both are included in feature 071's artifact bundle (`e2e-reports-{run_id}`) — no new artifact added. The narrative HTML report (D-003) is a distinct file so reviewers can open it directly when a journey fails.

**Rationale**: Reviewers triage by failure type: a bounded-context test failure points to a single context bug; a journey failure points to a cross-context integration bug. Keeping reports separate but colocated in the artifact lets reviewers quickly identify which file to open. Reusing feature 071's artifact upload step keeps CI config simple.

**Alternatives considered**:
- *Single combined report*: rejected — too much noise; hard to find journey failures among 50+ bounded-context test results.
- *Separate artifact for journey reports*: rejected — doubles the download overhead for reviewers; complicates feature 071's artifact naming convention.
