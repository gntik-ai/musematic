# Tasks: Judge/Enforcer Governance Pipeline

**Input**: Design documents from `specs/061-judge-enforcer-governance/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/rest-api.md ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US5) — required for story phases only
- Exact file paths from `plan.md` project structure

---

## Phase 1: Setup

**Purpose**: Create the governance bounded context skeleton.

- [X] T001 Create `apps/control-plane/src/platform/governance/__init__.py` and `governance/services/__init__.py` (empty init files to establish the package)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration, config, core models, events, schemas, repository, and pipeline config service — all user story phases depend on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Create migration `apps/control-plane/migrations/versions/048_governance_pipeline.py` with `revision="048_governance_pipeline"`, `down_revision="047_notifications_alerts"` — create PG enums `verdicttype`/`enforcementactiontype`, tables `governance_verdicts` and `enforcement_actions` (with ON DELETE CASCADE on `verdict_id`), table `workspace_governance_chains`, and `ALTER TABLE fleet_governance_chains ADD COLUMN verdict_to_action_mapping JSONB NOT NULL DEFAULT '{}'` (see `data-model.md` Section 1)
- [X] T003 [P] Add `GovernanceSettings` Pydantic sub-model to `apps/control-plane/src/platform/common/config.py` with fields `rate_limit_per_observer_per_minute: int = 100`, `retention_days: int = 90`, `gc_interval_hours: int = 24`, `judge_timeout_seconds: int = 30`; mount as `governance: GovernanceSettings` in `PlatformSettings`
- [X] T004 [P] Create `apps/control-plane/src/platform/governance/models.py` — `VerdictType(StrEnum)` (COMPLIANT/WARNING/VIOLATION/ESCALATE_TO_HUMAN), `ActionType(StrEnum)` (block/quarantine/notify/revoke_cert/log_and_continue), `TERMINAL_VERDICT_TYPES` frozenset, `GovernanceVerdict(Base, UUIDMixin, TimestampMixin)`, `EnforcementAction(Base, UUIDMixin, TimestampMixin)` per `data-model.md` Section 2
- [X] T005 [P] Create `apps/control-plane/src/platform/governance/exceptions.py` — `GovernanceError(PlatformError)`, `VerdictNotFoundError`, `ChainConfigError` (for role mismatch / missing agent / self-referential); follow `fleets/exceptions.py` style
- [X] T006 [P] Create `apps/control-plane/src/platform/governance/events.py` — `GovernanceEventType(StrEnum)` with `verdict_issued = "governance.verdict.issued"` and `enforcement_executed = "governance.enforcement.executed"`, `VerdictIssuedPayload(BaseModel)`, `EnforcementExecutedPayload(BaseModel)`, `publish_verdict_issued(producer, payload, correlation_ctx)`, `publish_enforcement_executed(producer, payload, correlation_ctx)`, `register_governance_event_types()` (per `data-model.md` Section 4; follow `trust/events.py` pattern)
- [X] T007 Create `apps/control-plane/src/platform/governance/schemas.py` — `VerdictListQuery`, `GovernanceVerdictRead`, `GovernanceVerdictDetail` (with nested `enforcement_action`), `EnforcementActionRead`, `EnforcementActionListQuery`, `VerdictListResponse`, `EnforcementActionListResponse` per `data-model.md` Section 3 and `contracts/rest-api.md` (depends on T004)
- [X] T008 Create `apps/control-plane/src/platform/governance/repository.py` — `GovernanceRepository(AsyncSession)` with: `create_verdict()`, `get_verdict()`, `list_verdicts(query)` (keyset pagination by `created_at`, total count), `create_enforcement_action()`, `list_enforcement_actions(query)`, `get_enforcement_action_for_verdict(verdict_id)` (idempotency check), `delete_expired_verdicts(retention_days) → int` (depends on T004, T007)
- [X] T009 Create `apps/control-plane/src/platform/governance/services/pipeline_config.py` — `ChainConfig` dataclass (`observer_fqns`, `judge_fqns`, `enforcer_fqns`, `policy_binding_ids`, `verdict_to_action_mapping`, `scope: Literal["workspace","fleet"]`); `PipelineConfigService` with `resolve_chain(fleet_id, workspace_id) → ChainConfig | None` (workspace chain wins, FR-013; returns None if neither configured) and `validate_chain_update(observer_fqns, judge_fqns, enforcer_fqns) → None` (FR-011 role check, FR-012 existence check, FR-025 self-referential check; raises `ChainConfigError` on failure) (depends on T005)

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel.

---

## Phase 3: User Story 1 — Observer signal triggers judge evaluation (Priority: P1) 🎯 MVP

**Goal**: Observer signals on `monitor.alerts` are routed through the configured governance chain to a judge agent; verdicts are persisted and published on `governance.verdict.issued`.

**Independent Test**: Configure a fleet with a governance chain (observer, judge, bound policy). Emit a test signal on `monitor.alerts` with `fleet_id` set. Verify a `governance_verdicts` row is created with the correct `verdict_type`, `policy_id`, `evidence`, `rationale`, and `source_event_id`. Verify a `governance.verdict.issued` event is published. Covers quickstart scenarios S1, S2, S4.

- [X] T010 [US1] Create `apps/control-plane/src/platform/governance/services/judge_service.py` — `JudgeService` with `process_signal(signal_envelope, fleet_id, workspace_id) → list[GovernanceVerdict]`: applies per-observer rate limit via `redis_client.check_rate_limit("governance", f"{observer_fqn}:{fleet_or_ws_id}", limit, 60_000)` (FR-024, S21); returns `[]` if `pipeline_config.resolve_chain()` returns None (FR-003 no-chain posture, S4); iterates `chain.judge_fqns` in order calling judge agent; on judge unavailable beyond `settings.governance.judge_timeout_seconds` emits ESCALATE_TO_HUMAN verdict (FR-021, S3); on missing policy emits ESCALATE_TO_HUMAN (FR-020, S5); rejects verdict missing required fields + emits ESCALATE_TO_HUMAN (FR-023); stops iteration on terminal verdict (VIOLATION/ESCALATE_TO_HUMAN — US5 layered logic, S19/S20); persists each verdict via `repo.create_verdict()`; publishes `verdict_issued` event per verdict; also implements `process_fleet_anomaly_signal(fleet_id, chain, signal) → dict` as oje_service interface for `FleetGovernanceChainService.trigger_oje_pipeline()` (depends on T004, T006, T008, T009)
- [X] T011 [US1] Create `apps/control-plane/src/platform/governance/consumers.py` — `ObserverSignalConsumer` class; consumer group `governance-observer-signals`; subscribes to `monitor.alerts` topic; deserializes `EventEnvelope`; extracts `fleet_id` and `workspace_id` from `envelope.correlation_context`; calls `judge_service.process_signal(envelope, fleet_id, workspace_id)`; discards events with no `fleet_id` AND no `workspace_id` (log + skip); follows `notifications/consumers/attention_consumer.py` pattern (depends on T010)
- [X] T012 [US1] Modify `apps/control-plane/src/platform/main.py` — in lifespan startup: call `register_governance_event_types()`, instantiate `ObserverSignalConsumer` with injected `JudgeService`, start consumer; wire `JudgeService` instance as `oje_service` in `FleetGovernanceChainService` instantiation; follow existing connector/notifications consumer wiring pattern (depends on T006, T011)
- [X] T013 [P] [US1] Create `apps/control-plane/tests/unit/governance/test_judge_service.py` — unit tests: VIOLATION verdict on threshold-breaching signal (S1), COMPLIANT verdict (S2), no-chain skip returns empty list (S4), missing policy → ESCALATE_TO_HUMAN (S5), rate limit exceeded → signal dropped (S21), judge unavailable timeout → ESCALATE_TO_HUMAN (S3)

**Checkpoint**: US1 complete — observer signals produce persisted verdicts on `governance.verdict.issued`.

---

## Phase 4: User Story 2 — Enforcer executes configured action on verdict (Priority: P1)

**Goal**: Verdicts on `governance.verdict.issued` trigger the enforcer; enforcement actions are persisted and published on `governance.enforcement.executed`.

**Independent Test**: Consume a pre-created VIOLATION verdict for a fleet with `verdict_to_action_mapping: {VIOLATION: block}`. Verify an `enforcement_actions` row is created with `action_type=block`, correct `verdict_id`, `target_agent_fqn`, and non-null `outcome`. Verify a `governance.enforcement.executed` event is published. Re-run enforcement on same verdict — verify only one `enforcement_actions` row exists. Covers quickstart S6, S9, S10.

- [X] T014 [US2] Create `apps/control-plane/src/platform/governance/services/enforcer_service.py` — `EnforcerService` with `process_verdict(verdict, chain_config) → EnforcementAction`: idempotency check via `repo.get_enforcement_action_for_verdict(verdict.id)` — return existing if found (FR-022, S10); resolve `action_type = chain_config.verdict_to_action_mapping.get(verdict.verdict_type, "log_and_continue")` (FR-010, S9); dispatch to `_execute_block()`, `_execute_quarantine()`, `_execute_notify()`, `_execute_revoke_cert()` (calls `CertificationService.revoke(cert_id, reason, actor_id)` from `trust/service.py:122`), `_execute_log_and_continue()`; target deleted edge case — catch + persist `outcome={"error":"target_not_found","target_agent_fqn":"..."}` (FR-026, S23); persist `EnforcementAction` via `repo.create_enforcement_action()`; publish `enforcement_executed` event (FR-008, FR-009) (depends on T004, T006, T008, T009)
- [X] T015 [US2] Modify `apps/control-plane/src/platform/governance/consumers.py` — append `VerdictConsumer` class (additive to file from T011); consumer group `governance-verdict-enforcer`; subscribes to `governance.verdict.issued` topic; deserializes `VerdictIssuedPayload`; loads full `GovernanceVerdict` from repo; calls `pipeline_config.resolve_chain(fleet_id, workspace_id)` to get `ChainConfig`; calls `enforcer_service.process_verdict(verdict, chain_config)`; handles enforcer unavailable — log + defer retry (depends on T014)
- [X] T016 [US2] Modify `apps/control-plane/src/platform/main.py` — in lifespan startup: instantiate `VerdictConsumer` with injected `EnforcerService`, start consumer; add APScheduler job `governance-retention-gc` with interval `settings.governance.gc_interval_hours * 3600` calling `_run_governance_retention_gc()` helper (depends on T008, T015)
- [X] T017 [P] [US2] Create `apps/control-plane/tests/unit/governance/test_enforcer_service.py` — unit tests: block action persisted with correct fields (S6), notify action (S7), revoke_cert calls CertificationService.revoke() (S8), default log_and_continue when no mapping (S9), idempotency — second call returns existing action (S10), target deleted → outcome notes missing target (S23)

**Checkpoint**: US2 complete — verdicts produce persisted enforcement actions on `governance.enforcement.executed`. Full US1+US2 pipeline is operational.

---

## Phase 5: User Story 3 — Admin configures governance chain per fleet and workspace (Priority: P2)

**Goal**: Workspace-level governance chains are configurable via REST; fleet chains gain `verdict_to_action_mapping`; chain validation rejects role mismatches, unknown agents, and self-referential loops.

**Independent Test**: (a) `PUT /api/v1/workspaces/{w}/governance-chain` with valid observer/judge/enforcer FQNs + `verdict_to_action_mapping` → 200, chain persisted, `is_current=true`. (b) Same PUT with a non-judge FQN in `judge_fqns` → 422 role mismatch. (c) `PUT /api/v1/fleets/{f}/governance-chain` with new `verdict_to_action_mapping` field → 200. Covers quickstart S11, S12, S13, S14.

- [X] T018 [P] [US3] Modify `apps/control-plane/src/platform/workspaces/models.py` — append `WorkspaceGovernanceChain(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin)` class with all fields from `data-model.md` Section 2; do NOT modify any existing class in the file
- [X] T019 [P] [US3] Modify `apps/control-plane/src/platform/fleets/models.py` — append `verdict_to_action_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))` to `FleetGovernanceChain` class body (after `is_default` field, ~line 222); do NOT modify any other field
- [X] T020 [P] [US3] Modify `apps/control-plane/src/platform/workspaces/schemas.py` — append `WorkspaceGovernanceChainUpdate` (with FQN list normalizing validator), `WorkspaceGovernanceChainResponse`, `WorkspaceGovernanceChainListResponse` per `data-model.md` Section 3; do NOT modify existing schemas
- [X] T021 [P] [US3] Modify `apps/control-plane/src/platform/fleets/schemas.py` — in `FleetGovernanceChainUpdate` (line 166) add `verdict_to_action_mapping: dict[str, str] = Field(default_factory=dict)`; in `FleetGovernanceChainResponse` (line 187) add `verdict_to_action_mapping: dict[str, str]`; both are additive — existing callers unaffected (Brownfield Rule 7)
- [X] T022 [US3] Create `apps/control-plane/src/platform/workspaces/governance.py` — `WorkspaceGovernanceChainRepository` (async SQLAlchemy: `get_current()`, `create_version()`, `list_history()`); `WorkspaceGovernanceChainService` mirroring `fleets/governance.py` with `get_chain()`, `update_chain()` (calls `pipeline_config.validate_chain_update()` before persisting), `get_chain_history()`, `create_default_chain()` (depends on T018, T020, T009)
- [X] T023 [US3] Modify `apps/control-plane/src/platform/fleets/governance.py` — in `update_chain()`: pass `verdict_to_action_mapping=request.verdict_to_action_mapping` to `FleetGovernanceChain(...)` constructor; add `pipeline_config.validate_chain_update(request.observer_fqns, request.judge_fqns, request.enforcer_fqns)` call before creating the chain record; no other changes (depends on T019, T021, T009)
- [X] T024 [US3] Modify `apps/control-plane/src/platform/workspaces/router.py` — add three endpoints (additive; existing endpoints unchanged): `GET /{workspace_id}/governance-chain → WorkspaceGovernanceChainResponse`, `PUT /{workspace_id}/governance-chain → WorkspaceGovernanceChainResponse`, `GET /{workspace_id}/governance-chain/history → WorkspaceGovernanceChainListResponse`; use `WorkspaceGovernanceChainService` dependency; follow `fleets/router.py:311-341` pattern (depends on T022)
- [X] T025 [P] [US3] Create `apps/control-plane/tests/unit/governance/test_pipeline_config.py` — unit tests: valid chain accepted, role mismatch raises `ChainConfigError` (S12), unknown agent raises `ChainConfigError` (S13), self-referential agent raises `ChainConfigError` (S22), workspace chain override (S14)

**Checkpoint**: US3 complete — fleet and workspace chains are configurable with validation.

---

## Phase 6: User Story 4 — Audit trail query for verdicts and enforcement actions (Priority: P2)

**Goal**: Compliance users with AUDITOR role can query, filter, and retrieve full detail of governance verdicts and enforcement actions.

**Independent Test**: Generate verdicts and enforcement actions (COMPLIANT, WARNING+notify, VIOLATION+block). AUDITOR user calls `GET /governance/verdicts?fleet_id=...` → all verdicts returned with correct fields. Calls `GET /governance/verdicts/{id}` → full detail including nested `enforcement_action`. Non-AUDITOR user → 403. Covers quickstart S15, S16, S17.

- [X] T026 [P] [US4] Create `apps/control-plane/src/platform/governance/dependencies.py` — `get_governance_service(db: AsyncSession = Depends(get_db), settings: PlatformSettings = Depends(get_settings)) → GovernanceService`; `GovernanceService` thin façade wrapping `GovernanceRepository` with `list_verdicts(query)`, `get_verdict(verdict_id)`, `list_enforcement_actions(query)` (depends on T007, T008)
- [X] T027 [US4] Create `apps/control-plane/src/platform/governance/router.py` — `router = APIRouter(prefix="/governance", tags=["governance"])`; three endpoints: `GET /verdicts → VerdictListResponse` (AUDITOR role check, FR-017/FR-018, S15), `GET /verdicts/{verdict_id} → GovernanceVerdictDetail` (AUDITOR, S16), `GET /enforcement-actions → EnforcementActionListResponse` (AUDITOR); all use `get_governance_service()` + `require_role(RoleType.AUDITOR)` dependency; per `contracts/rest-api.md` (depends on T026)
- [X] T028 [US4] Modify `apps/control-plane/src/platform/main.py` — register `governance.router` in `app.include_router()` with prefix `/api/v1`; place after notifications router registration (depends on T027)
- [X] T029 [P] [US4] Create `apps/control-plane/tests/integration/governance/test_governance_api.py` — integration tests: list verdicts with fleet_id filter returns correct records (S15), GET verdict detail includes nested enforcement_action (S16), VIEWER role denied with 403 (S17), retention GC removes verdict + cascades enforcement action deletion (S18)

**Checkpoint**: US4 complete — audit queries operational with AUDITOR authorization.

---

## Phase 7: User Story 5 — Layered judge chain (Priority: P3)

**Goal**: Fleet chains with multiple judge FQNs route observer signals through judges in order; terminal verdicts (VIOLATION/ESCALATE_TO_HUMAN) stop the chain; intermediate verdicts (COMPLIANT/WARNING) allow the next judge to run.

**Independent Test**: Configure fleet with two judge FQNs [J1, J2]. Emit signal → J1 returns COMPLIANT → J2 runs → two verdicts persisted. Emit signal → J1 returns VIOLATION → J2 does not run → one verdict persisted. Covers quickstart S19, S20.

**Note**: The layered chain iteration logic was implemented in T010 (`judge_service.py`). This phase adds targeted tests and verifies the behavior end-to-end.

- [X] T030 [US5] Create `apps/control-plane/tests/unit/governance/test_judge_service_layered.py` — unit tests for layered chain: first judge COMPLIANT → second judge runs, two verdicts persisted (S19); first judge VIOLATION → second judge skipped, one verdict persisted (S20); first judge ESCALATE_TO_HUMAN → second judge skipped (quickstart US5 scenario 3)

**Checkpoint**: US5 complete — layered judge chains route correctly.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Wire remaining integration points and validate the complete pipeline end-to-end.

- [X] T031 Verify `apps/control-plane/src/platform/fleets/governance.py` `trigger_oje_pipeline()` wiring: confirm `JudgeService` is passed as `oje_service` in `main.py` and that `process_fleet_anomaly_signal()` is exercised by an existing test or add a targeted call in `test_judge_service.py`
- [X] T032 [P] Verify `apps/control-plane/migrations/versions/048_governance_pipeline.py` roundtrip: run `make migrate` and `make migrate-rollback` locally; confirm no errors on upgrade and downgrade

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundation)**: Depends on Phase 1 — BLOCKS all user story phases
- **Phase 3 (US1)**: Depends on Phase 2
- **Phase 4 (US2)**: Depends on Phase 2; shares consumer file with US1 (T015 is additive to T011's file) — start after T011 is complete
- **Phase 5 (US3)**: Depends on Phase 2 only — can run in parallel with US1/US2 (different files)
- **Phase 6 (US4)**: Depends on Phase 2 only for router/deps files; for integration tests, depends on US1+US2 having seeded verdict/action data
- **Phase 7 (US5)**: Depends on T010 (judge_service) from Phase 3
- **Phase 8 (Polish)**: Depends on all phases complete

### User Story Dependencies

- **US1 (P1)**: After Foundation — no story dependencies
- **US2 (P1)**: After Foundation; T015 adds to consumers.py file created in T011 — complete T011 first
- **US3 (P2)**: After Foundation — independent of US1/US2 (different bounded contexts)
- **US4 (P2)**: After Foundation — router/deps independent; integration tests need data from US1+US2
- **US5 (P3)**: After T010 from US1 (layered logic lives in judge_service)

### Within Each User Story

- Models → Repository → Service → Consumer → Router
- T004 (models) → T008 (repo) → T010 (judge service) → T011 (consumer)
- T004 (models) → T008 (repo) → T014 (enforcer service) → T015 (consumer)
- T018/T019 (models) → T022/T023 (services) → T024 (router)

### Parallel Opportunities

- T003, T004, T005, T006 can all run in parallel (different files, no inter-dependencies within Foundation)
- T018, T019, T020, T021 can all run in parallel (different files)
- T013, T025, T026, T029 can all run in parallel (tests/deps, different files)
- US3 (T018–T025) can run entirely in parallel with US1 (T010–T013) and US2 (T014–T017) since they touch different bounded contexts

---

## Parallel Example: Foundation Phase

```bash
# Launch all parallel foundation tasks together:
Task T003: "Add GovernanceSettings to common/config.py"
Task T004: "Create governance/models.py"
Task T005: "Create governance/exceptions.py"
Task T006: "Create governance/events.py"
# Then sequentially:
Task T007: "Create governance/schemas.py" (after T004)
Task T008: "Create governance/repository.py" (after T004, T007)
Task T009: "Create pipeline_config.py" (after T005)
```

## Parallel Example: US3 alongside US1

```bash
# While US1 is being implemented (T010-T013):
Task T018: "Append WorkspaceGovernanceChain to workspaces/models.py"
Task T019: "Add verdict_to_action_mapping to fleets/models.py"
Task T020: "Append workspace chain schemas to workspaces/schemas.py"
Task T021: "Add verdict_to_action_mapping to fleets/schemas.py"
# Then after T018, T020:
Task T022: "Create workspaces/governance.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2 — Full Pipeline)

