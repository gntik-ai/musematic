# Tasks: IBOR Integration and Agent Decommissioning

**Input**: `specs/056-ibor-agent-decommissioning/`
**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story this task belongs to
- Tests **not** requested in spec — no test tasks included by default

---

## Phase 1: Foundational — Migration 044

**Purpose**: Schema changes that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No implementation work can begin until migration 044 is applied.

- [X] T001 Create Alembic migration `044_ibor_and_decommission` in `apps/control-plane/migrations/versions/044_ibor_and_decommission.py` (`down_revision = "043_runtime_warm_pool_targets"`); upgrade: `ALTER TYPE registry_lifecycle_status ADD VALUE IF NOT EXISTS 'decommissioned'`, add `decommissioned_at TIMESTAMPTZ NULL`, `decommission_reason TEXT NULL`, `decommissioned_by UUID NULL` to `registry_agent_profiles`, add `source_connector_id UUID NULL` to `user_roles`, create `ibor_connectors` and `ibor_sync_runs` tables; downgrade: drop both tables and the 4 columns (enum value left in place per PostgreSQL limitation — document in migration comment)

**Checkpoint**: `alembic upgrade 044_ibor_and_decommission` succeeds; `alembic downgrade -1` succeeds — user story implementation can now begin in parallel

---

## Phase 2: User Stories 3 + 4 + 5 — Registry Decommissioning, Irreversibility, Invisibility (P1 / P1 / P2) 🎯 MVP

**Goal**: Agents can be decommissioned with a mandatory reason; running instances are stopped; the terminal state is irreversible; decommissioned agents disappear from all operational views but remain in audit/analytics queries.

**Independent Test**: Decommission an agent with two mock runtime instances → instances stopped, status terminal, reason + actor persisted, event on `registry.events`; attempt `transition(decommissioned → published)` → 409 INVALID_TRANSITION; `list_agents()` excludes the agent; `agent_execution_summary(agent_id)` still returns data.

- [X] T002 [P] [US3] Add `decommissioned = "decommissioned"` to `LifecycleStatus(StrEnum)` and add columns `decommissioned_at`, `decommission_reason`, `decommissioned_by` to `AgentProfile` in `apps/control-plane/src/platform/registry/models.py`
- [X] T003 [P] [US3] Add `AgentDecommissionRequest` (reason: str, min_length=10, max_length=2000) and `AgentDecommissionResponse` (agent_id, agent_fqn, decommissioned_at, decommission_reason, decommissioned_by, active_instances_stopped) Pydantic schemas in `apps/control-plane/src/platform/registry/schemas.py`
- [X] T004 [P] [US4] Extend `VALID_REGISTRY_TRANSITIONS` in `apps/control-plane/src/platform/registry/state_machine.py`: add `decommissioned` as a target from every non-terminal status (`draft`, `validated`, `published`, `disabled`, `deprecated`, `archived`); add `LifecycleStatus.decommissioned: set()` entry (terminal — no exits)
- [X] T005 [P] [US5] Extend list/search predicates in `apps/control-plane/src/platform/registry/repository.py` to exclude `decommissioned` in all existing places where `archived` is excluded; add `include_decommissioned: bool = False` parameter to `list_agents_by_workspace()` for admin/audit override; add `persist_decommission()` method (sets the 3 new fields, idempotent — no-op if already decommissioned)
- [X] T006 [P] [US3] Add `publish_agent_decommissioned()` helper in `apps/control-plane/src/platform/registry/events.py` following the existing `publish_agent_published()` / `publish_agent_deprecated()` envelope pattern; topic: `registry.events`; event_type: `"agent_decommissioned"`; data fields: agent_profile_id, fqn, decommissioned_by, decommissioned_at, reason, active_instance_count_at_decommission
- [X] T007 [US3] Add `decommission_agent(workspace_id, agent_id, reason, actor_id, runtime_controller)` to `AgentService` in `apps/control-plane/src/platform/registry/service.py` (depends on T002, T003, T004, T005, T006): verify actor has `workspace_owner` or `platform_admin` role (403 otherwise); validate reason length (422 otherwise); return idempotently if already decommissioned; call `runtime_controller.list_active_instances(fqn)` + parallel `stop_runtime()` for each; call `repo.persist_decommission()`; publish event; return `AgentDecommissionResponse`; also extend `transition_lifecycle()` to return 409 when current status is `decommissioned`
- [X] T008 [US3] Add `POST /api/v1/registry/{workspace_id}/agents/{agent_id}/decommission` route to `apps/control-plane/src/platform/registry/router.py` (depends on T007): auth dependency `get_current_user`, body `AgentDecommissionRequest`, response `AgentDecommissionResponse`; 200 (including idempotent re-call), 403, 404, 422

