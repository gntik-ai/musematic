# Implementation Plan: Workspace Goal Management and Agent Response Decision

**Branch**: `059-workspace-goal-response` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/059-workspace-goal-response/spec.md`

## Summary

Extend the interactions bounded context to support a goal lifecycle state machine (READY → WORKING → COMPLETE), configurable per-agent response decision strategies (LLM-relevance, allow/blocklist, keyword, embedding-similarity, best-match), automatic goal completion after a configurable idle timeout, and an immutable decision rationale audit table. All changes are strictly additive: three new DB columns on `workspaces_goals`, one new table `workspaces_agent_decision_configs` (normalizes per-agent strategy config), and one new table `workspace_goal_decision_rationales` (immutable rationale log). Strategy execution follows the existing `evaluation/scorers` Protocol pattern. The auto-completion scanner follows the existing `connectors` APScheduler pattern.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, APScheduler 3.x, httpx 0.27+ (LLM/embedding calls), qdrant-client 1.12+ (embedding similarity), redis-py 5.x async  
**Storage**: PostgreSQL 16 (3 schema changes), Qdrant (read-only for embedding similarity), Kafka topic `workspace.goal` (existing)  
**Testing**: pytest + pytest-asyncio 8.x  
**Target Platform**: Python control plane (modular monolith, `api` + `worker` runtime profiles)  
**Project Type**: Brownfield extension of the `interactions` and `workspaces` bounded contexts  
**Performance Goals**: Decision latency p95 ≤ 2s (SC-005); goal state transition ≤ 1s (SC-002); config update takes effect ≤ 5s (SC-011)  
**Constraints**: Additive-only DB changes; backward-compatible existing endpoints; auto-complete scanner behind `FEATURE_GOAL_AUTO_COMPLETE` flag; no new LLM/embedding providers

## Constitution Check

| Rule | Status | Notes |
|------|--------|-------|
| Never rewrite existing code | ✅ PASS | All changes are extensions or new files |
| Every change is Alembic migration | ✅ PASS | Migration 046 covers all DDL |
| Preserve all existing tests | ✅ PASS | `post_goal_message` behavior is extended, not replaced |
| Use existing patterns | ✅ PASS | Protocol scorer pattern, APScheduler connectors pattern, httpx LLM/embed pattern |
| Reference exact files | ✅ PASS | All file paths named in plan phases below |
| Additive enum values | ✅ PASS | New `WorkspaceGoalState` enum (new type, not modifying existing GoalStatus) |
| Backward-compatible APIs | ✅ PASS | `state` additive to GET responses; existing message POST returns 409 (was silent before) |
| Feature flags | ✅ PASS | `FEATURE_GOAL_AUTO_COMPLETE` flag gates scanner; decision strategies always-on (additive) |
| No cross-boundary DB access | ✅ PASS | `WorkspaceGoalDecisionRationale` in interactions; `WorkspaceAgentDecisionConfig` in workspaces; FKs mirror existing cross-BC FK already present on `workspace_goal_messages` |
| GID in correlation envelope | ✅ PASS | `goal_id` already in `CorrelationContext`; lifecycle events use `make_envelope(goal_id=goal.id)` |
| Secrets never in LLM context | ✅ PASS | Rationale records exclude API keys per FR-019; LLM calls use httpx with settings-injected URL/key |

## Project Structure

### Documentation (this feature)

```text
specs/059-workspace-goal-response/
├── plan.md              ← this file
├── spec.md
├── research.md          ← Phase 0 complete
├── data-model.md        ← Phase 1 complete
├── quickstart.md        ← Phase 1 complete
├── contracts/
│   └── rest-api.md      ← Phase 1 complete
├── checklists/
│   └── requirements.md
└── tasks.md             ← /speckit.tasks (not yet generated)
```

### Source Code — Changed Files

```text
apps/control-plane/
├── migrations/versions/
│   └── 046_workspace_goal_lifecycle_and_decision.py   [NEW]
└── src/platform/
    ├── workspaces/
    │   └── models.py                                   [MODIFY — add state cols + new model]
    ├── interactions/
    │   ├── models.py                                   [MODIFY — add DecisionRationale model]
    │   ├── service.py                                  [MODIFY — extend post_goal_message]
    │   ├── router.py                                   [MODIFY — add 5 new endpoints]
    │   ├── schemas.py                                  [MODIFY — add new request/response schemas]
    │   ├── response_decision.py                        [NEW — 5 strategies + engine]
    │   └── goal_lifecycle.py                           [NEW — lifecycle service + scanner]
    ├── common/
    │   └── config.py                                   [MODIFY — add FEATURE_GOAL_AUTO_COMPLETE flag + scanner interval setting]
    └── main.py                                         [MODIFY — register auto-completion scheduler]
