# Tasks: User Journey E2E Tests

**Input**: Design documents from `/specs/072-user-journey-e2e-tests/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label [US1]–[US9]

---

## Phase 1: Setup

**Purpose**: Extend feature 071's E2E harness with pytest-xdist and create the `tests/e2e/journeys/` directory skeleton.

- [X] T001 Add `pytest-xdist` to `tests/e2e/pyproject.toml` under `[project.optional-dependencies] e2e` to enable `--dist=loadfile` parallel journey execution per research.md D-002
- [X] T002 [P] Create `tests/e2e/journeys/` directory skeleton: `__init__.py`, `helpers/__init__.py`, `plugins/__init__.py`, and `fixtures/` subdirectory; add a minimal `agent_package.tar.gz` stub to `tests/e2e/journeys/fixtures/` for use by the `published_agent` pre-baked fixture per data-model.md §3

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared helper library, persona fixtures, pre-baked state fixtures, narrative plugin, meta-test, mock OAuth Helm overlay, Makefile targets, and CI extension. All Phase 3–5 journey files depend on this phase.

**⚠️ CRITICAL**: No journey test file (US1–US9) can be implemented until this phase is complete.

### 2A — Helper modules (parallel with each other; depend on T001–T002)

- [X] T003 [P] Implement `journey_step(description: str)` context manager in `tests/e2e/journeys/helpers/narrative.py`: records `JourneyStepRecord` (journey_id, test_nodeid, step_index, description, started_at, duration_ms, status, error), catches exceptions to attribute failures to the specific step, and stores records on a thread-local stack for the narrative plugin to harvest; shape per data-model.md §4
- [X] T004 [P] Implement `oauth_login(client, provider, mock_server, login)` in `tests/e2e/journeys/helpers/oauth.py`: drives the full OIDC/OAuth callback flow (GET /authorize → redirect → GET /callback?code=…) against the in-cluster mock server; return the authenticated client with session token set; per contracts/oauth-mock.md
- [X] T005 [P] Implement `register_full_agent(client, journey_id, namespace, local_name, role_type, **manifest_kwargs)` and `certify_agent(client, agent_id, reviewer_client, evidence)` in `tests/e2e/journeys/helpers/agents.py`; auto-prefix all names with `j{NN}-test-{hash}-` per data-model.md §5; return shapes per contracts/fixtures-api.md §C.2–C.3
- [X] T006 [P] Implement `create_governance_chain(client, workspace_id, observer_fqn, judge_fqn, enforcer_fqn)` and `attach_contract(client, agent_id, max_response_time_ms, min_accuracy)` in `tests/e2e/journeys/helpers/governance.py`; validate each agent has the required role type before binding; return binding IDs per contracts/fixtures-api.md §C.4, C.7
- [X] T007 [P] Implement `wait_for_execution(client, execution_id, timeout, expected_states)` and `assert_checkpoint_resumed(client, execution_id, checkpoint_id)` in `tests/e2e/journeys/helpers/executions.py`; poll every 1 s until status matches or timeout; raise `AssertionError` with last observed state on timeout; per contracts/fixtures-api.md §C.5
- [X] T008 [P] Implement `subscribe_ws(ws_client, channel, topic)` async context manager and `assert_event_order(events, expected_types)` in `tests/e2e/journeys/helpers/websockets.py`; context manager yields sub with `.received_events` list for post-hoc assertion; assert_event_order verifies causal sequence; per contracts/fixtures-api.md §C.6

### 2B — Narrative plugin (parallel with 2A; depends on T001–T002)

- [X] T009 [P] Create `tests/e2e/journeys/plugins/narrative_report.py` pytest plugin: hook `pytest_runtest_logreport` to harvest `JourneyStepRecord` items from the narrative helper; emit each as a nested `<testcase>` in `reports/journeys-junit.xml` and as an ordered `<li>` row in `reports/journeys-report.html`; stop narrative at the failing step and highlight it; per data-model.md §4 and research.md D-003, D-010

### 2C — Conftest fixtures (sequential; depends on T003–T009)

- [X] T010 Implement 7 persona client fixtures (`admin_client`, `creator_client`, `consumer_client`, `operator_client`, `trust_reviewer_client`, `evaluator_client`, `researcher_client`) plus `ensure_journey_personas` (session-scoped autouse) and `cleanup_journey_resources` (function-scoped autouse) in `tests/e2e/journeys/conftest.py`; register all 9 journey markers via `pytest_configure`; OAuth-based personas call T004 (`oauth_login`); shapes per contracts/fixtures-api.md §A, §B.5–B.6, §E
- [X] T011 Add `workspace_with_agents` pre-baked fixture to `tests/e2e/journeys/conftest.py`: creates workspace + namespace + 4 agents (executor, observer, judge, enforcer) + default-allow policy + governance chain; registers teardown via `request.addfinalizer` at each creation step; yields shape per data-model.md §3; depends on T005 and T006
- [X] T012 Add `published_agent` pre-baked fixture to `tests/e2e/journeys/conftest.py`: registers agent, uploads `fixtures/agent_package.tar.gz`, attaches policy, certifies (admin self-approves), publishes to marketplace; yields shape per data-model.md §3; depends on T011
- [X] T013 Add `workspace_with_goal_ready` pre-baked fixture to `tests/e2e/journeys/conftest.py`: extends `workspace_with_agents` with 4 subscribed agents (3 relevant + 1 irrelevant by response-decision config) and a goal in READY state; yields shape per data-model.md §3; depends on T011
- [X] T014 Add `running_workload` pre-baked fixture to `tests/e2e/journeys/conftest.py`: seeds 3-agent fleet + 2 long-running executions (mock LLM slow responses) + warm pool fill + 3 queued executions; yields shape per data-model.md §3; depends on T011

### 2D — Meta-test and infrastructure (parallel with 2C; depend on T003–T009)

- [X] T015 [P] Create `tests/e2e/journeys/test_journey_structure.py` meta-test: discover all `test_j[0-9][0-9]_*.py` files via glob; parse `# Cross-context inventory:` comment block and validate context names against registry; count assertion points (union of `@journey_step` invocations + bare `assert` statements outside journey_step blocks); enforce FR-003 (≥4 valid contexts), FR-004 (≥15 assertion points), ≥10 journey_step decorators, naming conventions (`JOURNEY_ID` pattern, `TIMEOUT_SECONDS` range 60–900, required markers), and isolation-scope (helpers pass `journey_id`); print summary table on pass; fail with actionable message on violation; per contracts/journey-structure.md
- [X] T016 [P] Add `mockOAuth.google` and `mockOAuth.github` Helm overlay entries to `tests/e2e/cluster/values-e2e.yaml`: service definitions, resource limits, seedUsers (j-admin/j-creator/j-consumer for Google; j-admin-gh/j-creator-gh for GitHub), platform auth env var overrides pointing to in-cluster URLs; gated by `features.e2eMode: true`; per contracts/oauth-mock.md §Helm overlay
- [X] T017 [P] Add `e2e-journeys` and `e2e-j01` through `e2e-j09` Makefile targets to `tests/e2e/Makefile`: `e2e-journeys` runs `pytest journeys/ -n 3 --dist=loadfile -v -m journey --junitxml=reports/journeys-junit.xml --html=reports/journeys-report.html`; each `e2e-j{NN}` runs a single journey by marker (`-m j{NN}_{persona}`); per contracts/fixtures-api.md §F
- [X] T018 [P] Add `make e2e-journeys` step to `.github/workflows/e2e.yml` after the `make e2e-test` step and before `make e2e-chaos`; extend the existing artifact upload path to include `tests/e2e/reports/journeys-junit.xml` and `tests/e2e/reports/journeys-report.html`; per research.md D-009, D-010