**Checkpoint**: User Stories 3, 4, and 5 fully functional — decommission endpoint works, state machine blocks re-activation, list/search excludes decommissioned agents

---

## Phase 3: User Stories 1 + 2 Foundation — IBOR Connector CRUD (P1 / P2)

**Goal**: Platform admins can create, list, read, update, and soft-delete IBOR connectors via REST; configuration persists; credential values are never exposed.

**Independent Test**: Create connector → 201 with redacted `credential_ref`; list → 200 with sorted items; update → 200; DELETE → 204 (sets `enabled=false`, history preserved); GET after DELETE → 200 with `enabled: false`; list_runs → 200 empty array; duplicate name → 409.

- [X] T009 [P] [US1] Add `IBORSourceType(StrEnum)` (`ldap`, `oidc`, `scim`), `IBORSyncMode(StrEnum)` (`pull`, `push`), `IBORSyncRunStatus(StrEnum)` (`running`, `succeeded`, `partial_success`, `failed`), `IBORConnector` SQLAlchemy model, and `IBORSyncRun` SQLAlchemy model to `apps/control-plane/src/platform/auth/models.py`; add `source_connector_id: Mapped[uuid | None]` column to `UserRole`
- [X] T010 [P] [US1] Add `IBORRoleMappingRule`, `IBORConnectorCreate`, `IBORConnectorUpdate`, `IBORConnectorResponse` (credential_ref redacted to name only), and `IBORSyncRunResponse` Pydantic schemas to `apps/control-plane/src/platform/auth/schemas.py`; `cadence_seconds` validated in [60, 86400]
- [X] T011 [US1] Add connector CRUD queries (`create_connector`, `list_connectors`, `get_connector`, `update_connector`, `soft_delete_connector`) and sync-run queries (`create_sync_run`, `update_sync_run`, `list_sync_runs`, `list_user_roles_by_connector`) to `apps/control-plane/src/platform/auth/repository.py` (depends on T009)
- [X] T012 [US1] Create `apps/control-plane/src/platform/auth/ibor_service.py` — `IBORConnectorService` with 6 methods: `create_connector`, `list_connectors`, `get_connector`, `update_connector`, `delete_connector` (soft-disable), `list_sync_runs` (paginated, max 90 default / 500 max); enforce `platform_admin` role; duplicate name → 409 (depends on T010, T011)
- [X] T013 [US1] Add `get_ibor_service` and `get_ibor_sync_service` (stub, used in T019) FastAPI dependency factories to `apps/control-plane/src/platform/auth/dependencies.py` (depends on T012)
- [X] T014 [US1] Add 6 IBOR connector endpoints to `apps/control-plane/src/platform/auth/router.py`: `POST /ibor/connectors` → 201, `GET /ibor/connectors` → 200, `GET /ibor/connectors/{id}` → 200/404, `PUT /ibor/connectors/{id}` → 200, `DELETE /ibor/connectors/{id}` → 204, `GET /ibor/connectors/{id}/runs` → 200; all require `platform_admin` (depends on T012, T013)

**Checkpoint**: IBOR connector CRUD fully functional — sync engine phases can now proceed

---

## Phase 4: User Story 1 — IBOR Pull Sync Engine (P1)

**Goal**: Scheduled and on-demand pull sync runs reconcile enterprise directory users into platform roles per connector mapping policy; per-user transactions ensure partial-success tolerance; concurrent runs rejected.

**Independent Test**: Run pull sync → roles_added == 1 for alice mapped to Platform-Admins; second run after alice removed → roles_revoked == 1; bob's manual role (source_connector_id NULL) preserved; mixed-result run → status partial_success with error_details; concurrent trigger → SyncInProgressError.

