# Feature Specification: User Journey E2E Tests

**Feature Branch**: `072-user-journey-e2e-tests`
**Created**: 2026-04-21
**Status**: Draft
**Input**: User description: "User Journey E2E Tests — multi-step workflow tests simulating real users crossing multiple bounded contexts in a single test, extending the `tests/e2e/` harness from 071-e2e-kind-testing with a new `tests/e2e/journeys/` tree covering 9 personas: platform administrator, agent creator, consumer, workspace collaborator, trust officer, operator, evaluator, external integration, and research scientist."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Platform administrator bootstraps the platform from fresh install to production-ready (Priority: P1) 🎯 MVP

A platform administrator receives a freshly installed deployment with a bootstrap admin credential. They log in with the temporary password, are forced to change it, enroll MFA, configure Google + GitHub OAuth providers for their organization, create the first production workspace with namespaces and quotas, invite users, configure workspace-level visibility grants and governance chain (observer → judge → enforcer), and set default alert preferences. The test asserts state at every stage and confirms the workspace is discoverable and joinable by the invited users.

**Why this priority**: This is the canonical "first day" journey — without it, no production deployment can be trusted to support the other personas. It exercises the most fundamental cross-context flow (auth → OAuth admin → workspaces → registry → policies → governance → notifications) and catches bootstrap gaps that single-context tests would never see. Required P1 because the remaining journeys assume a bootstrapped platform.

**Independent Test**: With a fresh kind cluster (from feature 071), run `pytest tests/e2e/journeys/test_j01_admin_bootstrap.py`; the test must execute all 15 steps of the admin bootstrap journey, asserting state at each step, and must NOT depend on any other journey test having run first. Final state assertion: workspace exists with configured namespaces, visibility grants, quotas, governance chain, and alert settings.

**Acceptance Scenarios**:

1. **Given** a fresh platform install with a bootstrap admin credential, **When** the admin logs in with the temporary password, **Then** login succeeds but API responses flag that a password change is required before any further write operations succeed.
2. **Given** the admin changes their temporary password to a strong password, **When** they subsequently enroll TOTP MFA, **Then** MFA enrollment succeeds and subsequent logins require the second factor.
3. **Given** an admin with MFA enabled, **When** they configure both Google and GitHub OAuth providers with their organizational restrictions, **Then** a subsequent `GET /api/v1/auth/oauth/providers` returns both providers marked enabled.
4. **Given** OAuth providers are configured, **When** the admin creates the first workspace with namespaces, quotas, visibility grants, governance chain assignment, and default alert preferences, **Then** a final assertion against the workspace detail endpoint confirms every configuration element is present.
5. **Given** the workspace is fully configured, **When** an invited user attempts to join via the invitation link, **Then** the workspace is discoverable, the join succeeds, and the new member inherits the configured role.

---

### User Story 2 — Agent creator takes an agent from idea to published marketplace listing (Priority: P1)

An agent creator signs in via GitHub OAuth, opens the creator workbench, selects an organizational namespace, registers a new agent with a complete manifest (FQN, purpose ≥ 50 chars, approach, role type, visibility patterns, tools), verifies FQN resolution and zero-trust visibility enforcement, uploads a packaged revision, attaches a policy, requests certification, has a trust reviewer approve it, and then confirms the agent appears in the marketplace with trust signals, is discoverable by intent and FQN pattern, and has stored evaluation results visible on its profile.

**Why this priority**: This is the complete creator lifecycle — registration through marketplace publication — that the platform promises. Bounded-context tests cover registration, certification, and marketplace search individually; this journey is the only place where "a newly registered agent ends up searchable and trusted by a real consumer" is verified end to end. P1 because without creator-to-publication, there are no agents for consumers or workspace goals to use.

**Independent Test**: With a bootstrapped platform (US1 already validated or preconditions seeded by fixture), run `pytest tests/e2e/journeys/test_j02_creator_to_publication.py`; the test must complete all 20 steps, asserting at each step, and the final state must show the agent certified, published, and retrievable via both intent-based marketplace search and FQN-pattern search.

**Acceptance Scenarios**:

