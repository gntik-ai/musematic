# Tasks: Zero-Trust Default Visibility

**Input**: Design documents from `specs/053-zero-trust-visibility/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/contracts.md ✅, quickstart.md ✅

**Organization**: 5 modified Python files across 5 user stories + 1 foundational phase. No schema migrations, no new endpoints, no new Kafka topics.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Foundational (Feature Flag — Blocks All Stories)

**Purpose**: Introduce `FEATURE_ZERO_TRUST_VISIBILITY` as a runtime-toggleable environment variable. This is the single blocker for all user stories.

- [X] T001 Add `VisibilitySettings(BaseSettings)` class with `zero_trust_enabled: bool = False` and env prefix `VISIBILITY_`; add `visibility: VisibilitySettings = Field(default_factory=VisibilitySettings)` to `PlatformSettings` in `apps/control-plane/src/platform/common/config.py`
- [X] T002 [P] Write unit tests for `VisibilitySettings` in `apps/control-plane/tests/unit/test_visibility_config.py`: default is `False`; `VISIBILITY_ZERO_TRUST_ENABLED=true` coerces to `True`; invalid value raises `ValidationError`; `PlatformSettings` exposes `settings.visibility.zero_trust_enabled`

**Checkpoint**: Feature flag readable from env. All user stories can now begin.

---

## Phase 2: User Story 1 — Default-deny for a newly registered agent (Priority: P1) 🎯 MVP

**Goal**: With flag ON and no grants, a freshly registered agent sees zero agents and zero tools across all registry read paths.

**Independent Test**: Enable flag. Register agent with empty `visibility_agents`/`visibility_tools`, no workspace grant. Call `list_agents()` with `requesting_agent_id` set → `items=[]`, `total=0`. Call `get_agent_by_id()` for an invisible agent → `AgentNotFoundError`. Call same with flag OFF → all agents returned.

- [X] T003 [US1] In `apps/control-plane/src/platform/registry/service.py`: change `list_agents()` predicate from `if requesting_agent_id is not None:` to `if requesting_agent_id is not None and self.settings.visibility.zero_trust_enabled:` — apply the same guard to both the items query and the count query (lines 344–393)
- [X] T004 [US1] In `apps/control-plane/src/platform/registry/service.py`: guard `_assert_agent_visible()` (lines 662–677) on `self.settings.visibility.zero_trust_enabled`; add audit event publish with `block_reason="visibility_denied"` using the existing event infrastructure when flag ON and visibility denied
- [X] T005 [P] [US1] Write US1 test scenarios in `apps/control-plane/tests/unit/registry/test_visibility_flag.py`: (a) flag ON + `requesting_agent_id` + empty patterns → `items=[]`, `total=0`; (b) flag OFF + `requesting_agent_id` → all agents returned (no regression); (c) `_assert_agent_visible()` flag ON → `AgentNotFoundError` for invisible agent; (d) `_assert_agent_visible()` flag OFF → agent returned normally

**Checkpoint**: Default-deny works. New agents start with zero visibility when flag is ON.

---

## Phase 3: User Story 2 — Per-agent FQN pattern grants (Priority: P1)

**Goal**: Agent with `visibility_agents=["finance-ops:*"]` sees exactly matching FQNs; workspace grants union with per-agent patterns; marketplace applies the same effective visibility.

**Independent Test**: Set `visibility_agents=["finance-ops:*"]`. Call `list_agents()` → only `finance-ops:*` FQNs returned. Call `search_service.search()` with `requesting_agent_id` → same filter applied. Set `visibility_agents=[]` + workspace grant `["finance-ops:*"]` → `finance-ops:*` returned via grant. Set both per-agent `["hr-ops:*"]` and workspace `["finance-ops:*"]` → union of both namespaces returned.

- [X] T006 [P] [US2] In `apps/control-plane/src/platform/marketplace/search_service.py`: extend `_get_visibility_patterns(workspace_id, requesting_agent_id=None)` — when flag ON and `requesting_agent_id` provided, call `self.registry_service.resolve_effective_visibility(requesting_agent_id, workspace_id)` and return `effective.visibility_agents or []`; when flag OFF or no agent_id, keep existing `["*"]` fallback behavior
- [X] T007 [US2] In `apps/control-plane/src/platform/marketplace/search_service.py`: thread `requesting_agent_id: UUID | None = None` through `search()`, `get_listing()`, and `_get_recommendations_for_agent()` call sites so `_get_visibility_patterns()` receives it; ensure `registry_service` is accessible (add as optional injected dependency to `SearchService.__init__` if not already present)
- [X] T008 [P] [US2] Add US2 pattern scenarios to `apps/control-plane/tests/unit/registry/test_visibility_flag.py`: (a) `visibility_agents=["finance-ops:*"]` → only matching FQNs; (b) namespace wildcard excludes other namespaces; (c) empty per-agent + workspace grant → workspace grant honored; (d) per-agent `["hr-ops:*"]` + workspace `["finance-ops:*"]` → union of both; (e) filtered `total` equals enumerable count (SC-007)
- [X] T009 [US2] Write `apps/control-plane/tests/unit/marketplace/test_marketplace_visibility.py`: (a) `_get_visibility_patterns()` flag ON + agent + patterns → union returned; (b) flag ON + agent + no patterns → `[]`; (c) flag OFF → `["*"]` fallback; (d) `_is_visible(fqn, [])` → `False` for all FQNs; (e) search result `total` reflects post-filter count

**Checkpoint**: Per-agent and workspace pattern grants work end-to-end in registry and marketplace.

---

## Phase 4: User Story 3 — Tool visibility enforced at invocation (Priority: P1)

**Goal**: Tool gateway denies any tool invocation whose `tool_fqn` does not match the caller's effective `visibility_tools` patterns when flag is ON; flag OFF behavior is unchanged.

**Independent Test**: Agent has `visibility_tools=["tools:search:*"]`. Invoke `tools:search:web` → proceeds to existing permission/purpose/budget/safety checks. Invoke `tools:finance:wire-transfer` → `GateResult(allowed=False, block_reason="visibility_denied")`. Repeat with flag OFF → both invocations proceed to existing checks (no new denial).

- [X] T010 [US3] In `apps/control-plane/src/platform/policies/gateway.py`: add `settings: PlatformSettings | None = None` optional parameter to `ToolGatewayService.__init__()`; store as `self.settings`
- [X] T011 [US3] In `apps/control-plane/src/platform/policies/gateway.py`: insert visibility pre-check as **stage 0** in `validate_tool_invocation()` before the permission check — when `self.settings` is not None and `self.settings.visibility.zero_trust_enabled` and `self.registry_service` is not None: call `resolve_effective_visibility(agent_id, workspace_id)` and check `tool_fqn` against `effective.visibility_tools` using existing `fnmatch`; if no match call `_blocked(..., block_reason="visibility_denied", ...)`
- [X] T012 [P] [US3] Write `apps/control-plane/tests/unit/policies/test_tool_gateway_visibility.py`: (a) flag ON + tool in visibility_tools → proceeds to next stage; (b) flag ON + tool NOT in patterns → `GateResult(allowed=False, block_reason="visibility_denied")`; (c) flag OFF → both tools proceed unchanged; (d) `settings=None` (legacy init without settings) → visibility check skipped; (e) Kafka publish from `_blocked()` carries `block_reason="visibility_denied"` (SC-005)

**Checkpoint**: Tool visibility is enforced at the gateway. `visibility_denied` is a distinct, auditable block reason.

---

## Phase 5: User Story 4 — Delegation to invisible peers is blocked (Priority: P2)

**Goal**: `add_participant()` rejects a delegation when the target agent's FQN is outside the requesting agent's effective `visibility_agents`; error shape is identical to "interaction not found".

**Independent Test**: Agent A with `visibility_agents=[]` attempts `add_participant(..., requesting_agent_id=A_id)` targeting `finance-ops:secret-agent` → `InteractionNotFoundError(interaction_id)`. Agent A with `visibility_agents=["finance-ops:*"]` targets `finance-ops:aml-checker` → participant created. Call without `requesting_agent_id` (legacy) → no check, participant created.

- [X] T013 [US4] In `apps/control-plane/src/platform/interactions/service.py`: add `registry_service: Any | None = None` optional parameter to `InteractionService.__init__()`; store as `self.registry_service`
- [X] T014 [US4] In `apps/control-plane/src/platform/interactions/service.py`: add `requesting_agent_id: UUID | None = None` optional parameter to `add_participant()` (lines 371–383); when `self.settings.visibility.zero_trust_enabled` and `requesting_agent_id` is not None and `self.registry_service` is not None: call `resolve_effective_visibility(requesting_agent_id, workspace_id)` and check `participant.identity` against `visibility_agents` using `fqn_matches()`; if no match raise `InteractionNotFoundError(interaction_id)`
- [X] T015 [P] [US4] Write `apps/control-plane/tests/unit/interactions/test_delegation_visibility.py`: (a) flag ON + invisible target → `InteractionNotFoundError`; (b) flag ON + visible target → `ParticipantResponse` returned; (c) flag OFF → no check, any target accepted; (d) `requesting_agent_id=None` (legacy) → no check regardless of flag; (e) error shape for denied delegation is identical to "interaction not found" (SC-006)

**Checkpoint**: No agent can delegate to a peer it cannot see, even by direct FQN reference.

---

## Phase 6: User Story 5 — Backward-compatible rollout (Priority: P2)

**Goal**: Flag OFF leaves all existing behavior unchanged; flag toggle takes effect on the next request without redeployment.

**Independent Test**: Deploy with `VISIBILITY_ZERO_TRUST_ENABLED=false`. Run all US1–US4 scenarios. Zero new denials. Toggle to `true` in memory; re-run same scenarios. Denials appear on next call. Toggle back to `false`; next call reverts.

- [X] T016 [P] [US5] Write `apps/control-plane/tests/unit/test_visibility_flag_off.py`: for each enforcement point (registry `list_agents`, `_assert_agent_visible`, gateway `validate_tool_invocation`, interaction `add_participant`, marketplace `_get_visibility_patterns`), assert that with `zero_trust_enabled=False` the behavior is identical to passing no requesting_agent_id / no visibility filter — no `AgentNotFoundError`, no `visibility_denied` result, no `InteractionNotFoundError` from the new check (SC-004)
- [X] T017 [P] [US5] Add flag-toggle test to `apps/control-plane/tests/unit/test_visibility_flag_off.py`: (a) toggle flag `False → True` mid-test, assert next call sees zero-trust enforcement; (b) toggle `True → False`, assert next call reverts to unrestricted behavior — SC-008 verified at unit-test granularity

**Checkpoint**: Rollout safety proven. Operators can deploy the code dormant and activate per workspace.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No dependencies — start immediately
- **Phase 2 (US1)**: Requires Phase 1 complete (`settings.visibility.zero_trust_enabled` must exist)
- **Phase 3 (US2)**: Requires Phase 1; independent of Phase 2 (different file: marketplace)
- **Phase 4 (US3)**: Requires Phase 1; independent of Phase 2 and 3
- **Phase 5 (US4)**: Requires Phase 1; independent of Phase 2, 3, 4
- **Phase 6 (US5)**: Requires Phases 2–5 complete (tests exercise all enforcement points)

### User Story Dependencies

- **US1 (P1)**: After Phase 1 — no other story dependency
- **US2 (P1)**: After Phase 1 — no other story dependency (T006/T007 are in marketplace, independent of registry)
- **US3 (P1)**: After Phase 1 — no other story dependency
- **US4 (P2)**: After Phase 1 — no other story dependency
- **US5 (P2)**: After all P1 stories (US1–US3) complete

### Within Each Phase

- Implementation tasks before test tasks (no TDD mandated)
- Same-file tasks are sequential (T003 → T004, T006 → T007, T010 → T011, T013 → T014)
- Test tasks marked [P] can begin independently of other test tasks

### Parallel Opportunities

```bash
# After T001 (Phase 1) completes, all of these can run in parallel:
Task: T003+T004  # registry/service.py — US1
Task: T006+T007  # marketplace/search_service.py — US2
Task: T010+T011  # policies/gateway.py — US3
Task: T013+T014  # interactions/service.py — US4