- [X] T015 [P] [US1] Add `revoke_connector_sourced_roles(connector_id, user_id)` helper to `RBACEngine` in `apps/control-plane/src/platform/auth/rbac.py`; only revokes roles where `source_connector_id == connector_id` (preserves rows where `source_connector_id IS NULL` — manual assignments per FR-003)
- [X] T016 [P] [US1] Add `publish_ibor_sync_completed(run_id, connector_id, connector_name, mode, status, duration_ms, counts)` to `apps/control-plane/src/platform/auth/events.py`; topic: `auth.events`; event_type: `"ibor_sync_completed"`
- [X] T017 [US1] Create `apps/control-plane/src/platform/auth/ibor_sync.py` — `IBORSyncService` with: `run_sync(connector_id, triggered_by)` (acquires Redis lock `ibor:sync:{connector_id}`; raises `SyncInProgressError` if held; dispatches to pull or push adapter; persists `IBORSyncRun` record; publishes event on completion); `_pull_ldap(connector)` using `ldap3` library; `_pull_oidc(connector)` via httpx (admin userinfo + groups API); `_pull_scim(connector)` via httpx (`GET /Users`, `/Groups`); `_reconcile_user_roles(connector, directory_user_groups)` — per-user transaction, first-match-wins policy evaluation, upsert/revoke via `revoke_connector_sourced_roles()` and `rbac.grant_role(source_connector_id=connector.id)`; `_resolve_credential(credential_ref)` — reads K8s Secret via existing secrets-ref pattern; run status `partial_success` when any per-user error occurs (depends on T012, T015, T016)
- [X] T018 [US1] Wire `get_ibor_sync_service` dependency factory in `apps/control-plane/src/platform/auth/dependencies.py` to return `IBORSyncService` instance (depends on T017)
- [X] T019 [US1] Add `POST /api/v1/auth/ibor/connectors/{id}/sync` endpoint to `apps/control-plane/src/platform/auth/router.py`: starts async sync; returns 202 `{run_id, connector_id, status: "running", started_at}`; returns 409 if `SyncInProgressError` (depends on T017, T018)
- [X] T020 [US1] Register `IBORSyncService` with APScheduler in `apps/control-plane/src/platform/main.py` app factory lifespan: on startup, load all enabled connectors and schedule `run_sync()` per `cadence_seconds`; on connector create/update/delete, refresh scheduler jobs (follows existing APScheduler pattern from features 022/025/034) (depends on T017)

**Checkpoint**: User Story 1 fully functional — pull sync runs on schedule and on-demand, roles reconciled, manual assignments preserved

---

## Phase 5: User Story 2 — IBOR Push Sync (P2)

**Goal**: Push-mode SCIM sync exports active agent identities and marks decommissioned agents as inactive in the enterprise IBOR endpoint for compliance reporting.

**Independent Test**: Push sync against mock SCIM endpoint → `post_user` called 3 times for active agents; decommission one agent then push → that agent's SCIM record has `active: false`.

- [X] T021 [US2] Add `_push_scim(connector, run)` method to `IBORSyncService` in `apps/control-plane/src/platform/auth/ibor_sync.py`: query `AgentProfile` for all agents in workspace (status in `{published, disabled, deprecated}` → `active: true`; status `decommissioned` → `active: false`); serialize each as SCIM User via httpx `POST {scim_endpoint}/Users`; handle per-agent errors as partial-success; extend `run_sync()` dispatch to call `_push_scim()` when `connector.sync_mode == IBORSyncMode.push` (depends on T017)

**Checkpoint**: User Stories 1 and 2 both fully functional — pull and push sync modes operational

---

## Phase 6: Tests

**Purpose**: Full coverage of all new code paths per the 21 scenarios in `quickstart.md`.

- [X] T022 [P] Create `apps/control-plane/tests/unit/auth/test_ibor_connector_crud.py`: test create → 201, duplicate name → 409, list sorted by name, get → 200/404, update → 200, delete → 204 sets enabled=false with history preserved, list_runs pagination (depends on T014)
- [X] T023 [P] Create `apps/control-plane/tests/unit/auth/test_ibor_sync_pull.py`: Scenarios 1–5 from quickstart.md — role imported on first sync (roles_added == 1), role revoked when user removed from group, concurrent trigger → SyncInProgressError, partial-success on mixed user results, OIDC and SCIM adapter paths (depends on T017)
- [X] T024 [P] Create `apps/control-plane/tests/unit/auth/test_ibor_sync_push.py`: Scenarios 6–7 from quickstart.md — push exports 3 active agents to mock SCIM, decommissioned agent pushed as active=false (depends on T021)
- [X] T025 [P] Create `apps/control-plane/tests/unit/auth/test_rbac_source_connector.py`: Scenario 3 from quickstart.md — manual role (source_connector_id=NULL) preserved across pull sync; IBOR-sourced role revoked when user leaves group (depends on T015, T017)
- [X] T026 [P] Create `apps/control-plane/tests/unit/registry/test_decommission_service.py`: Scenarios 8, 11, 12 from quickstart.md — decommission stops instances and sets terminal state, idempotency (second call returns original values), Kafka event published with correct payload (depends on T007)
- [X] T027 [P] Create `apps/control-plane/tests/unit/registry/test_decommission_state_machine.py`: Scenarios 13–15 from quickstart.md — decommissioned → published raises InvalidTransitionError, FQN reuse creates new record with new ID, decommissioned_at/reason cannot be cleared (depends on T004, T005)
- [X] T028 [P] Create `apps/control-plane/tests/unit/registry/test_decommission_visibility.py`: Scenarios 16–19 from quickstart.md — marketplace search excludes decommissioned, direct FQN lookup returns status=decommissioned + invocable=false, workflow-builder picker excludes decommissioned, analytics still returns decommissioned agent history (depends on T005, T007)
- [X] T029 [P] Create `apps/control-plane/tests/unit/registry/test_decommission_router.py`: Scenarios 9–10 from quickstart.md — non-owner actor → 403, reason < 10 chars → 422, missing agent → 404; Contract 1 and Contract 12 validation (depends on T008)
- [X] T030 [P] Create `apps/control-plane/tests/unit/migrations/test_044_roundtrip.py`: Scenario 20 from quickstart.md — upgrade applies ibor_connectors, ibor_sync_runs tables and 4 columns; downgrade removes them; `decommissioned` enum value present after both directions (depends on T001)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **US3+US4+US5 (Phase 2)**: Depends on Phase 1 (migration must be applied)
- **US1/US2 Foundation (Phase 3)**: Depends on Phase 1 (IBOR tables must exist); can run in parallel with Phase 2
- **US1 Pull Sync (Phase 4)**: Depends on Phase 3 (connector CRUD must exist)
- **US2 Push Sync (Phase 5)**: Depends on Phase 4 (`ibor_sync.py` base must exist)
- **Tests (Phase 6)**: All test tasks depend on their respective implementation phases