1. **Given** a creator signs in via GitHub OAuth, **When** they access the creator workbench, **Then** role-based access allows workbench views and registration actions for namespaces they own.
2. **Given** the creator registers an agent with a valid FQN and all required natural-language fields, **When** the request completes, **Then** the agent is retrievable by FQN and by namespace-pattern search from the creator's own account but is invisible to agents/accounts outside the configured visibility scope.
3. **Given** the creator uploads an agent package, **When** the upload completes, **Then** an immutable revision with a content digest is created and the agent profile reflects the new revision.
4. **Given** certification is requested, **When** a trust reviewer approves it with evidence, **Then** the agent's trust state transitions to certified and the marketplace listing reflects the certification badge plus any quality metrics.
5. **Given** the agent is certified and published, **When** a consumer searches the marketplace by intent ("KYC verification"), **Then** the agent appears in results ranked by relevance and trust, and evaluation history is visible on the agent profile.

---

### User Story 3 — Consumer discovers, launches, tracks, and reviews a task (Priority: P1)

A consumer signs in via Google OAuth (auto-provisioned on first login with a default role), browses the marketplace, searches by intent, inspects an agent profile, starts a conversation, sends a task message, subscribes to WebSocket updates for real-time progress, observes reasoning trace milestones and workflow execution steps as they occur, waits for completion, views the structured output with full reasoning trace and execution timeline, injects a follow-up message within the same conversation, configures personal alert preferences, and verifies a second task triggers the configured alerts on completion.

**Why this priority**: This is the core end-user experience — "can someone who has never used the platform before find what they need and get a result with visibility into what happened." Bounded-context tests cover conversations, executions, reasoning traces, and WebSocket events individually, but only a journey test exercises the complete user-facing loop, including real-time observability. P1 because the platform's user value is not demonstrated until this loop closes.

**Independent Test**: With a bootstrapped platform and a fully certified agent available (seeded by fixture), run `pytest tests/e2e/journeys/test_j03_consumer_discovery_execution.py`; the test must complete all 23 steps, receive live WebSocket events during execution (verified by assertion on event types and ordering), and end with a conversation containing two completed interactions plus configured alert preferences.

**Acceptance Scenarios**:

1. **Given** a first-time user signs in via Google OAuth, **When** the OAuth callback completes, **Then** a new user account is auto-provisioned with the platform's default role and subsequent API calls succeed with the issued session token.
2. **Given** the consumer searches the marketplace by intent, **When** results are returned, **Then** the ranked list is ordered by a relevance signal combined with trust signals, and the top result's agent profile displays FQN, purpose, approach, trust badges, certification, and quality metrics.
3. **Given** a conversation is started and a task message is sent, **When** the consumer subscribes to a WebSocket topic scoped to the conversation, **Then** workflow execution events, reasoning trace milestone events, and the final completion event arrive over the socket in causal order.
4. **Given** the execution completes, **When** the consumer views the reasoning trace and execution timeline, **Then** the task plan, tool selections, parameter provenance, and step durations are all present and consistent with the events observed over the WebSocket.
5. **Given** the consumer configures alert preferences (notify on completion, not on pending) and launches a second task, **When** that task completes, **Then** the configured alert fires (verified by WebSocket alert event or notification record) and the conversation history lists both completed interactions.

---

### User Story 4 — Workspace collaborator posts a goal and multiple agents collaborate to solve it (Priority: P2)

A workspace user opens a workspace that has multiple subscribed specialized agents (e.g., market-data-agent, risk-analysis-agent, client-advisory-agent, plus an irrelevant notification-agent), creates a workspace goal with a multi-sentence objective, observes the goal transition from READY to WORKING when a message is posted, confirms that only relevant agents (per their configured response-decision policy) choose to respond while the irrelevant agent does not, tracks every message through the same Goal Correlation ID (GID), posts follow-up messages that steer agent focus, responds to an attention request raised mid-flow, marks the goal COMPLETE, and verifies GID propagation reached the analytics store and event log.

**Why this priority**: This journey exercises the most distinctively multi-agent property of the platform — a workspace where many specialized agents observe a goal and collectively decide who should act. Bounded-context tests cover goal CRUD, response decision, GID envelope, and attention requests individually; only a journey exercises "does the combination actually produce a useful collaborative result with correct correlation propagated everywhere." P2 because the single-consumer path (US3) delivers immediate value without multi-agent orchestration.

**Independent Test**: With a bootstrapped platform and a workspace pre-configured with three relevant agents + one irrelevant agent (seeded by fixture), run `pytest tests/e2e/journeys/test_j04_workspace_goal_collaboration.py`; the test must create a goal, assert state transitions, verify the participant set on resulting messages includes relevant agents and excludes the irrelevant one, verify GID matches across every message and appears in at least one analytics/event-log query, resolve an attention request, and mark the goal complete.

