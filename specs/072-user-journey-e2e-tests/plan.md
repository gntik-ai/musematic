# Implementation Plan: User Journey E2E Tests

**Branch**: `072-user-journey-e2e-tests` | **Date**: 2026-04-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/072-user-journey-e2e-tests/spec.md`

## Summary

Extend feature 071's E2E harness at `tests/e2e/` with a new `tests/e2e/journeys/` tree of 9 multi-step persona-driven journey tests. Each journey simulates a complete user workflow (admin bootstrap, creator-to-publication, consumer discovery, workspace goal collaboration, trust officer governance, operator incident response, evaluator improvement loop, external A2A+MCP integration, scientific discovery) crossing ≥ 4 bounded contexts with ≥ 15 named assertion points per journey. The harness reuses feature 071's kind cluster, seeders, fixtures (http_client, ws_client, db, kafka_consumer, mock_llm), dev-only `/api/v1/_e2e/*` endpoints, and mock LLM provider — no cluster provisioning, no chart changes, and no duplicate fixtures. New additions: persona-scoped client fixtures (`admin_client`, `creator_client`, `consumer_client`, `operator_client`, `trust_reviewer_client`, `evaluator_client`, `researcher_client`), reusable workflow helpers (`oauth_login`, `register_full_agent`, `certify_agent`, `create_governance_chain`, `wait_for_execution`, `subscribe_ws`), in-cluster mock Google OIDC + GitHub OAuth servers for OAuth-driven journeys, pre-baked fixtures (`workspace_with_agents`, `published_agent`, `workspace_with_goal_ready`, `running_workload`), a pytest narrative-output plugin ensuring every assertion point prints a readable step description, per-journey Makefile targets (`e2e-journeys`, `e2e-j01` … `e2e-j09`), and a CI phase running after bounded-context suites. Journeys are independent, isolated via `j{NN}-test-{uuid}` name prefixes, and support parallel execution.

## Technical Context

**Language/Version**: Python 3.12+ (test harness only); YAML (Helm values additions for mock OAuth servers + CI workflow extensions); Bash (Makefile additions)
**Primary Dependencies**: pytest 8.x (already in feature 071 harness), pytest-asyncio, pytest-html, pytest-timeout, pytest-xdist (NEW — parallel journey execution for SC-005), httpx 0.27+, websockets, aiokafka 0.11+, asyncpg — all reused from feature 071's `tests/e2e/pyproject.toml`. No new runtime dependencies on the control plane.
**Storage**: None directly owned — journey tests assert against existing platform data stores (PostgreSQL, Redis, Kafka, MinIO, ClickHouse) via feature 071's `db`, `kafka_consumer`, and `http_client` fixtures.
**Testing**: pytest is the test framework under test here. The harness itself is validated by CI green runs of all 9 journeys + a meta-test (`test_journey_structure.py`) that enforces FR-003 (≥4 bounded contexts per journey via comment inventory) and FR-004 (≥15 assertion points per journey via AST inspection).
**Target Platform**: Linux developer workstation (≥ 16 GB RAM, feature 071's kind cluster up) for local runs; GitHub Actions `ubuntu-latest-8-cores` runner for CI — same target platform as feature 071.
**Project Type**: Test harness extension. Single new directory `tests/e2e/journeys/` alongside the existing `tests/e2e/suites/`, `tests/e2e/chaos/`, `tests/e2e/performance/` trees. Additive Helm overlay entries for mock OAuth servers, additive Makefile targets, additive CI step. No platform code changes; no migrations; no new Kafka topics.
**Performance Goals**: Full `make e2e-journeys` run ≤ 30 minutes on the reference CI runner (SC-004); combined feature 071 + feature 072 CI workflow ≤ 75 minutes total (spec assumption); 2 concurrent journeys run successfully with isolation (SC-005).
**Constraints**: **Reuse feature 071 without duplication** (FR-025) — no alternate cluster, no fork of fixtures, no redundant seeders. **Idempotent teardown** scoped to `j{NN}-test-%` prefix (FR-009) so any journey can rerun after a prior failure without manual cleanup. **Mock LLM only** (FR-010) — no real LLM API calls. **Journey independence** (FR-007) — pytest run order must produce identical results regardless of order. **Isolation via per-journey name prefix** (FR-008) — concurrent journeys never share workspaces, users, or agents.
**Scale/Scope**: 9 journey test files, 1 `conftest.py`, 1 `helpers/` module with 6 reusable workflow functions, 7 new persona-scoped client fixtures, 4 pre-baked state fixtures, 1 narrative-output pytest plugin, 2 new mock OAuth server deployments (Google OIDC + GitHub OAuth, as additive Helm values + in-cluster stubs), 1 meta-test enforcing FR-003/FR-004. Total: ≈ 180–220 named assertion points across all 9 journeys (average 20 per journey per FR-004 + scenarios).

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | No platform code changes; journey tests live under `tests/e2e/journeys/`, a new subdirectory of the existing test harness |
| **Principle III** — Dedicated data stores | ✅ PASS | Journeys assert against existing data stores via feature 071's fixtures; no new stores introduced |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | Journeys use the `db` fixture (asyncpg SELECT-only user from feature 071) strictly for read-only assertions; writes go through the platform API |
| **Principle V** — Append-only execution journal | ✅ PASS | Operator journey (US6) asserts checkpoint-based resume without mutating the journal — only reads checkpoints and triggers rollback via the API |
| **Principle VI** — Policy is machine-enforced | ✅ PASS | Trust officer journey (US5) exercises the real policy engine, tool gateway, and governance pipeline end-to-end |
| **Principle VII** — Simulation isolation | ✅ PASS | No new simulation paths; existing isolation properties verified where relevant |
| **Principle VIII** — FQN addressing | ✅ PASS | Every journey that registers agents uses FQN (`j{NN}-test-{hash}:agent-name`); creator journey (US2) explicitly asserts FQN registration + resolution |
| **Principle IX** — Zero-trust default visibility | ✅ PASS | Creator journey (US2) explicitly asserts zero-trust visibility enforcement (agent invisible outside configured scope) |
| **Principle X** — GID correlation | ✅ PASS | Workspace goal journey (US4) asserts GID propagation across messages, executions, and at least one downstream analytics/event-log record (FR-014) |
| **Principle XI** — Secrets never in LLM context | ✅ PASS | External integration journey (US8) asserts MCP tool output sanitization; runtime suite from feature 071 already asserts secrets absent from prompts |
| **Principle XIII** — Attention pattern | ✅ PASS | Workspace goal journey (US4) exercises attention request end-to-end via WebSocket assertion |
| **Principle XIV** — A2A external only | ✅ PASS | External integration journey (US8) asserts A2A flows work for external clients; internal paths continue via Kafka + gRPC untouched |
| **Principle XV** — MCP via tool gateway | ✅ PASS | External integration journey (US8) explicitly asserts MCP tool invocation goes through the tool gateway with policy enforcement |
| **Principle XVI** — Generic S3, MinIO optional | ✅ PASS | No storage changes; journey tests use feature 071's existing storage fixtures unchanged |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | Purely additive: new directory, new fixtures, new Makefile targets, new CI step |
| **Brownfield Rule 2** — Alembic migrations | ⚠️ N/A | No schema changes |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Existing feature 071 suites + chaos + performance unaffected; journey tests run separately |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | Journey fixtures extend feature 071 fixtures via pytest composition; workflow helpers follow the factory pattern already established by `AgentFactory`, `PolicyFactory` |
| **Brownfield Rule 5** — Reference existing files | ✅ PASS | Plan cites exact files reused (`tests/e2e/conftest.py`, `tests/e2e/fixtures/*`, `tests/e2e/Makefile`, `.github/workflows/e2e.yml`) |
| **Brownfield Rule 7** — Backward-compatible | ✅ PASS | No production surface changes; additive mock OAuth servers are gated by feature 071's `FEATURE_E2E_MODE` flag |
| **Brownfield Rule 8** — Feature flags | ✅ PASS | Mock OAuth servers mount only when `FEATURE_E2E_MODE=true` (inherits feature 071's guard) |
| **Reminder 25** — No MinIO in app code | ✅ PASS | No application code changes |
| **Reminder 26** — E2E on kind | ✅ PASS | Extends feature 071's kind harness; no docker-compose paths |

No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/072-user-journey-e2e-tests/
├── plan.md                    ✅ This file
├── spec.md                    ✅ Feature specification
├── research.md                ✅ Phase 0 output
├── data-model.md              ✅ Phase 1 output (journey/persona/assertion entities)
├── quickstart.md              ✅ Phase 1 output (9 walkthroughs, one per journey)
├── contracts/
│   ├── fixtures-api.md        ✅ Phase 1 output (persona fixtures + helper surface)
│   ├── oauth-mock.md          ✅ Phase 1 output (mock Google OIDC + GitHub OAuth contract)
│   └── journey-structure.md   ✅ Phase 1 output (meta-test enforcing FR-003 + FR-004)
└── checklists/
    └── requirements.md        ✅ Spec validation (all pass)
```

### Source Code (extending tests/e2e/ at repo root)

```text
# NEW — journeys tree alongside existing suites/chaos/performance
tests/e2e/journeys/
├── __init__.py
├── conftest.py                               # Persona fixtures + pre-baked state fixtures + autouse seeder trigger for journey-scoped entities
├── helpers/
│   ├── __init__.py
│   ├── oauth.py                              # oauth_login(http_client, provider, mock_server) — drives OIDC / OAuth flow against in-cluster mock
│   ├── agents.py                             # register_full_agent(client, ns, name, role_type, **kwargs) + certify_agent(client, agent_id)
│   ├── governance.py                         # create_governance_chain(client, ws_id, observer, judge, enforcer) + attach_contract(client, agent_id, contract)
│   ├── executions.py                         # wait_for_execution(client, execution_id, timeout) + assert_checkpoint_resumed(client, execution_id, checkpoint_id)
│   ├── websockets.py                         # subscribe_ws(ws_client, channel, topic) + assert_event_order(events, expected_types)
│   └── narrative.py                          # @journey_step("description") decorator that records each assertion point for narrative HTML output
├── test_j01_admin_bootstrap.py               # P1 MVP — 15 steps, 6 BCs: auth, OAuth config, workspaces, registry, policies, governance
├── test_j02_creator_to_publication.py        # P1 — 20 steps, 7 BCs: auth (GitHub OAuth), workspaces, registry, trust, marketplace, evaluation, agentops
├── test_j03_consumer_discovery_execution.py  # P1 — 23 steps, 8 BCs: auth (Google OAuth), marketplace, interactions, workflows, execution, reasoning, context-engineering, websocket
├── test_j04_workspace_goal_collaboration.py  # P2 — 21 steps, 5 BCs: auth, workspaces, interactions, websocket, notifications
├── test_j05_trust_governance_pipeline.py     # P2 — 22 steps, 6 BCs: auth, policies, trust, governance, marketplace, audit
├── test_j06_operator_incident_response.py    # P2 — 24 steps, 8 BCs: auth, fleets, execution, workflow, runtime, agentops, governance, analytics
├── test_j07_evaluator_improvement_loop.py    # P3 — 18 steps, 5 BCs: auth, evaluation, agentops, registry, analytics
├── test_j08_external_a2a_mcp.py              # P3 — 19 steps, 5 BCs: a2a, mcp, auth, registry, policies
├── test_j09_scientific_discovery.py          # P3 — 17 steps, 5 BCs: auth, workspaces, discovery, reasoning, knowledge
├── test_journey_structure.py                 # Meta-test enforcing FR-003 + FR-004 via AST inspection of every test_j*.py file
└── plugins/
    └── narrative_report.py                   # pytest plugin capturing @journey_step decorators into junit.xml + report.html narrative rows

# EXTENDED — additive changes to feature 071 harness
tests/e2e/
├── Makefile                                  # MODIFY: add e2e-journeys, e2e-j01 … e2e-j09 targets
├── pyproject.toml                            # MODIFY: add pytest-xdist (parallel execution for SC-005)
└── cluster/
    └── values-e2e.yaml                       # MODIFY: add mockOAuth.google.enabled + mockOAuth.github.enabled Helm toggles and service definitions (additive, inherits FEATURE_E2E_MODE gate)

# EXTENDED — CI
.github/workflows/
└── e2e.yml                                   # MODIFY: add `make e2e-journeys` step after `make e2e-test`, before `make e2e-chaos`; extend artifact path to include journeys-junit.xml + journeys-report.html
```

### Key Architectural Boundaries

- **No platform code changes.** The feature is pure test-harness extension; no changes to `apps/control-plane/`, `apps/satellite-services/`, or `apps/web/`.
- **Mock OAuth servers live under `tests/e2e/cluster/`** as additive Helm values, mounted only when `FEATURE_E2E_MODE=true` — inheriting feature 071's production-safety guard (no separate flag needed; same belt-and-suspenders).
- **Journey helpers vs. suite fixtures.** Feature 071's `fixtures/*` provide low-level clients + factories (http_client, workspace factory, agent factory). This feature's `journeys/helpers/*` are **high-level orchestrations** composing those primitives into reusable multi-step workflows. Different layers, no duplication.
- **Narrative output is a separate pytest plugin.** `plugins/narrative_report.py` wraps `@journey_step("description")` decorators and emits rows into `journeys-report.html` so reviewers can read the test run as a story (SC-010).
- **Meta-test enforces FR-003 + FR-004.** `test_journey_structure.py` parses every `test_j*.py` file via `ast`, extracts the cross-context inventory comment, counts assertion points (via count of `@journey_step` decorators and `assert` statements), and fails the build if any journey falls below the mandated thresholds.

## Complexity Tracking

No constitution violations.

**Highest-risk areas**:

1. **Mock OAuth server determinism under parallel journeys.** Google OIDC + GitHub OAuth mock servers must handle concurrent callbacks from 3+ journeys (J01 admin, J02 creator, J03 consumer) running in parallel under pytest-xdist. Mitigation: keep state keyed by a per-request correlation ID threaded from the journey test into the OAuth client (`state` parameter). Each journey seeds its own correlation. No shared mutable state in the mock server.
2. **Parallel journey isolation.** SC-005 requires 2 journeys to run concurrently with non-overlapping isolation scopes. Risk: a journey accidentally creates an entity without the `j{NN}-test-` prefix, polluting another journey. Mitigation: every helper (`register_full_agent`, `create_workspace`, `certify_agent`) takes a `journey_id` parameter as its first arg and prefixes every resource name; a pre-commit hook + meta-test (`test_journey_structure.py`) fails the build if any journey creates an un-prefixed resource.
3. **Narrative output readability for reviewers.** SC-010 is qualitative ("a reviewer unfamiliar with the codebase can read the report"). Mitigation: adopt `@journey_step("human sentence")` decorator convention with code-review gate — every journey step gets a decorator describing the action in plain language; the plugin emits those sentences into the HTML report as an ordered list.
4. **Journey runtime exceeding 30-minute budget.** 9 journeys × average 3 minutes each = 27 minutes sequential. Mitigation: run journeys in parallel via pytest-xdist (3-way) → wall clock ≈ 10 minutes. Reserve 20 minutes headroom within the 30-minute SC-004 target. Per-journey timeout enforcement via `@pytest.mark.timeout(180)` (3 minutes default, 600 for J06 operator and J07 evaluator which include 10-case evaluation).
5. **Idempotent teardown on failed journeys.** Mid-flow failure may leave partial state: a workspace created but agents not deleted. Mitigation: every helper that creates a resource registers it with a pytest `request.addfinalizer` hook at creation time (not at end-of-test), so even if the journey raises mid-flow, teardown runs. Backed by `j{NN}-test-` prefix scan as safety net via `make e2e-reset`.
6. **Pre-baked fixture drift as feature 071 evolves.** `workspace_with_agents`, `published_agent`, `workspace_with_goal_ready`, `running_workload` fixtures are complex multi-step seeders. If feature 071's seeders change signatures, these break. Mitigation: pre-baked fixtures call feature 071's seeder functions directly (not duplicate them); any signature change is caught by the meta-test.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md)

Key decisions:

- **D-001**: Extend feature 071's harness via a new `tests/e2e/journeys/` directory parallel to `tests/e2e/suites/`. Journeys import feature 071's fixtures directly; no fork, no duplicate seeders. Alternative rejected: parallel feature-071-clone tree (violates FR-025 and Brownfield Rule 1).
- **D-002**: Use pytest-xdist for parallel journey execution (SC-005). Proven, widely-used plugin; integrates cleanly with pytest-asyncio; no additional orchestration layer required. Alternative rejected: pytest sessions per journey (heavier, slower setup).
- **D-003**: Add `@journey_step("description")` decorator + a lightweight `narrative_report.py` pytest plugin emitting narrative rows into `journeys-report.html`. Alternative rejected: Behave/Gherkin (introduces a second testing framework; violates consistency with feature 071's pytest conventions).
- **D-004**: Ship mock Google OIDC + GitHub OAuth servers as additive Helm overlays mounted only when `FEATURE_E2E_MODE=true`. Same flag gate as feature 071's dev-only endpoints — no second feature flag. Alternative rejected: start mocks as local Docker containers on the host (breaks kind isolation; journeys would only work on host OS matching dev machine).
- **D-005**: Per-journey isolation enforced by helper functions prefixing every entity name with `j{NN}-test-{hash}`. Scope filter passed to feature 071's reset endpoint inherits the prefix. Alternative rejected: per-journey kind cluster (violates SC-005 parallel execution with single cluster; 9 parallel clusters exceed 16 GB laptop budget).
- **D-006**: Pre-baked fixtures call feature 071's seeder Python functions directly (import from `tests/e2e/seeders/`), not via the dev-only `/_e2e/seed` HTTP endpoint. This gives journey tests the same seed fidelity as `make e2e-up` while avoiding a network hop. Alternative rejected: per-journey `_e2e/seed` call (slower; introduces a second code path for baseline setup).
- **D-007**: Meta-test `test_journey_structure.py` parses every journey file via Python's `ast` module, extracts the cross-context inventory (header comment), counts assertion points (union of `@journey_step` decorators + `assert` statements + fixture-level state checks), and fails the build if any journey is below FR-003 (≥ 4 BCs) or FR-004 (≥ 15 assertions). Alternative rejected: manual review checklist (not enforceable in CI).
- **D-008**: Per-journey pytest timeouts: J01–J05 at 180s (3 min), J06 + J07 at 600s (10 min — include 10-case evaluation / checkpoint recovery), J08 + J09 at 300s. Global `--timeout 900` ceiling. Overrides via `@pytest.mark.timeout(N)` per journey. Alternative rejected: no per-journey timeout (first stuck journey hangs CI for 45 min).
- **D-009**: CI extension to `.github/workflows/e2e.yml` adds one new step `make e2e-journeys` after `make e2e-test` (bounded-context suites) and before `make e2e-chaos`. Journeys run on the same kind cluster already provisioned by `make e2e-up`. Parallel execution is via pytest-xdist inside the single step. Alternative rejected: dedicated CI job (wastes 10 minutes on cluster provisioning redundancy).
- **D-010**: Narrative reports go to `tests/e2e/reports/journeys-junit.xml` + `tests/e2e/reports/journeys-report.html` — separate files from bounded-context reports so reviewers can triage by failure type. Both uploaded as part of feature 071's `e2e-reports-{run_id}` artifact bundle (no separate artifact).

---

## Phase 1: Design & Contracts

**Status**: ✅ Complete

- [data-model.md](data-model.md) — Journey / Persona / AssertionPoint / JourneyMarker / PrebakedFixture / IsolationScope entity shapes; pre-baked fixture specifications for `workspace_with_agents`, `published_agent`, `workspace_with_goal_ready`, `running_workload`; OAuth mock server seed state.
- [contracts/fixtures-api.md](contracts/fixtures-api.md) — Full pytest fixture surface for journeys: 7 persona-scoped client fixtures + 4 pre-baked state fixtures + signatures for 6 workflow helpers (oauth_login, register_full_agent, certify_agent, create_governance_chain, wait_for_execution, subscribe_ws).
- [contracts/oauth-mock.md](contracts/oauth-mock.md) — HTTP contracts for mock Google OIDC + GitHub OAuth servers: endpoints, request/response shapes, correlation-ID-keyed state, Helm values to enable them, 404-when-flag-off inheritance from feature 071.
- [contracts/journey-structure.md](contracts/journey-structure.md) — Meta-test `test_journey_structure.py`: AST inspection rules, cross-context inventory comment format, assertion-point counting algorithm, FR-003 + FR-004 enforcement thresholds.
- [quickstart.md](quickstart.md) — Nine acceptance-scenario walkthroughs (Q1–Q9), one per journey, with exact commands, expected output, and narrative report excerpts.