**Checkpoint**: Foundation complete — all 9 journey test files can now be implemented in parallel.

---

## Phase 3: P1 Core Journeys (User Stories 1–3) 🎯 MVP

**Goal**: Three highest-priority journeys covering admin bootstrap (US1), creator-to-publication (US2), and consumer discovery and execution (US3).

**Independent Test**: Each runs independently with `make e2e-j01`, `make e2e-j02`, or `make e2e-j03` after `make e2e-up`.

- [X] T019 [P] [US1] Implement `tests/e2e/journeys/test_j01_admin_bootstrap.py` (JOURNEY_ID="j01", TIMEOUT_SECONDS=180, 6 BCs: auth, accounts, workspaces, policies, trust, governance): 15+ `journey_step` blocks covering bootstrap login → forced password change assertion (write succeeds after change) → TOTP MFA enrollment (generate + confirm code) → Google + GitHub OAuth provider configuration → `GET /api/v1/auth/oauth/providers` (assert 2 enabled) → workspace creation with namespaces + quotas + visibility grants → governance chain assignment via `create_governance_chain` (observer→judge→enforcer) → default alert settings → workspace invite flow (assert invited user joins with correct role) → final state assertion (workspace detail has namespaces, visibility, quotas, governance chain, alerts); markers: `@pytest.mark.journey`, `@pytest.mark.j01_admin`, `@pytest.mark.timeout(180)`
- [X] T020 [P] [US2] Implement `tests/e2e/journeys/test_j02_creator_to_publication.py` (JOURNEY_ID="j02", TIMEOUT_SECONDS=300, 7 BCs: auth, workspaces, registry, trust, marketplace, evaluation, agentops): 20+ `journey_step` blocks covering GitHub OAuth login via `oauth_login` → RBAC access check → FQN registration with NL fields (purpose ≥50 chars, approach, role_type, visibility patterns) → FQN resolution assertion → zero-trust visibility check (agent invisible outside scope) → package upload + immutable revision with digest → policy attachment → certification request + trust reviewer approval → marketplace listing with trust badge → intent-based search assertion → FQN-pattern search assertion → evaluation history on profile; markers: `@pytest.mark.journey`, `@pytest.mark.j02_creator`, `@pytest.mark.timeout(300)`
- [X] T021 [P] [US3] Implement `tests/e2e/journeys/test_j03_consumer_discovery_execution.py` (JOURNEY_ID="j03", TIMEOUT_SECONDS=300, 8 BCs: auth, marketplace, interactions, workflows, execution, reasoning, context-engineering, websocket): 23+ `journey_step` blocks covering Google OAuth first-time login → auto-provisioning assertion (`provisioned_via == "google"`) → marketplace search by intent (ranked results) → agent profile inspection (FQN, purpose, approach, trust badges, quality metrics) → conversation creation + task message → WebSocket subscription via `subscribe_ws` → assert causal event order (`reasoning.trace.step` before `execution.completed`) → reasoning trace + execution timeline inspection → follow-up message (new interaction in same conversation) → alert preference config → second task + alert verification → conversation history (2 completed interactions); markers: `@pytest.mark.journey`, `@pytest.mark.j03_consumer`, `@pytest.mark.timeout(300)`