**Acceptance Scenarios**:

1. **Given** a workspace has four subscribed agents (three relevant by capability, one irrelevant), **When** a goal is created and a first message is posted, **Then** the goal transitions from READY to WORKING and the response-decision log records a deliberate "respond" decision for relevant agents and a "pass" for the irrelevant one.
2. **Given** responses arrive from multiple agents, **When** messages are listed under the goal, **Then** each message's `gid` field equals the goal's assigned GID and each message's `participant_id` is the FQN of an agent that chose to respond.
3. **Given** a follow-up user message refines the objective, **When** agents receive it, **Then** subsequent agent messages reflect the refinement (verifiable via content search or by metadata marker set by the agent adapter).
4. **Given** an agent raises an attention request, **When** the WebSocket subscriber connected to the attention channel receives it, **Then** the request includes an urgency level, a target user identifier, and a reference to the goal's GID.
5. **Given** the goal is marked COMPLETE, **When** a subsequent message POST is attempted, **Then** the API rejects the write with a state-violation error and the GID appears in at least one downstream record (analytics, event log) confirming propagation.

---

### User Story 5 — Trust officer builds the governance pipeline end-to-end (Priority: P2)

A trust officer authors a safety policy (e.g., "Agents must not disclose PII"), attaches it to a workspace, configures a governance chain (observer → judge → enforcer) by assigning registered agents to each role, triggers an agent execution that would violate the policy (both an obvious violation caught by the SafetyPreScreener in <10 ms and a subtle violation that passes the pre-screener and flows through the Observer→Judge→Enforcer pipeline), verifies the judge issues a VIOLATION verdict with rationale, confirms the enforcer blocks the action and notifies a human operator, inspects the audit trail, attaches a behavioral contract with response-time and accuracy thresholds, triggers a contract breach, and verifies the contract monitor enforces it. The officer then requests third-party certification for a compliant agent, certifies in the third-party-reviewer role, sees the third-party badge appear in the marketplace, triggers surveillance-driven recertification after an agent revision, and decommissions a non-compliant agent.

**Why this priority**: Governance is the platform's safety-and-compliance backbone; without a journey test, reviewers cannot trust that all individually-tested components actually compose into the safety promise. P2 because day-one operation (US1–US3) can still function with manual review while this journey matures.

**Independent Test**: With a bootstrapped platform (US1 preconditions) and two agents in a workspace (one compliant, one that will violate), run `pytest tests/e2e/journeys/test_j05_trust_governance.py`; the test must author a policy, attach it, configure the governance chain, trigger the two violation scenarios, observe verdicts + enforcement actions, attach + breach a contract, complete third-party certification, and decommission an agent — each stage asserted independently.

**Acceptance Scenarios**:

1. **Given** a workspace has a safety policy attached and a governance chain configured, **When** an execution produces output that obviously violates the policy, **Then** the SafetyPreScreener catches the violation in under 10 ms and blocks the output before it reaches any Observer/Judge/Enforcer agents.
2. **Given** a subtle violation that bypasses the pre-screener, **When** it flows through the pipeline, **Then** the observer emits a detection signal, the judge issues a VIOLATION verdict with a documented rationale, the enforcer blocks the action, and a notification reaches a human operator (verifiable via WebSocket or notification record).
3. **Given** the pipeline has run, **When** the trust officer inspects the audit trail, **Then** every verdict and enforcement action is present with timestamps, rationale, and correlation IDs linking them to the originating execution.
4. **Given** a behavioral contract attaches response-time and accuracy thresholds, **When** an execution breaches the response-time threshold, **Then** the contract monitor detects the breach and triggers the configured enforcement action.
5. **Given** a compliant agent requests third-party certification, **When** the third-party certifier reviews and approves, **Then** the certification appears on the marketplace listing with a distinct third-party badge distinguishable from internal certification.
6. **Given** an agent is decommissioned, **When** the marketplace is queried, **Then** the agent is absent from discovery results, but its historical data (executions, interactions, evaluations) remains retrievable via direct ID lookup for compliance/audit purposes.

---

### User Story 6 — Operator monitors, diagnoses a failure, recovers, and manages lifecycle (Priority: P2)

