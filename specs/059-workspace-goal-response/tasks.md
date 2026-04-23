# Tasks: Workspace Goal Management and Agent Response Decision

**Input**: Design documents from `specs/059-workspace-goal-response/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/rest-api.md ✅ quickstart.md ✅

**Tests**: Included — explicitly requested in implementation plan (Step 6: "Write tests for each strategy").

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unresolved dependencies)
- **[Story]**: User story label (US1–US6 from spec.md)
- All paths under `apps/control-plane/`

---

## Phase 1: Setup

**Purpose**: Establish a clean baseline before any brownfield changes.

- [x] T001 Run `cd apps/control-plane && pytest -x -q` to confirm all existing tests pass before any modifications

**Checkpoint**: Green baseline confirmed — brownfield extensions can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database migration + SQLAlchemy models + Pydantic schemas + settings — all user stories depend on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. T002–T007 are independent of each other (different files) and can run in parallel.

- [x] T002 [P] Create Alembic migration `046_workspace_goal_lifecycle_and_decision` in `migrations/versions/046_workspace_goal_lifecycle_and_decision.py`: CREATE TYPE workspacegoalstate AS ENUM ('ready','working','complete'); ALTER TABLE workspaces_goals ADD COLUMN state, auto_complete_timeout_seconds, last_message_at; CREATE TABLE workspaces_agent_decision_configs (workspace_id FK, agent_fqn TEXT, response_decision_strategy VARCHAR(64), response_decision_config JSONB, subscribed_at TIMESTAMPTZ) with UNIQUE(workspace_id, agent_fqn); CREATE TABLE workspace_goal_decision_rationales (goal_id FK, message_id FK, agent_fqn TEXT, strategy_name, decision VARCHAR(8), score FLOAT4, matched_terms TEXT[], rationale TEXT, error TEXT) with UNIQUE(message_id, agent_fqn) — full DDL in data-model.md; set down_revision='045_oauth_providers_and_links'
- [x] T003 [P] In `src/platform/workspaces/models.py`: add `WorkspaceGoalState(enum.Enum)` with values ready/working/complete; add mapped columns `state: Mapped[WorkspaceGoalState]` (server_default='ready'), `auto_complete_timeout_seconds: Mapped[int | None]`, `last_message_at: Mapped[datetime | None]` to the existing `WorkspaceGoal` class; add new `WorkspaceAgentDecisionConfig(Base, UUIDMixin, TimestampMixin)` class with columns workspace_id FK, agent_fqn TEXT, response_decision_strategy String(64) default='llm_relevance', response_decision_config JSONB default=dict, subscribed_at TZDateTime server_default=now(); add UNIQUE constraint and workspace relationship — full schema in data-model.md
- [x] T004 [P] In `src/platform/interactions/models.py`: add `WorkspaceGoalDecisionRationale(Base, UUIDMixin)` class with columns created_at TZDateTime, workspace_id UUID, goal_id FK→workspaces_goals (CASCADE), message_id FK→workspace_goal_messages (CASCADE), agent_fqn TEXT, strategy_name String(64), decision String(8), score Float4 nullable, matched_terms ARRAY(Text), rationale Text, error Text nullable; add UNIQUE(message_id, agent_fqn) constraint and indexes — full schema in data-model.md
- [x] T005 [P] In `src/platform/workspaces/schemas.py`: extend the existing `WorkspaceGoalResponse` (or equivalent goal GET schema) to include `state: str` and `auto_complete_timeout_seconds: int | None` fields; extend goal create/update request schemas to accept optional `auto_complete_timeout_seconds: int | None = None` — these fields must be Optional with None defaults to remain backward-compatible per Brownfield Rule 7
- [x] T006 [P] In `src/platform/interactions/schemas.py`: add `GoalStateTransitionRequest(BaseModel)` with `target_state: Literal["complete"]` and `reason: str | None`; add `GoalStateTransitionResponse` with goal_id, previous_state, new_state, automatic bool, transitioned_at; add `AgentDecisionConfigUpsert`, `AgentDecisionConfigResponse`, `AgentDecisionConfigListResponse`; add `DecisionRationaleResponse` and `DecisionRationaleListResponse` — full schema definitions in data-model.md
- [x] T007 [P] In `src/platform/common/config.py`: add `FEATURE_GOAL_AUTO_COMPLETE: bool = False` to the feature flags section (or `PlatformSettings`) and `goal_auto_complete_scan_interval_seconds: int = 60` to `InteractionsSettings` (create the section if absent)

**Checkpoint**: Migration + models + schemas + settings complete — all user story implementation can now begin.

---

## Phase 3: User Story 1 — Goal Activates on First Message (Priority: P1) 🎯 MVP

**Goal**: When a workspace member posts the first message to a READY goal, the goal transitions to WORKING automatically and atomically. Subsequent messages leave the goal in WORKING. The `last_message_at` timestamp is updated on every post.

**Independent Test**: Create goal (verify `state=ready`). POST first message. Query goal — verify `state=working` and `last_message_at` is set. POST second message — verify `state` remains `working`. (Quickstart Scenario 1)

- [x] T008 [US1] Create `src/platform/interactions/goal_lifecycle.py`: define `GoalStateConflictError(PlatformError)` exception; implement `GoalLifecycleService` class with async methods: `transition_ready_to_working(goal, session)` — sets goal.state=WORKING, publishes `workspace.goal.state_changed` Kafka event via `make_envelope(goal_id=goal.id)` on topic `workspace.goal`, commits not called here (caller commits); `assert_accepts_messages(goal)` — raises `GoalStateConflictError(409)` if `goal.state == WorkspaceGoalState.complete` with detail "Goal is complete and cannot accept new messages"; `update_last_message_at(goal, session, ts)` — sets `goal.last_message_at = ts`
- [x] T009 [US1] In `src/platform/interactions/service.py`, extend the existing `post_goal_message` method: (1) load goal with `SELECT FOR UPDATE` using `session.execute(select(WorkspaceGoal).where(...).with_for_update())` to prevent concurrent COMPLETE+post race; (2) call `GoalLifecycleService.assert_accepts_messages(goal)` — raises 409 if COMPLETE; (3) if `goal.state == WorkspaceGoalState.ready`, call `GoalLifecycleService.transition_ready_to_working(goal, session)`; (4) after inserting the message, call `GoalLifecycleService.update_last_message_at(goal, session, datetime.now(UTC))`; (5) all changes commit in the same existing transaction

**Checkpoint**: US1 complete — goal state machine activates on first message, independently verifiable.

---

## Phase 4: User Story 3 — Completed Goal Blocks New Messages (Priority: P1)

**Goal**: Workspace admin can explicitly transition a WORKING goal to COMPLETE via a new endpoint. After COMPLETE, any attempt to post a message returns 409. COMPLETE is terminal — re-transition attempts return 409. All prior messages remain readable.

**Independent Test**: POST to transition endpoint with `{"target_state":"complete"}` → verify 200, `new_state="complete"`. POST a message → verify 409 with clear error. GET messages → verify history intact. Attempt second transition → verify 409. (Quickstart Scenarios 2–3)

- [x] T010 [US3] In `src/platform/interactions/goal_lifecycle.py`: add `transition_working_to_complete(goal, session, automatic=False, reason=None)` method to `GoalLifecycleService` — validates `goal.state == WorkspaceGoalState.working` (raises `GoalStateConflictError` 409 if COMPLETE or READY), sets `goal.state = WorkspaceGoalState.complete`, publishes `workspace.goal.state_changed` event with `{"automatic": automatic, "reason": reason, "previous_state": "working", "new_state": "complete"}` via `make_envelope(goal_id=goal.id)` on `workspace.goal` topic
- [x] T011 [US3] In `src/platform/interactions/router.py`: add `POST /workspaces/{workspace_id}/goals/{goal_id}/transition` endpoint — requires workspace admin/owner role (use existing RBAC dependency); validate request body as `GoalStateTransitionRequest`; load goal (404 if not found); call `GoalLifecycleService.transition_working_to_complete`; catch `GoalStateConflictError` → return 409; commit; return `GoalStateTransitionResponse`

**Checkpoint**: US3 complete — COMPLETE state is fully enforced; manual admin transition works.

---

## Phase 5: User Story 2 — Response Decision Strategies (Priority: P1)

**Goal**: Each agent subscribed to a workspace has a configurable response decision strategy. When a message is posted, the engine evaluates every subscribed agent's strategy independently, persists a `WorkspaceGoalDecisionRationale` record per agent, and marks each as `respond` or `skip`. Admins can configure strategy per agent via new endpoints.

**Independent Test**: Configure `keyword` strategy with `keywords=["deploy"]` for agent A. POST a message containing "deploy". Query rationale — agent A shows `decision=respond, matched_terms=["deploy"]`. POST a message without "deploy" — agent A shows `decision=skip`. (Quickstart Scenarios 4, 7, 8)

- [x] T012 [US2] Create `src/platform/interactions/response_decision.py` with: `DecisionResult(BaseModel)` (decision, strategy_name, score, matched_terms, rationale, error); `ResponseDecisionStrategy(Protocol)` with `async def decide(message, goal_context, config) -> DecisionResult`; `_FailSafeSkipStrategy` that always returns `skip` with the provided error message; `STRATEGY_REGISTRY: dict[str, ResponseDecisionStrategy]` (populated in T013–T016); `def get_strategy(name) -> ResponseDecisionStrategy` returning `_FailSafeSkipStrategy` for unknown names (FR-021 fail-safe); `ResponseDecisionEngine` class with `async def evaluate_for_message(message_id, goal_id, workspace_id, message_content, goal_context, subscriptions, session) -> list[WorkspaceGoalDecisionRationale]` — iterates subscriptions, calls strategy, inserts `WorkspaceGoalDecisionRationale` rows (ignoring unique conflicts for idempotency), returns all rationale records
- [x] T013 [US2] In `src/platform/interactions/response_decision.py`: implement `LLMRelevanceDecision` — build relevance prompt from message + goal_context, POST to `settings.llm_api_url` via `httpx.AsyncClient(timeout=30.0)`, parse JSON response for `score` float, return `respond` if `score >= config["threshold"]` else `skip` with score in rationale; on any exception return `_fail_safe_skip(error=str(exc))`; register as `"llm_relevance"` in `STRATEGY_REGISTRY`
- [x] T014 [US2] In `src/platform/interactions/response_decision.py`: implement `AllowBlocklistDecision` — import `fnmatch`; tokenize message content; check each token against `config.get("blocklist",[])` using `fnmatch.fnmatch`; if any match → return `skip` with matched term; check against `config.get("allowlist",[])` using `fnmatch.fnmatch`; if any match → return `respond` with matched term; fall through to `config.get("default","skip")`; register as `"allow_blocklist"` in `STRATEGY_REGISTRY`
- [x] T015 [US2] In `src/platform/interactions/response_decision.py`: implement `KeywordDecision` — read `keywords: list[str]` from config (empty → fail-safe skip per FR-021); read `mode: str = config.get("mode","any_of")`; normalize message to lowercase unless `config.get("case_sensitive", False)`; for `any_of`: return `respond` if any keyword appears in message (record all matches in matched_terms); for `all_of`: return `respond` only if ALL keywords appear; else `skip`; register as `"keyword"` in `STRATEGY_REGISTRY`
- [x] T016 [US2] In `src/platform/interactions/response_decision.py`: implement `EmbeddingSimilarityDecision` — call embedding API via `httpx.AsyncClient(timeout=30.0)` to `settings.memory.embedding_api_url` with `{"model": settings.memory.embedding_model, "input": message}` to get query vector; call `AsyncQdrantClient.search_vectors(collection=config.get("collection","platform_memory"), query_vector=vector, limit=1)` to get top cosine score; return `respond` if `score >= config["threshold"]` else `skip`; on httpx or qdrant error → fail-safe skip; register as `"embedding_similarity"` in `STRATEGY_REGISTRY`
- [x] T017 [US2] In `src/platform/interactions/service.py`: extend `post_goal_message` (after the message is inserted and `last_message_at` updated, before commit): (1) load `WorkspaceAgentDecisionConfig` rows for this workspace via `session.execute(select(WorkspaceAgentDecisionConfig).where(WorkspaceAgentDecisionConfig.workspace_id == workspace_id))`; (2) if subscriptions exist, build `goal_context = f"{goal.title}\n{goal.description or ''}"` and call `await ResponseDecisionEngine(...).evaluate_for_message(...)`; (3) do NOT fail the message post if engine raises — catch and log; all inserts in same transaction
- [x] T018 [US2] In `src/platform/interactions/router.py`: add `PUT /workspaces/{workspace_id}/agent-decision-configs/{agent_fqn}` endpoint — URL-decode agent_fqn, upsert `WorkspaceAgentDecisionConfig` (INSERT ON CONFLICT DO UPDATE), validate strategy name via `get_strategy()` (422 on unknown), return 201 on create / 200 on update; add `GET /workspaces/{workspace_id}/agent-decision-configs` endpoint — query all configs for workspace, return `AgentDecisionConfigListResponse`

**Checkpoint**: US2 complete — all 4 individual strategies work, rationale records persist, admin config endpoints work.

---

## Phase 6: User Story 4 — Best-Match Mode Routes to Single Agent (Priority: P2)

**Goal**: When all agents in a workspace are configured with `"best_match"` strategy, the engine runs each agent's underlying numeric strategy to compute scores, selects the single highest-scoring agent to respond, and marks all others as skip. Ties break by earliest `subscribed_at`.

**Independent Test**: Configure 3 agents with `best_match`. POST a message. Verify exactly 1 `decision=respond` in rationale. With equal scores, verify earliest `subscribed_at` wins. (Quickstart Scenarios 9–10)

- [x] T019 [US4] In `src/platform/interactions/response_decision.py`: implement `BestMatchDecision` — when the engine detects all participating subscriptions use `best_match` strategy, collect all agents and their underlying score strategies (read from `response_decision_config.get("score_strategy","llm_relevance")`); run each score strategy to get a numeric score; sort by (score DESC, subscribed_at ASC); assign `respond` to index 0 and `skip` to all others; record `"not selected in best-match"` and tie-break reason in rationale; handle zero-candidate case (all strategies error → no responder); update `ResponseDecisionEngine.evaluate_for_message` to detect best-match mode (any subscription has strategy `"best_match"`) and route to cross-agent orchestration; register as `"best_match"` in `STRATEGY_REGISTRY`

**Checkpoint**: US4 complete — best-match guarantees exactly one responder, tie-break is deterministic.

---

## Phase 7: User Story 5 — Auto-Completion Timeout (Priority: P2)

**Goal**: Goals with a non-null `auto_complete_timeout_seconds` are automatically transitioned to COMPLETE by a background scanner when no message has been posted within the timeout window. The scanner is idempotent and gated behind `FEATURE_GOAL_AUTO_COMPLETE`.

**Independent Test**: Create goal with `auto_complete_timeout_seconds=60`. Post one message. Wait 65 s. Verify `state=complete` and a `workspace.goal.state_changed` event with `automatic=true` was emitted. Create a second goal with the same timeout, post a message at t=0, post another at t=50 — verify goal remains WORKING at t=65 (timer reset). (Quickstart Scenarios 11–12)

- [x] T020 [US5] In `src/platform/interactions/goal_lifecycle.py`: add `GoalAutoCompletionScanner` class with `async def scan_and_complete_idle_goals(session: AsyncSession) -> int` — execute `SELECT ... FROM workspaces_goals WHERE state='working' AND auto_complete_timeout_seconds IS NOT NULL AND last_message_at + auto_complete_timeout_seconds * interval '1 second' < NOW() FOR UPDATE SKIP LOCKED` (prevents double-transition under concurrent scanner replicas); for each row call `GoalLifecycleService.transition_working_to_complete(goal, session, automatic=True)`; commit after each batch; return count of goals transitioned; log count at INFO level
- [x] T021 [US5] In `src/platform/main.py`: add `_build_goal_auto_completion_scheduler(app: FastAPI) -> Any | None` function following the existing `_build_connectors_worker_scheduler` pattern — check `app.state.settings.FEATURE_GOAL_AUTO_COMPLETE`; if False return None; create `AsyncIOScheduler(timezone="UTC")`; add interval job calling `GoalAutoCompletionScanner().scan_and_complete_idle_goals(session)` every `app.state.settings.interactions.goal_auto_complete_scan_interval_seconds` seconds; register scheduler in lifespan startup/shutdown alongside existing schedulers (connector_worker_scheduler, etc.)

**Checkpoint**: US5 complete — auto-completion scanner works with feature flag, timer resets on new messages.

---

## Phase 8: User Story 6 — Decision Rationale is Queryable (Priority: P3)

**Goal**: Workspace admins can retrieve the decision rationale for any message (one entry per subscribed agent) and can list all rationale records for a goal with optional filters. No credential or secret appears in any rationale field.

**Independent Test**: Post messages through several strategies. GET `.../messages/{id}/rationale` — verify one entry per subscribed agent with strategy_name, decision, score, matched_terms. Verify no entry contains a string matching `r'[A-Za-z0-9+/]{40,}'` (secret pattern scan). (Quickstart Scenario 13)

- [x] T022 [US6] In `src/platform/interactions/service.py`: add `async def list_rationale_for_message(message_id, workspace_id, session) -> DecisionRationaleListResponse` — query `workspace_goal_decision_rationales WHERE message_id=? AND workspace_id=?` ordered by `created_at`; verify the message belongs to this workspace (404 if not found); return serialized list; add `async def list_rationale_for_goal(goal_id, workspace_id, session, page, page_size, agent_fqn=None, decision=None) -> DecisionRationaleListResponse` — paginated query with optional filters on `agent_fqn` and `decision`
- [x] T023 [US6] In `src/platform/interactions/router.py`: add `GET /workspaces/{workspace_id}/goals/{goal_id}/messages/{message_id}/rationale` endpoint — requires workspace admin role; delegates to `service.list_rationale_for_message`; returns `DecisionRationaleListResponse`; add `GET /workspaces/{workspace_id}/goals/{goal_id}/rationale` endpoint — requires workspace admin role; accepts `page`, `page_size`, `agent_fqn`, `decision` query params; delegates to `service.list_rationale_for_goal`; returns paginated `DecisionRationaleListResponse`

**Checkpoint**: US6 complete — all six user stories are independently functional and testable.

---

## Phase 9: Polish & Tests

**Purpose**: Test coverage (explicitly requested in plan Step 6) and cross-cutting verification.

- [x] T024 [P] Write unit tests for all 5 response decision strategies in `tests/unit/interactions/test_response_decision.py`: mock `httpx.AsyncClient` and `AsyncQdrantClient`; test LLMRelevanceDecision (respond at threshold, skip below, httpx error → skip with error); test AllowBlocklistDecision (blocklist hit, allowlist hit, default fallback, blocklist beats allowlist); test KeywordDecision (any_of match/no-match, all_of match/partial, case-insensitive, empty keywords → fail-safe); test EmbeddingSimilarityDecision (above threshold → respond, below → skip, client error → skip); test BestMatchDecision (highest scorer wins, tie-break by subscribed_at, all-error → no responder); test `get_strategy("unknown_xyz")` returns _FailSafeSkipStrategy
- [x] T025 [P] Write unit tests for GoalLifecycleService in `tests/unit/interactions/test_goal_lifecycle.py`: mock session and Kafka producer; test `transition_ready_to_working` (correct state, event emitted); test `assert_accepts_messages` (passes for READY/WORKING, raises GoalStateConflictError for COMPLETE); test `transition_working_to_complete` with automatic=False (event emitted, automatic=False in payload); test `transition_working_to_complete` when already COMPLETE (raises GoalStateConflictError 409); test that state transitions are one-directional
- [x] T026 Write integration tests in `tests/integration/interactions/test_goal_lifecycle_integration.py` using real AsyncSession (test DB): (1) full flow: create goal → assert state=ready → post first message → assert state=working + last_message_at set + rationale records created; (2) post to COMPLETE goal → assert 409 + no message stored in DB; (3) auto-completion scanner: insert WORKING goal with elapsed timeout → call `scan_and_complete_idle_goals` → assert state=complete; (4) idempotent scanner: call scanner twice on same goal → assert only one COMPLETE event emitted; (5) rationale UNIQUE constraint: insert duplicate (message_id, agent_fqn) → assert DB constraint error is handled gracefully

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories; T002–T007 are all parallel within this phase
- **Phase 3 (US1)**: Depends on Phase 2 complete — T008 before T009 (same logical unit)
- **Phase 4 (US3)**: Depends on Phase 3 (T008/T009 must exist — `goal_lifecycle.py` must exist to extend)
- **Phase 5 (US2)**: Depends on Phase 2 — T012 before T013–T016 (same file, sequential); T017 depends on T012–T016; T018 independent of T012–T016
- **Phase 6 (US4)**: Depends on Phase 5 (T012–T016 — extends same file and same engine)
- **Phase 7 (US5)**: Depends on Phase 3 (T020 extends `goal_lifecycle.py`)
- **Phase 8 (US6)**: Depends on Phase 5 (rationale records only exist after T012–T017)
- **Phase 9 (Polish)**: Depends on all phases complete; T024 and T025 are parallel

### User Story Dependencies

```
US1 (P1) → US3 (P1) → [US5 builds on lifecycle]
US2 (P1) → US4 (P2) [best-match extends strategies]
         → US6 (P3) [rationale query requires rationale records]