```

### Tests

```text
apps/control-plane/tests/
├── unit/interactions/
│   ├── test_response_decision.py                       [NEW — strategy unit tests]
│   └── test_goal_lifecycle.py                          [NEW — lifecycle unit tests]
└── integration/interactions/
    └── test_goal_lifecycle_integration.py              [NEW — DB-backed integration tests]
```

## Phase 0: Research (Complete)

See [research.md](research.md) for all findings.

**Key decisions from research**:

1. `WorkspaceGoal` model is in `workspaces/models.py` — modify there, not `interactions/`.
2. `workspace_goal_messages.goal_id` already exists — no schema change to that table.
3. No `workspace_agent_subscriptions` table exists — create new `workspaces_agent_decision_configs` table.
4. Strategy pattern: follow `evaluation/scorers/base.py` Protocol + registry.
5. LLM calls: `httpx.AsyncClient(timeout=30.0)` to `settings.X.llm_api_url`.
6. APScheduler: follow `connectors` pattern in `main.py`.
7. Next migration: `046_workspace_goal_lifecycle_and_decision`.
8. Feature flag: `FEATURE_GOAL_AUTO_COMPLETE` (default: false).

## Phase 1: Design & Contracts (Complete)

- [data-model.md](data-model.md): Full DDL, SQLAlchemy models, state machine, strategy config schemas, Pydantic schemas.
- [contracts/rest-api.md](contracts/rest-api.md): 5 new endpoints + 1 modified endpoint, full request/response shapes.
- [quickstart.md](quickstart.md): 15 test scenarios covering lifecycle, all 5 strategies, best-match, auto-completion, rationale, concurrency, config update.

## Phase 2: Implementation Tasks

### Story Dependency Map

```
US1 (lifecycle) → US3 (COMPLETE blocks) → US5 (auto-completion)
US2 (strategies) → US4 (best-match)
US6 (rationale) — parallel with US2, required by all strategies
```

Suggested MVP: US1 (lifecycle) + US6 (rationale persistence) — delivers observable state transitions with audit trail.

---

### T001 — Alembic Migration 046

**File**: `apps/control-plane/migrations/versions/046_workspace_goal_lifecycle_and_decision.py`

Create migration using Alembic `op.execute()` blocks:
1. Create enum type `workspacegoalstate` (`ready`, `working`, `complete`)
2. `ALTER TABLE workspaces_goals ADD COLUMN state workspacegoalstate NOT NULL DEFAULT 'ready'`
3. `ALTER TABLE workspaces_goals ADD COLUMN auto_complete_timeout_seconds INTEGER NULL`
4. `ALTER TABLE workspaces_goals ADD COLUMN last_message_at TIMESTAMPTZ NULL`
5. Create indexes on `workspaces_goals (state)` and partial index for auto-complete scan
6. Create table `workspaces_agent_decision_configs` with all columns from data-model.md
7. Create table `workspace_goal_decision_rationales` with all columns from data-model.md

**Down**: DROP tables in reverse order, DROP columns, DROP enum.

---

### T002 — WorkspaceGoal Model Extension

**File**: `apps/control-plane/src/platform/workspaces/models.py`

1. Add `WorkspaceGoalState(enum.Enum)` with values `ready`, `working`, `complete`
2. Add three mapped columns to `WorkspaceGoal`: `state`, `auto_complete_timeout_seconds`, `last_message_at`
3. Add `WorkspaceAgentDecisionConfig` model class (see data-model.md for full schema)
4. Add `Workspace.agent_decision_configs` relationship backref

---

### T003 — DecisionRationale Model

**File**: `apps/control-plane/src/platform/interactions/models.py`

1. Add `WorkspaceGoalDecisionRationale` model class (see data-model.md for full schema)
2. No existing models changed

---

### T004 — Pydantic Schemas

**File**: `apps/control-plane/src/platform/interactions/schemas.py`

Add:
- `GoalStateTransitionRequest` / `GoalStateTransitionResponse`
- `AgentDecisionConfigUpsert` / `AgentDecisionConfigResponse` / `AgentDecisionConfigListResponse`
- `DecisionRationaleResponse` / `DecisionRationaleListResponse`

**File**: `apps/control-plane/src/platform/workspaces/schemas.py` (if AgentDecisionConfig schemas belong there — keep consistent with which models.py file owns the model)

---

### T005 — Settings Extension

**File**: `apps/control-plane/src/platform/common/config.py`

Add to `InteractionsSettings` (or create it if absent):
- `goal_auto_complete_scan_interval_seconds: int = 60`

Add to `PlatformSettings` feature flags section:
- `FEATURE_GOAL_AUTO_COMPLETE: bool = False`

---

### T006 — Response Decision Module

**File**: `apps/control-plane/src/platform/interactions/response_decision.py`

```python
class DecisionResult(BaseModel):
    decision: Literal["respond", "skip"]
    strategy_name: str
    score: float | None = None
    matched_terms: list[str] = []
    rationale: str = ""
    error: str | None = None