An operator opens the operator dashboard and reviews fleet health, active executions, and warm-pool status (pool size, available pods, hit rate), launches a long-running multi-step execution that creates checkpoints, simulates a mid-execution failure by killing the agent's runtime pod, verifies the platform detects the failure via RuntimeController heartbeat, performs a rollback to the last checkpoint, confirms the execution resumes from checkpoint state rather than from scratch, inspects the execution timeline with reasoning traces, reviews governance verdicts for recent executions, queues multiple executions and injects an urgent one to observe re-prioritization, views analytics for performance/token-usage/cost, reviews and approves an AgentOps adaptation proposal, triggers a canary deployment of the new revision, and decommissions an underperforming agent while preserving its historical data.

**Why this priority**: This journey is the operational control loop — without it, no one can confirm the platform's reliability features (checkpointing, warm pool, re-prioritization, canary deployment) compose correctly for a real operator under realistic failure. P2 because this journey assumes the platform is running and being used (US1–US3), and operators are a smaller population than creators/consumers.

**Independent Test**: With a bootstrapped platform and a running workload environment (seeded fixture containing a fleet, several executions in progress, a warm pool filled, and a failing canary candidate), run `pytest tests/e2e/journeys/test_j06_operator_incident_response.py`; the test must drive all 24 steps — dashboard view, long execution with checkpoints, forced pod kill, rollback + checkpoint-resume verification, trace inspection, re-prioritization, adaptation approval, canary deployment, decommission — each with independent assertions.

**Acceptance Scenarios**:

1. **Given** the operator is on the dashboard, **When** they view warm-pool metrics, **Then** pool size, available pods, and dispatch hit rate are displayed with values consistent with recent activity.
2. **Given** a long-running execution is started, **When** its runtime pod is killed mid-flight, **Then** platform heartbeat detection surfaces the failure within the heartbeat-timeout window, and an operator-initiated rollback resumes execution from the most recent checkpoint with state intact (not restarted from scratch).
3. **Given** multiple executions are queued, **When** an urgent execution is injected with a higher priority, **Then** the scheduler reorders the queue so the urgent one runs next (verifiable via execution start-time ordering).
4. **Given** AgentOps generates an adaptation proposal, **When** the operator approves it, **Then** a new agent revision is created and a canary deployment with a defined traffic split is triggered; rolling back is available via a single API call.
5. **Given** an agent is decommissioned, **When** the operator views marketplace discovery, **Then** the agent is absent, but historical executions remain accessible for audit — consistent with US5's decommission criteria.

---

### User Story 7 — Evaluator runs quality assessment and closes the adaptation loop (Priority: P3)

An evaluator creates an evaluation suite for an agent, configures a TrajectoryScorer with named dimensions (path efficiency, tool appropriateness, reasoning coherence, cost effectiveness), configures an LLM-as-Judge with a custom rubric, runs the suite across ten test cases, runs a calibration pass that re-judges three cases five times each (producing score distributions), views per-case trajectory scores and judge rationales, compares the results across two agent revisions to detect behavioral regressions, triggers the adaptation pipeline from the evaluation, approves an adaptation proposal to create an improved revision, and re-runs the suite to verify measurable improvement.

**Why this priority**: This is the quality-improvement control loop — critical for mature platform operation but not for day-one deployment. P3 because day-one and ongoing operation (US1–US6) can proceed without a formal evaluator workflow in place; this journey locks in the feedback loop that makes continuous improvement measurable.

**Independent Test**: With a bootstrapped platform and two agent revisions seeded as fixtures (one baseline, one regression candidate), run `pytest tests/e2e/journeys/test_j07_evaluator_improvement_loop.py`; the test must create the suite, run both scoring modes on ten cases, produce a calibration distribution, compare revisions, trigger and approve an adaptation, and verify the resulting revision achieves a measurable improvement on re-evaluation.

**Acceptance Scenarios**:

1. **Given** a TrajectoryScorer is configured with four named dimensions, **When** the suite runs against ten test cases, **Then** each case has four dimensional scores persisted and retrievable.
2. **Given** calibration re-judges three cases five times each, **When** the run completes, **Then** score distributions (mean and standard deviation) are computed and persisted for each case.
3. **Given** two agent revisions have been evaluated, **When** the comparison report is generated, **Then** per-dimension deltas are surfaced and any statistically-significant regression is flagged.
4. **Given** an adaptation proposal is approved, **When** the new revision is created and re-evaluated, **Then** the comparison report shows the dimensions expected to improve have indeed improved by a measurable margin.

---

### User Story 8 — External system integrates via A2A and MCP (Priority: P3)