US1 independent of US2 (different concerns, different files)
US5 independent of US2/US4/US6
```

### Within Each User Story

- Models → Services → Endpoints (same ordering within each phase)
- Same-file tasks are always sequential
- Cross-file tasks within a phase can be parallel where marked [P]

### Parallel Opportunities

Within Phase 2: T002 ‖ T003 ‖ T004 ‖ T005 ‖ T006 ‖ T007 (all different files)  
Within Phase 9: T024 ‖ T025 (different test files)  
Across phases after Phase 2: US1 (Phase 3) ‖ US2 (Phase 5 begins) once Phase 2 complete

---

## Parallel Example: Phase 2 (Foundational)

```bash
# All six foundational tasks can be dispatched simultaneously:
Task: "T002 — Create Alembic migration 046 in migrations/versions/046_workspace_goal_lifecycle_and_decision.py"
Task: "T003 — Extend WorkspaceGoal + add WorkspaceAgentDecisionConfig in workspaces/models.py"
Task: "T004 — Add WorkspaceGoalDecisionRationale in interactions/models.py"
Task: "T005 — Extend goal schemas in workspaces/schemas.py"
Task: "T006 — Add new interaction schemas in interactions/schemas.py"
Task: "T007 — Add feature flag + scanner settings in common/config.py"
```

## Parallel Example: Phase 9 (Tests)

```bash
# Strategy tests and lifecycle tests can run in parallel:
Task: "T024 — Unit tests for response decision strategies"
Task: "T025 — Unit tests for GoalLifecycleService"
```

---

## Implementation Strategy

### MVP (US1 + US3 only — lifecycle without strategies)

1. Complete Phase 1: Verify baseline
2. Complete Phase 2: Foundational (migration + models + schemas)
3. Complete Phase 3: US1 — goal activates on first message
4. Complete Phase 4: US3 — COMPLETE blocks messages
5. **STOP and VALIDATE**: Post messages, transition to COMPLETE, verify 409. Run Quickstart Scenarios 1–3.
6. Merge / deploy — lifecycle is fully functional without decision strategies

### Incremental Delivery

1. Foundation → MVP (US1 + US3) → Demo basic lifecycle
2. Add US2 (decision strategies) → 4 strategies work, rationale persists → Demo per-agent filtering
3. Add US4 (best-match) → Single responder guaranteed → Demo efficiency mode
4. Add US5 (auto-completion) → Operational burden reduced → Demo ops feature
5. Add US6 (rationale query) → Full observability → Demo audit/debug capability
6. Add tests (Phase 9) → Polish complete

### Parallel Team Strategy

With 2 developers after Phase 2:
- Developer A: US1 (T008–T009) → US3 (T010–T011) → US5 (T020–T021)
- Developer B: US2 (T012–T018) → US4 (T019) → US6 (T022–T023)

---

## Notes

- [P] tasks touch different files — verify before parallelizing within the same editing session
- `interactions/goal_lifecycle.py` is touched in US1 (T008), US3 (T010), US5 (T020) — always extend, never replace (Brownfield Rule 1)
- `interactions/service.py` is touched in US1 (T009), US2 (T017), US6 (T022) — extend `post_goal_message` incrementally
- `interactions/router.py` is touched in US3 (T011), US2 (T018), US6 (T023) — add endpoints only, never remove
- `interactions/response_decision.py` is touched in US2 (T012–T016) and US4 (T019) — always extend the registry
- Migration down_revision MUST be `045_oauth_providers_and_links`; verify with `alembic history` before merging
- Run `alembic upgrade head` and `alembic downgrade -1` to verify rollback before merging
- Feature flag `FEATURE_GOAL_AUTO_COMPLETE=false` is the default; scanner only starts when flag is true
- Decision rationale UNIQUE(message_id, agent_fqn) — engine must handle INSERT ON CONFLICT DO NOTHING for idempotency