# Within US2, these two test tasks are parallel:
Task: T008  # registry pattern tests (different file from T009)
Task: T009  # marketplace tests
```

---

## Parallel Example: US1 + US2 + US3 simultaneous

```bash
# After T001 completes:
# Developer A (US1):
T003 → T004 → T005

# Developer B (US2):
T006 → T007 → T008 (parallel with T009)
               T009

# Developer C (US3):
T010 → T011 → T012
```

---

## Implementation Strategy

### MVP First (US1 — Foundational Default-deny)

1. Complete Phase 1: T001 (feature flag)
2. Complete Phase 2: T003 → T004 → T005 (registry flag gate)
3. **STOP and VALIDATE**: Run US1 test scenarios. Registry list returns empty for new agent.
4. Deploy flag OFF — no behavior change for existing deployments.

### Incremental Delivery

1. Phase 1 → Phase 2 (US1): Default-deny in registry + `_assert_agent_visible`
2. Phase 3 (US2): Per-agent patterns + marketplace fix → full discovery zero-trust
3. Phase 4 (US3): Tool gateway stage 0 → tool invocation zero-trust
4. Phase 5 (US4): Delegation check → lateral-movement gap closed
5. Phase 6 (US5): Rollout safety tests → operators can activate confidently

---

## Notes

- All 5 implementation files are independent — Phases 2–5 can be parallelized after Phase 1
- `[P]` test tasks can be written concurrently with implementation (write stub, implement, then fill test)
- Flag OFF is the default — deploying these 17 tasks to production is a zero-impact deploy
- Activation is a single env-var change: `VISIBILITY_ZERO_TRUST_ENABLED=true`
- No Alembic migrations, no new Kafka topics, no new endpoints required