An external system or developer fetches the platform's Agent Card from the well-known URL, inspects its capabilities and auth schemes, fetches a per-agent card by FQN, authenticates via OAuth2 bearer token, submits an A2A task, subscribes to SSE for progress, observes the task transition through submitted → working → completed states with events received in correct order, retrieves the final result, submits a multi-turn A2A task requiring clarification exchanges, discovers platform tools via MCP, invokes a tool via MCP ensuring the call passes through platform policy checks and that output is sanitized (no secrets).

**Why this priority**: External protocol compatibility (A2A + MCP) is a key integration surface. Bounded-context tests cover the individual endpoints, but only a journey test verifies that a third-party integrator's complete flow — discover, authenticate, task, stream, tool — actually succeeds against a real cluster. P3 because external integration can be tested later without blocking platform GA for internal users.

**Independent Test**: With a bootstrapped platform and a published A2A-capable agent (seeded), run `pytest tests/e2e/journeys/test_j08_external_integration.py`; the test must fetch Agent Cards (platform + per-agent), authenticate via OAuth2, submit single-turn and multi-turn A2A tasks and assert SSE ordering, discover and invoke MCP tools, and verify policy-enforced sanitization.

**Acceptance Scenarios**:

1. **Given** the platform exposes Agent Cards, **When** an external client fetches the well-known URL and a per-agent URL, **Then** both return valid JSON with the documented capabilities, auth schemes, and per-agent skills (purpose, approach, visibility).
2. **Given** an A2A task is submitted, **When** the client subscribes to SSE progress, **Then** state-transition events arrive in causal order (submitted → working → completed or → failed) with the correct payload shape at each step.
3. **Given** a multi-turn A2A task is submitted requiring a clarification exchange, **When** the server requests clarification and the client responds, **Then** the task state reflects the exchange and eventually completes with a correct final result referencing the full turn history.
4. **Given** platform tools are discovered via MCP, **When** the client invokes a tool, **Then** the call passes through the tool gateway with policy enforcement applied, and any secret-like values in the output are redacted before the response returns.

---

### User Story 9 — Research scientist runs the hypothesis-to-experiment discovery loop (Priority: P3)

A researcher creates a discovery workspace, triggers hypothesis generation from seed data, views generated hypotheses, triggers a Chain of Debates across top hypotheses, observes debate rounds (position → critique → rebuttal → synthesis) with transcripts persisted, triggers Elo-based tournament ranking, inspects the proximity graph to see similar hypotheses clustered, verifies generation biases toward underrepresented clusters, triggers evolution of the top-ranked hypothesis producing a refined variant, and triggers experiment design for the validated hypothesis, ending with an experiment plan.

**Why this priority**: The scientific discovery flow uses the most specialized subsystems (Chain of Debates reasoning mode, Elo tournaments, proximity graph, knowledge graph). Without a journey test, these stages are only tested individually and the compounding correctness is unverified. P3 because scientific discovery is a specialized subset of users and is not critical for general platform operation.

**Independent Test**: With a bootstrapped discovery workspace (seeded fixture with seed data for hypothesis generation), run `pytest tests/e2e/journeys/test_j09_scientific_discovery.py`; the test must drive generation → debate → ranking → clustering → evolution → experiment design — each stage asserted independently, producing a final experiment plan.

**Acceptance Scenarios**:

1. **Given** seed data and generation agents, **When** hypothesis generation is triggered, **Then** at least the configured minimum number of initial hypotheses are produced and stored.
2. **Given** top hypotheses, **When** Chain of Debates is triggered, **Then** debate rounds produce position, critique, rebuttal, and synthesis messages with transcripts persisted as reasoning artifacts.
3. **Given** hypotheses have been debated, **When** tournament ranking runs, **Then** every hypothesis has an Elo score and the proximity graph clusters similar hypotheses together.
4. **Given** the top-ranked hypothesis is selected for evolution, **When** evolution runs, **Then** a refined variant hypothesis is produced referencing the original, and an experiment-design step produces a structured experiment plan for the validated hypothesis.

---

### Edge Cases