**Checkpoint**: US1–US3 complete and passing. MVP delivered.

---

## Phase 4: P2 Governance and Operations Journeys (User Stories 4–6)

**Goal**: Three P2 journeys covering workspace goal collaboration (US4), trust governance pipeline (US5), and operator incident response (US6).

**Independent Test**: `make e2e-j04`, `make e2e-j05`, `make e2e-j06`.

- [X] T022 [P] [US4] Implement `tests/e2e/journeys/test_j04_workspace_goal_collaboration.py` (JOURNEY_ID="j04", TIMEOUT_SECONDS=300, 5 BCs: auth, workspaces, interactions, websocket, notifications): 21+ `journey_step` blocks covering login → goal creation from `workspace_with_goal_ready` fixture (assert READY state + GID assigned) → first message (assert WORKING state) → response-decision log inspection (relevant agents "respond", irrelevant agent "pass") → all messages carry same GID assertion → follow-up message steering agent focus → attention request via WebSocket (`interaction.attention` event with urgency + GID) → attention response → goal COMPLETE (assert subsequent message POST rejected) → GID appears in analytics/event-log downstream record; markers: `@pytest.mark.journey`, `@pytest.mark.j04_workspace_goal`, `@pytest.mark.timeout(300)`
- [ ] T023 [P] [US5] Implement `tests/e2e/journeys/test_j05_trust_governance_pipeline.py` (JOURNEY_ID="j05", TIMEOUT_SECONDS=300, 6 BCs: auth, policies, trust, governance, marketplace, audit): 22+ `journey_step` blocks covering trust reviewer login → safety policy creation + workspace attachment → governance chain config via `create_governance_chain` → SafetyPreScreener violation catch assertion (<10ms) → subtle violation through Observer→Judge→Enforcer pipeline → judge VIOLATION verdict with rationale → enforcer blocks + operator notification (WebSocket or notification record) → audit trail inspection (verdicts + enforcement + correlation IDs) → behavioral contract via `attach_contract` (max response time + accuracy) → contract breach enforcement → third-party certification request + approval + marketplace badge → surveillance recertification trigger → agent decommission (invisible in marketplace, historical data retained by direct ID lookup); markers: `@pytest.mark.journey`, `@pytest.mark.j05_trust`, `@pytest.mark.timeout(300)`
- [ ] T024 [P] [US6] Implement `tests/e2e/journeys/test_j06_operator_incident_response.py` (JOURNEY_ID="j06", TIMEOUT_SECONDS=600, 8 BCs: auth, fleets, execution, workflows, runtime, agentops, governance, analytics): 24+ `journey_step` blocks covering operator login → dashboard warm-pool metrics (pool size, available pods, hit rate) → long-running execution creation + checkpoint assertion → runtime pod kill via `POST /api/v1/_e2e/kill-pod` → heartbeat detection + failure surfaced within heartbeat-timeout window → `assert_checkpoint_resumed` (assert execution state from DB, not restarted from scratch) → rollback record in audit trail → execution timeline + reasoning trace inspection → governance VIOLATION verdict inspection (policy + evidence + rationale) → queue re-prioritization (inject urgent execution, assert start-time ordering) → analytics dashboard (performance + token usage + cost) → AgentOps adaptation proposal review + approval → canary deployment trigger + rollback endpoint verification → decommission with historical data preserved; markers: `@pytest.mark.journey`, `@pytest.mark.j06_operator`, `@pytest.mark.timeout(600)`