class ResponseDecisionStrategy(Protocol):
    async def decide(
        self, message: str, goal_context: str, config: dict[str, Any]
    ) -> DecisionResult: ...
```

Implement five strategy classes:

**`LLMRelevanceDecision`**:
- Build prompt: `f"Rate relevance of message to goal context. Goal: {goal_context}\nMessage: {message}\nReturn JSON: {\"score\": 0.0-1.0}"`
- POST to `settings.interactions.llm_api_url` (or `settings.llm_api_url`)
- Parse `data["score"]` → float
- Return `respond` if `score >= config["threshold"]`, else `skip`
- On httpx error / parse error: return `skip` with `error=str(exc)`

**`AllowBlocklistDecision`**:
- Tokenize message into lowercase words/phrases
- Check against `config.get("blocklist", [])` using `fnmatch`; if match → `skip`
- Check against `config.get("allowlist", [])` using `fnmatch`; if match → `respond`
- Fall through to `config.get("default", "skip")`
- `matched_terms` lists the first matched blocklist/allowlist term

**`KeywordDecision`**:
- `mode = config.get("mode", "any_of")`
- `case_sensitive = config.get("case_sensitive", False)`
- Normalize message and keywords
- `any_of`: any keyword in message → `respond`
- `all_of`: all keywords in message → `respond`
- Return `matched_terms` for all found keywords

**`EmbeddingSimilarityDecision`**:
- Call embedding API via `httpx.AsyncClient` to get query vector
- Call `AsyncQdrantClient.search_vectors(collection, query_vector, limit=1)` 
- Compare cosine score against `config["threshold"]`
- Return `respond` if score >= threshold, else `skip`
- On client error: return `skip` with error

**`BestMatchDecision`** (composite):
- Takes `subscriptions: list[WorkspaceAgentDecisionConfig]`
- Runs each agent's underlying numeric strategy to get a score
- Selects the single highest-scoring agent; all others → `skip`
- Tie-break: sort by `subscribed_at ASC` — earliest wins
- Tie-break reason recorded in rationale

**`StrategyRegistry`**:
```python
_REGISTRY: dict[str, ResponseDecisionStrategy] = {
    "llm_relevance": LLMRelevanceDecision(),
    "allow_blocklist": AllowBlocklistDecision(),
    "keyword": KeywordDecision(),
    "embedding_similarity": EmbeddingSimilarityDecision(),
    "best_match": BestMatchDecision(),
}