- **Persona fixture clashes between parallel journeys**: two journeys running in parallel must not stomp on each other's workspace, user, or agent state; each journey creates its own isolated workspace (name prefixed `j{NN}-test-`) and uses unique user email suffixes (`@e2e.test` scope filter preserved).
- **OAuth mock providers shared across journeys**: the mock Google and GitHub OAuth providers must handle concurrent callbacks from multiple journeys; callback state is keyed by a per-journey correlation ID.
- **Long-running journey exceeds default pytest timeout**: journeys must declare explicit per-journey timeouts (e.g., `@pytest.mark.timeout(600)` for journeys that include 10-case evaluation or long execution runs).
- **A journey depends on an agent being certified AND deployed**: fixtures must include a "fully baked" agent fixture that is already certified, published, and warm, so journeys starting mid-flow don't re-execute the full creator journey to set up.
- **Journey fails mid-flow leaving residual state**: teardown must use idempotent cleanup (`DELETE ... WHERE name LIKE 'j{NN}-test-%'` scope filter) so a failed journey doesn't poison the next run.
- **WebSocket event ordering under load**: when multiple executions run concurrently, the per-conversation WebSocket subscription must deliver events in causal order; tests assert order within a single conversation, not globally.
- **Mock LLM queue drained mid-journey**: journey tests use the mock LLM FIFO queue; a journey with N agent turns must pre-populate N responses before starting to avoid non-deterministic fallback behavior mid-flow.
- **GID propagation gap between services**: a journey-level assertion must verify GID reaches the analytics store AND event log; a gap in even one downstream service (possible when a service is redeployed mid-test) fails the journey.
- **Attention request target offline**: if the user who should receive an attention request isn't connected via WebSocket, the request must be retained in a durable store so the test can resolve it via polling or reconnection.
- **Third-party certifier stub unavailable**: the in-cluster third-party certifier stub must be explicitly healthy before journey 5 runs; a failing health check should skip (not fail) the journey with a clear message.
- **A journey re-runs after a previous failure**: every assertion must be idempotent with respect to fixture state; re-running a journey after a prior failure must not require manual cleanup beyond `make e2e-reset`.

## Requirements *(mandatory)*

### Functional Requirements

**Journey harness and organization**

- **FR-001**: The harness MUST host journey tests in a new `tests/e2e/journeys/` directory, parallel to the existing `tests/e2e/suites/` (bounded-context) directory, so that journey tests can be discovered and run independently from context suites.
- **FR-002**: The harness MUST provide 9 journey test files, one per persona: admin bootstrap (`test_j01_admin_bootstrap.py`), creator-to-publication (`test_j02_creator_to_publication.py`), consumer discovery and execution (`test_j03_consumer_discovery_execution.py`), workspace goal collaboration (`test_j04_workspace_goal_collaboration.py`), trust officer governance (`test_j05_trust_governance.py`), operator incident response (`test_j06_operator_incident_response.py`), evaluator improvement loop (`test_j07_evaluator_improvement_loop.py`), external integration (`test_j08_external_integration.py`), scientific discovery (`test_j09_scientific_discovery.py`).
- **FR-003**: Each journey test MUST cross at minimum four bounded contexts, verified by an inventory comment at the top of the file listing the contexts it exercises.
- **FR-004**: Each journey test MUST include at least 15 named assertion points, each asserting state (entity presence, state-machine transition, event arrival, correlation ID propagation) rather than merely absence of errors.
- **FR-005**: Each journey test MUST declare a pytest marker identifying the journey (`@pytest.mark.journey` + a per-journey marker `@pytest.mark.j01_admin` through `@pytest.mark.j09_discovery`) so that selective execution by marker works from the command line.

**Fixtures and independence**

- **FR-006**: The journey harness MUST provide persona-specific fixtures: `admin_client`, `creator_client`, `consumer_client`, `operator_client`, `trust_reviewer_client`, `evaluator_client`, `researcher_client`, plus auxiliary fixtures for `workspace_with_agents`, `published_agent`, `workspace_with_goal_ready`, and `running_workload`.
- **FR-007**: Journey tests MUST be independent — a journey's success MUST NOT depend on any other journey having run first; the pytest run order MUST produce identical results when journeys run in any order.
- **FR-008**: Journey tests MUST be isolated — concurrent execution of two or more journeys on the same cluster MUST NOT cause cross-interference; each journey creates its own workspace, users, and agents under a per-journey name prefix.
- **FR-009**: Journey fixtures MUST use idempotent teardown matching an E2E-scope filter (e.g., workspace name `LIKE 'j{NN}-test-%'`) so a failed journey leaves no state that breaks subsequent runs.
- **FR-010**: Journey tests MUST use the mock LLM provider exclusively (no real LLM API calls), pre-populating sufficient responses for all agent turns before the journey starts.