**Checkpoint**: US4–US6 complete and passing.

---

## Phase 5: P3 Specialist Journeys (User Stories 7–9)

**Goal**: Three P3 journeys covering evaluator improvement loop (US7), external A2A+MCP integration (US8), and scientific discovery (US9).

**Independent Test**: `make e2e-j07`, `make e2e-j08`, `make e2e-j09`.

- [ ] T025 [P] [US7] Implement `tests/e2e/journeys/test_j07_evaluator_improvement_loop.py` (JOURNEY_ID="j07", TIMEOUT_SECONDS=600, 5 BCs: auth, evaluation, agentops, registry, analytics): 18+ `journey_step` blocks covering evaluator login → evaluation suite creation → TrajectoryScorer config (path_efficiency, tool_appropriateness, reasoning_coherence, cost_effectiveness) → LLM-as-Judge config with custom rubric → 10-case suite run → 4-dimensional score persistence assertion per case → calibration (3 cases × 5 runs → score distributions with mean + stddev) → evaluation results view (scores + trajectories + judge rationale) → two-revision comparison (delta + regression flag) → adaptation pipeline trigger → adaptation proposal approval → new revision creation → re-evaluation (targeted dimensions improve by measurable margin); markers: `@pytest.mark.journey`, `@pytest.mark.j07_evaluator`, `@pytest.mark.timeout(600)`
- [ ] T026 [P] [US8] Implement `tests/e2e/journeys/test_j08_external_a2a_mcp.py` (JOURNEY_ID="j08", TIMEOUT_SECONDS=300, 5 BCs: a2a, mcp, auth, registry, policies): 19+ `journey_step` blocks covering platform Agent Card fetch (`/.well-known/agent.json`) + per-agent card by FQN (assert valid JSON with capabilities + auth schemes + skills) → OAuth2 bearer token auth → single-turn A2A task submit + SSE subscribe → assert causal state order (submitted→working→completed) + event payload shapes → multi-turn A2A task with clarification exchange (server requests clarification → client responds → task completes referencing full turn history) → MCP tool discovery via tool manifest endpoint → MCP tool invocation through tool gateway → assert permission + purpose policy checks applied → assert secret-like values redacted in output; markers: `@pytest.mark.journey`, `@pytest.mark.j08_external`, `@pytest.mark.timeout(300)`
- [ ] T027 [P] [US9] Implement `tests/e2e/journeys/test_j09_scientific_discovery.py` (JOURNEY_ID="j09", TIMEOUT_SECONDS=300, 5 BCs: auth, workspaces, discovery, reasoning, knowledge): 17+ `journey_step` blocks covering researcher login → discovery workspace creation + seed data upload → hypothesis generation trigger (assert ≥ configured minimum hypotheses produced) → Chain of Debates trigger on top hypotheses → debate round transcript assertion (position, critique, rebuttal, synthesis persisted as reasoning artifacts) → Elo tournament ranking (every hypothesis has a score) → proximity graph clustering (similar hypotheses grouped) → generation bias toward underrepresented clusters → top-ranked hypothesis evolution (refined variant referencing original) → experiment design trigger → structured experiment plan assertion; markers: `@pytest.mark.journey`, `@pytest.mark.j09_discovery`, `@pytest.mark.timeout(300)`