1. Complete Phase 1 (Setup) + Phase 2 (Foundation)
2. Complete Phase 3 (US1 — judge evaluation + verdict issuance)
3. Complete Phase 4 (US2 — enforcement execution)
4. **STOP and VALIDATE**: Emit a test signal → verify verdict → verify enforcement action → verify both Kafka events published
5. Full Observer→Judge→Enforcer pipeline is operational

### Incremental Delivery

1. Foundation → US1 (judge pipeline) → deploy (verdicts appearing in DB + Kafka)
2. US2 (enforcer) → deploy (enforcement actions completing the loop)
3. US3 (chain config) → deploy (workspace chains + fleet chain mapping live)
4. US4 (audit queries) → deploy (compliance surface live)
5. US5 (layered judges) → deploy (multi-judge chains usable)

### Parallel Team Strategy

With two developers after Foundation:
- Developer A: US1 (T010–T013) + US2 (T014–T017) — pipeline services
- Developer B: US3 (T018–T025) — chain config + workspace governance

---

## Notes

- [P] tasks = different files, no intra-phase dependencies
- [Story] label maps task to specific user story for traceability
- `FleetGovernanceChain` + `FleetGovernanceChainService` already exist — T019/T021/T023 are additive modifications only (Brownfield Rule 1)
- `AgentRoleType.judge` and `AgentRoleType.enforcer` already exist in `registry/models.py:31-32` — no enum migration needed
- T010 (`judge_service.py`) already includes US5 layered chain logic; T030 is a test-only task
- `EnforcementAction.verdict_id` FK uses `ON DELETE CASCADE` — retention GC (T016) only needs to delete verdicts; actions cascade automatically (SC-010)
- All integration points use in-process service calls (CertificationService for revoke_cert) — no new cross-process calls