**OAuth mock providers**

- **FR-011**: The harness MUST include mock Google OIDC and GitHub OAuth providers running in-cluster, callable by journey tests to drive OAuth-based login flows for admin, creator, and consumer personas.
- **FR-012**: OAuth mock providers MUST support per-journey correlation IDs so multiple journeys running in parallel do not cross-contaminate OAuth state.

**WebSocket, GID, and event assertions**

- **FR-013**: Journey tests that include real-time flows (US3 consumer, US4 workspace goal, US5 trust notifications, US6 operator) MUST assert on WebSocket event ordering and payload shape, not just event receipt.
- **FR-014**: Journey tests crossing interactions, executions, and analytics MUST assert GID propagation: a goal's GID MUST appear in the goal record, every associated message, every associated execution event, and at least one analytics/event-log downstream record.
- **FR-015**: Journey tests exercising the governance pipeline (US5) MUST assert on the Observer→Judge→Enforcer chain with verdict rationale and enforcement action recorded in the audit trail.

**Checkpoint, warm pool, and priority assertions**

- **FR-016**: The operator journey (US6) MUST exercise checkpoint-based recovery by triggering a runtime pod kill and asserting execution resumes from checkpoint state (not from scratch) with state fidelity verifiable via direct DB query.
- **FR-017**: The operator journey (US6) MUST measure warm-pool dispatch latency and assert dispatch-from-warm-pool completes under the warm-pool launch threshold from feature 071's performance thresholds.
- **FR-018**: The operator journey (US6) MUST exercise queue re-prioritization: queue multiple executions, inject an urgent one with higher priority, and assert start-time ordering reflects the new priority.

**A2A and MCP protocol assertions**

- **FR-019**: The external integration journey (US8) MUST fetch the platform Agent Card, fetch a per-agent card by FQN, and assert both return valid JSON conforming to the documented A2A schema.
- **FR-020**: The external integration journey (US8) MUST exercise the A2A task lifecycle with SSE streaming, asserting events arrive in causal order (submitted → working → completed or → failed).
- **FR-021**: The external integration journey (US8) MUST exercise MCP tool discovery and invocation, asserting the invocation passes through platform policy checks and output is sanitized.

**Reports and narrative output**