**Checkpoint**: US7–US9 complete and passing. All 9 journeys implemented.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T028 Create `tests/e2e/tests/test_mock_oauth_disabled_in_production.py`: assert `helm template deploy/helm/platform/ --set features.e2eMode=false` produces zero Deployments named `mock-google-oidc` or `mock-github-oauth`; per contracts/oauth-mock.md production-safety section
- [ ] T029 [P] Run `make e2e-journeys` with `-n 3` parallel workers; verify all 9 journeys pass and meta-test `test_journey_structure.py` reports every journey above FR-003 (≥4 BCs) and FR-004 (≥15 assertion points) thresholds; verify isolation by confirming no cross-journey resource names collide (SC-005)
- [ ] T030 [P] Validate quickstart.md walkthroughs Q1–Q9 by running `make e2e-j{NN}` for each; open `reports/journeys-report.html` and confirm narrative rows are human-readable without codebase context per SC-010

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all journeys**
  - 2A helpers (T003–T008) + 2B plugin (T009): all parallel
  - 2C conftest (T010–T014): strictly sequential (same file, each builds on previous); depends on 2A + 2B
  - 2D infra (T015–T018): parallel with each other; parallel with 2C
- **Phase 3 (P1 journeys)**: All depend on Phase 2 — T019/T020/T021 can run in parallel
- **Phase 4 (P2 journeys)**: All depend on Phase 2 — T022/T023/T024 can run in parallel
- **Phase 5 (P3 journeys)**: All depend on Phase 2 — T025/T026/T027 can run in parallel
- **Polish (Phase 6)**: Depends on all journeys complete (T019–T027)

### User Story Dependencies