def get_strategy(name: str) -> ResponseDecisionStrategy:
    strategy = _REGISTRY.get(name)
    if strategy is None:
        # Unknown strategy — fail safe
        return _FailSafeSkipStrategy(error=f"Unknown strategy: {name!r}")
    return strategy
```

**`ResponseDecisionEngine`**:
```python
class ResponseDecisionEngine:
    async def evaluate_for_message(
        self,
        *,
        message_id: UUID,
        goal_id: UUID,
        workspace_id: UUID,
        message_content: str,
        goal_context: str,
        subscriptions: list[WorkspaceAgentDecisionConfig],
        session: AsyncSession,
    ) -> list[WorkspaceGoalDecisionRationale]:
        """Run all strategies, persist rationale records, return results."""
```

---

### T007 — Goal Lifecycle Module

**File**: `apps/control-plane/src/platform/interactions/goal_lifecycle.py`

```python
class GoalLifecycleService:
    async def transition_ready_to_working(
        self, *, goal: WorkspaceGoal, session: AsyncSession
    ) -> WorkspaceGoal:
        """READY → WORKING. Called atomically within post_goal_message."""

    async def transition_working_to_complete(
        self,
        *,
        goal: WorkspaceGoal,
        session: AsyncSession,
        automatic: bool = False,
        reason: str | None = None,
    ) -> WorkspaceGoal:
        """WORKING → COMPLETE. Raises 409 if already COMPLETE."""

    async def assert_accepts_messages(self, goal: WorkspaceGoal) -> None:
        """Raise GoalStateConflictError if goal is COMPLETE."""

class GoalAutoCompletionScanner:
    async def scan_and_complete_idle_goals(
        self, *, session: AsyncSession
    ) -> int:
        """
        Find WORKING goals where:
          auto_complete_timeout_seconds IS NOT NULL
          AND last_message_at + auto_complete_timeout_seconds * interval '1 second' < NOW()
          AND state = 'working'
        Apply SELECT FOR UPDATE SKIP LOCKED, transition each to COMPLETE.
        Returns count of goals transitioned.
        """
```

Kafka event published on each transition via `make_envelope()` to `workspace.goal` topic:
```json
{
  "event_type": "workspace.goal.state_changed",
  "payload": {
    "goal_id": "...",
    "workspace_id": "...",
    "previous_state": "working",
    "new_state": "complete",
    "automatic": true,
    "reason": null
  }
}
```

---

### T008 — Extend `post_goal_message` in Service

**File**: `apps/control-plane/src/platform/interactions/service.py`

Modify existing `post_goal_message(goal_id, message, participant, workspace_id)`:

1. Load goal with `SELECT FOR UPDATE` (prevents concurrent COMPLETE + post race)
2. Call `GoalLifecycleService.assert_accepts_messages(goal)` → raises `GoalStateConflictError` (409) if COMPLETE
3. If `goal.state == READY`, call `GoalLifecycleService.transition_ready_to_working(goal, session)` before inserting the message
4. Insert `WorkspaceGoalMessage` (existing logic)
5. Update `goal.last_message_at = datetime.now(UTC)` (for auto-completion timer reset)
6. Load `WorkspaceAgentDecisionConfig` for all agents subscribed to this workspace
7. Build `goal_context` string from goal title + description
8. Call `ResponseDecisionEngine.evaluate_for_message(...)` — persists rationale records, returns list
9. Emit `workspace.goal.message_posted` Kafka event (existing) with `goal_id` in correlation context
10. Commit in one transaction (message + goal state + last_message_at + rationale records)

**Error path**: If `evaluate_for_message` raises, log error but do NOT fail the message post — rationale records are best-effort (except they are persisted transactionally; if the whole transaction fails, no partial state).

---

### T009 — New Router Endpoints

**File**: `apps/control-plane/src/platform/interactions/router.py`

Add the five endpoints from [contracts/rest-api.md](contracts/rest-api.md):

1. `POST /workspaces/{workspace_id}/goals/{goal_id}/transition` — requires workspace admin role
2. `PUT /workspaces/{workspace_id}/agent-decision-configs/{agent_fqn}` — requires workspace admin role
3. `GET /workspaces/{workspace_id}/agent-decision-configs` — requires workspace admin role
4. `GET /workspaces/{workspace_id}/goals/{goal_id}/messages/{message_id}/rationale` — requires workspace admin
5. `GET /workspaces/{workspace_id}/goals/{goal_id}/rationale` — paginated, requires workspace admin

All delegates to service layer methods. Router stays thin.

---

### T010 — Auto-Completion Scheduler in main.py

**File**: `apps/control-plane/src/platform/main.py`

Add `_build_goal_auto_completion_scheduler(app: FastAPI) -> Any | None` following the same pattern as `_build_connectors_worker_scheduler`:

```python
def _build_goal_auto_completion_scheduler(app: FastAPI) -> Any | None:
    if not getattr(app.state.settings, "FEATURE_GOAL_AUTO_COMPLETE", False):
        return None
    # ... AsyncIOScheduler with interval job calling GoalAutoCompletionScanner