- **FR-022**: The journey harness MUST emit JUnit XML and HTML reports (extending feature 071's reporting), with a dedicated `journeys-junit.xml` and `journeys-report.html` pair for ease of triage.
- **FR-023**: Each journey test MUST produce human-readable narrative output via pytest's `-v` mode — each assertion point prints a brief description of what was verified — so a reviewer can read the test output as a story.
- **FR-024**: The `make e2e-journeys` target MUST run the full journey suite; `make e2e-j{NN}` targets MUST run a single journey (e.g., `make e2e-j03`).

**Dependence on feature 071**

- **FR-025**: This feature MUST reuse feature 071's kind cluster, seeders, fixtures (http_client, ws_client, db, kafka_consumer, mock_llm), and dev-only `/api/v1/_e2e/*` endpoints — no duplicate cluster provisioning, seeder logic, or test-only endpoint surface may be introduced.

### Key Entities

- **Journey** — a single multi-step test file simulating a persona's workflow across multiple bounded contexts; identified by a sequential ID (j01–j09), a persona, an acceptance scenario set, and a list of crossed contexts.
- **Persona** — a named user role (Admin, Creator, Consumer, Workspace Collaborator, Trust Officer, Operator, Evaluator, External Integrator, Researcher) with its own authenticated client fixture and permission scope.
- **Assertion Point** — a named verification step within a journey; each asserts state (entity existence, state transition, event arrival, correlation propagation) rather than merely the absence of exceptions.
- **Persona Fixture** — a pytest fixture that returns a pre-authenticated client for a specific persona, wired to the platform API with the correct role and workspace scope.
- **Pre-baked Fixture** — a fixture that seeds a downstream state (a certified agent, a bootstrapped workspace, a running workload) so a journey can start mid-flow without re-executing upstream journeys.
- **Journey Marker** — a pytest marker (`@pytest.mark.j{NN}_{persona}`) enabling selective execution by the command line.
- **Journey Report Artifact** — the JUnit XML and HTML report bundle written to `tests/e2e/reports/` after journey execution; consumed by CI and by human reviewers.
- **Isolation Scope** — a per-journey name prefix (`j{NN}-test-`) applied to workspaces, users, and agents so that concurrent journeys cannot interfere.
- **OAuth Mock Provider** — an in-cluster stub Google OIDC or GitHub OAuth server that handles per-journey OAuth flows; deterministic, keyed by correlation ID.
- **Cross-Context Inventory** — a comment block at the top of each journey test file listing the bounded contexts the journey exercises; mechanically inspectable to verify FR-003.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fresh kind cluster provisioned by feature 071, running `make e2e-journeys` executes all 9 journey tests and reports pass/fail for each on ≥ 95% of attempts under nominal conditions.
- **SC-002**: Each journey test file executes a minimum of 15 distinct assertion points (verifiable by a static test that parses each journey file and counts `assert` statements + fixture-level state verifications).
- **SC-003**: Each journey test file exercises a minimum of 4 distinct bounded contexts from feature 071's bounded-context list (verifiable by the mandatory cross-context inventory comment + a test that compares it to a registry of bounded-context names).
- **SC-004**: The complete `make e2e-journeys` run completes within 30 minutes on the reference CI runner (`ubuntu-latest-8-cores`) in 90% of runs.
- **SC-005**: Any 2 journeys can run concurrently on the same cluster with non-overlapping isolation scopes and both complete successfully; verified by a parallel-execution test running `pytest tests/e2e/journeys/ -n 2` in CI.
- **SC-006**: A journey test rerun after a prior failure (without manual cleanup beyond `make e2e-reset`) succeeds on ≥ 95% of attempts — idempotent teardown is effective.
- **SC-007**: OAuth flows are exercised successfully by the admin (Google + GitHub), creator (GitHub), and consumer (Google) journeys against the in-cluster mock OAuth providers.
- **SC-008**: GID propagation is verified end-to-end in the workspace goal journey (US4): the same GID appears in the goal record, all linked interaction messages, all linked execution events, and at least one downstream analytics or event-log record.
- **SC-009**: The operator journey (US6) demonstrates checkpoint-based recovery: after a forced runtime pod kill, execution resumes from the most recent checkpoint, and final state is verifiably identical to an uninterrupted run for the same workload.
- **SC-010**: Journey reports are human-readable: a reviewer unfamiliar with the codebase can open `journeys-report.html` and understand the sequence of verified user actions from the narrative output alone — validated by a one-time reviewer walkthrough in feature review.

## Assumptions

- Feature 071 (E2E on kind) is in place, providing cluster provisioning, shared fixtures, mock LLM, and the `/api/v1/_e2e/*` dev-only endpoint surface. All journey fixtures extend (not fork) feature 071's harness.
- Mock Google OIDC and GitHub OAuth servers are deployable in-cluster as part of feature 071's seeders (journey 1, 2, and 3 depend on them); if feature 071 does not yet ship them, they are added by this feature as an additive change to the `tests/e2e/cluster/` overlay.
- Per-journey workspace, user, and agent names follow a documented `j{NN}-test-{uuid}` prefix convention enforced by fixtures; the E2E reset endpoint's scope filter accommodates this prefix.
- Performance thresholds from feature 071's `performance/thresholds.py` (warm launch < 2 s, cold launch < 10 s, trivial round-trip < 5 s) are reused by the operator journey for warm-pool dispatch assertions; thresholds are not duplicated.
- Journeys are not load tests; each journey's workload is shaped to exercise logic, not stress. Runtime-intensive steps (like 10-case evaluation) are time-boxed with explicit per-journey pytest timeouts.
- LLM responses used throughout journeys are supplied via the mock LLM provider (FR-010) with deterministic queue-based fallbacks; no journey test depends on an LLM quality assessment.
- The `make e2e-journeys` target runs after `make e2e-up` (a preprovisioned cluster is expected); the CI workflow from feature 071's US5 is extended to include the journey target as an additional phase after `make e2e-test`.
- Running feature 071 + 072 journeys in the same CI workflow fits within a combined runtime budget of ≤ 75 minutes on `ubuntu-latest-8-cores`.
- Journey tests are additive and do NOT modify any bounded-context suite from feature 071; if a journey uncovers a bug in a bounded-context path, the fix is made in the application code and a regression test is added to the appropriate bounded-context suite (not to the journey).
- Journey tests produce narrative output via pytest's verbose mode; if per-step narrative clarity is insufficient, a future iteration may add a custom pytest plugin — that plugin is out of scope for this feature.