- **US1 (P1)**: Independent — no pre-baked state fixture required beyond `admin_client` (T010)
- **US2 (P1)**: Independent — no US1 dependency; requires `workspace_with_agents` (T011)
- **US3 (P1)**: Independent — requires `published_agent` fixture (T012)
- **US4 (P2)**: Independent — requires `workspace_with_goal_ready` fixture (T013)
- **US5 (P2)**: Independent — requires `workspace_with_agents` (T011) + `trust_reviewer_client` (T010)
- **US6 (P2)**: Independent — requires `running_workload` (T014) + `operator_client` (T010)
- **US7 (P3)**: Independent — requires `published_agent` (T012) + `evaluator_client` (T010)
- **US8 (P3)**: Independent — requires `published_agent` (T012) seeded with A2A capability
- **US9 (P3)**: Independent — requires `researcher_client` (T010) + discovery workspace setup

### Parallel Opportunities

```bash
# Phase 2A+2B — all 7 files in parallel:
Task: "helpers/narrative.py (T003)"
Task: "helpers/oauth.py (T004)"
Task: "helpers/agents.py (T005)"
Task: "helpers/governance.py (T006)"
Task: "helpers/executions.py (T007)"
Task: "helpers/websockets.py (T008)"
Task: "plugins/narrative_report.py (T009)"

# Phase 2D — parallel with conftest work (T010-T014):
Task: "test_journey_structure.py meta-test (T015)"
Task: "values-e2e.yaml OAuth overlay (T016)"
Task: "Makefile targets (T017)"
Task: "e2e.yml CI step (T018)"

# Phase 3 — all three P1 journeys in parallel:
Task: "test_j01_admin_bootstrap.py (T019)"
Task: "test_j02_creator_to_publication.py (T020)"
Task: "test_j03_consumer_discovery_execution.py (T021)"

# Phase 4 — all three P2 journeys in parallel:
Task: "test_j04_workspace_goal_collaboration.py (T022)"
Task: "test_j05_trust_governance_pipeline.py (T023)"
Task: "test_j06_operator_incident_response.py (T024)"

# Phase 5 — all three P3 journeys in parallel:
Task: "test_j07_evaluator_improvement_loop.py (T025)"
Task: "test_j08_external_a2a_mcp.py (T026)"
Task: "test_j09_scientific_discovery.py (T027)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T018) — CRITICAL
3. Complete US1 only: `test_j01_admin_bootstrap.py` (T019)
4. **STOP and VALIDATE**: `make e2e-j01` — admin bootstrap journey passes and meta-test passes for J01
5. Demo: admin can bootstrap a platform from scratch in a single automated test

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation ready
2. T019 (J01) → `make e2e-j01` passes → **MVP** ✅
3. T020 + T021 (J02 + J03) in parallel → P1 complete: `make e2e-j02` + `make e2e-j03` pass
4. T022–T024 (J04–J06) in parallel → P2 complete
5. T025–T027 (J07–J09) in parallel → P3 complete → `make e2e-journeys` full suite passes

### Parallel Team Strategy (2 developers per plan.md)

- Developer A: T003–T009 (helpers + plugin) → T010–T014 (conftest) → T019 + T020 (J01 + J02)
- Developer B: T015–T018 (meta-test + infra) → T021 (J03) → T022 + T023 (J04 + J05)
- After P1: split P2 and P3 journeys evenly

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase
- [Story] label maps task to user story for traceability
- Implement meta-test (T015) before writing journey files so it validates them as they are added
- Helpers (T003–T008) must be complete before conftest (T010) and before any journey file
- All resources in journeys must use `j{NN}-test-{hash}-` prefix — enforced by helpers, verified by meta-test
- Pre-populate mock LLM queue before starting agent turns in each journey (FR-010)
- All OAuth flows go through in-cluster mocks (T016) — never call real Google/GitHub OAuth
- Journey timeouts per research.md D-008: J01 180s, J02–J05 300s, J06–J07 600s, J08–J09 300s
- Journeys are additive test files only — no platform code changes, no migrations, no new Kafka topics