### User Story Dependencies

- **US3 + US4 (P1)**: Phase 1 → Phase 2 (registry decommissioning + irreversibility)
- **US5 (P2)**: Bundled with Phase 2 (same repository/service files)
- **US1 (P1)**: Phase 1 → Phase 3 → Phase 4 (connector CRUD → pull sync engine)
- **US2 (P2)**: Phase 1 → Phase 3 → Phase 4 → Phase 5 (push sync extends pull sync base)

### Parallel Opportunities Within Phases

- Phase 2: T002, T003, T004, T005, T006 are all independent (different files) — run in parallel; T007 depends on all; T008 depends on T007
- Phase 3: T009, T010 are independent; T011 depends on T009; T012 depends on T010+T011; T013, T014 depend on T012
- Phase 4: T015, T016 are independent; T017 depends on T012+T015+T016; T018, T019, T020 depend on T017
- Phase 5: T021 depends on T017 only
- Phase 6: All test tasks T022–T030 are independent of each other — run in parallel

---

## Parallel Execution Examples

```bash
# Phase 2 — launch T002–T006 in parallel (all different files):
Task: "Add decommissioned to LifecycleStatus + 3 AgentProfile columns in registry/models.py"
Task: "Add AgentDecommissionRequest/Response schemas in registry/schemas.py"
Task: "Add decommissioned transitions to state_machine.py"
Task: "Extend list predicates + persist_decommission() in registry/repository.py"
Task: "Add publish_agent_decommissioned() in registry/events.py"
# → Then T007 (service), then T008 (router)

# Phase 3 — T009, T010 in parallel:
Task: "Add IBORConnector, IBORSyncRun models to auth/models.py"
Task: "Add IBOR Pydantic schemas to auth/schemas.py"

# Phase 6 — all test files in parallel (T022–T030):
Task: "test_ibor_connector_crud.py"
Task: "test_ibor_sync_pull.py"
Task: "test_ibor_sync_push.py"
Task: "test_rbac_source_connector.py"
Task: "test_decommission_service.py"
Task: "test_decommission_state_machine.py"
Task: "test_decommission_visibility.py"
Task: "test_decommission_router.py"
Task: "test_044_roundtrip.py"
```

---

## Implementation Strategy

### MVP First (US3 + US4 only — decommissioning without IBOR)

1. Phase 1 (T001) → Foundation
2. Phase 2 (T002–T008) → Decommission endpoint functional
3. **STOP and VALIDATE**: agents can be decommissioned; state machine enforces irreversibility; list/search excludes them
4. Deliver US3+US4 independently if needed

### Full Incremental Delivery

1. T001 → Migration applied
2. T002–T008 → US3+US4+US5 complete (decommission + invisibility)
3. T009–T014 → US1/US2 CRUD foundation complete
4. T015–T020 → US1 pull sync complete
5. T021 → US2 push sync complete
6. T022–T030 → Full test coverage

---

## Summary

| Phase | Tasks | User Stories | Parallelizable |
|---|---|---|---|
| Phase 1: Migration | T001 | Foundational | No |
| Phase 2: Registry Decommission | T002–T008 | US3, US4, US5 | T002–T006 in parallel |
| Phase 3: IBOR Connector CRUD | T009–T014 | US1, US2 | T009–T010 in parallel |
| Phase 4: IBOR Pull Sync | T015–T020 | US1 | T015–T016 in parallel |
| Phase 5: IBOR Push Sync | T021 | US2 | Single task |
| Phase 6: Tests | T022–T030 | All | All 9 in parallel |
| **Total** | **30 tasks** | **5 user stories** | **18 parallelizable** |