```

Register in `lifespan` startup/shutdown alongside existing schedulers.

---

### T011 — Unit Tests: Response Decision Strategies

**File**: `apps/control-plane/tests/unit/interactions/test_response_decision.py`

Cover:
- `KeywordDecision`: any_of match, all_of match, no match, case-insensitive, empty config → skip with error
- `AllowBlocklistDecision`: blocklist hit, allowlist hit, no match → default, blocklist beats allowlist
- `LLMRelevanceDecision`: mock httpx → respond (score≥threshold), skip (score<threshold), httpx error → skip with error
- `EmbeddingSimilarityDecision`: mock httpx + mock qdrant → respond, skip, client error → skip
- `BestMatchDecision`: 3 agents, highest wins; tie-break by subscribed_at; all skip → no responder
- `get_strategy("unknown")` → fail-safe skip strategy

---

### T012 — Unit Tests: Goal Lifecycle

**File**: `apps/control-plane/tests/unit/interactions/test_goal_lifecycle.py`

Cover:
- `transition_ready_to_working`: correct state change, emits Kafka event
- `transition_ready_to_working`: idempotent when already WORKING (or raises if goal already WORKING)
- `transition_working_to_complete`: correct, emits event with `automatic=False`
- `assert_accepts_messages`: passes for READY/WORKING, raises GoalStateConflictError for COMPLETE
- `transition_working_to_complete` when already COMPLETE → raises 409

---

### T013 — Integration Tests

**File**: `apps/control-plane/tests/integration/interactions/test_goal_lifecycle_integration.py`

Cover:
- Full flow: create goal → post first message → verify WORKING + rationale records
- Post to COMPLETE goal → verify 409 + no message stored
- Auto-completion scanner: insert WORKING goal with elapsed timeout → scanner transitions it → verify COMPLETE
- `SELECT FOR UPDATE SKIP LOCKED` under concurrent scanner replicas (two simultaneous `scan_and_complete_idle_goals` calls → exactly one transition event)
- Rationale records: UNIQUE constraint prevents duplicate (message_id, agent_fqn) entries

## Complexity Tracking

No constitution violations. All patterns follow existing codebase conventions.

## User Input Notes

The user's implementation plan mentioned:
- Steps 1–6 are fully covered by Tasks T001–T013 above
- Dependency on UPD-001 (FQN): `AllowBlocklistDecision` uses `fnmatch` for FQN-style patterns in allowlist/blocklist config — the FQN namespace format is already established in the platform (feature 051/VIII)
- Dependency on UPD-003 (GID): `CorrelationContext.goal_id` already exists (feature 052/X); lifecycle events use `make_envelope(goal_id=goal.id)`
- Estimated effort: 3 story points (~1.5 days) — consistent with 13 tasks across 2 new files + 5 modified files
