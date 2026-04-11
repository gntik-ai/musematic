# Tasks: Workspaces Bounded Context

**Input**: Design documents from `specs/018-workspaces-bounded-context/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/workspaces-api.md ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story — each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US6)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package stubs, Alembic migration, settings additions.

- [x] T001 Create `apps/control-plane/src/platform/workspaces/` package: `__init__.py`, `models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`, `state_machine.py`, `consumer.py` — all as empty stubs with correct module docstrings
- [x] T002 [P] Create Alembic migration `apps/control-plane/migrations/versions/004_workspaces_tables.py` — 5 tables: `workspaces_workspaces` (id, name, description, status, owner_id, is_default, created_at, updated_at, deleted_at), `workspaces_memberships` (id, workspace_id FK, user_id, role, created_at, updated_at), `workspaces_goals` (id, workspace_id FK, title, description, status, gid UNIQUE, created_by, created_at, updated_at), `workspaces_settings` (id, workspace_id FK UNIQUE, subscribed_agents TEXT[], subscribed_fleets UUID[], subscribed_policies UUID[], subscribed_connectors UUID[], updated_at), `workspaces_visibility_grants` (id, workspace_id FK UNIQUE, visibility_agents TEXT[], visibility_tools TEXT[], updated_at); include all indexes: `ix_workspaces_owner_id`, `ix_workspaces_owner_name_status` (unique partial, status != 'deleted'), `ix_memberships_user_id`, `uq_workspace_user`, `uq_goal_gid`, `ix_goals_workspace_status`
- [x] T003 [P] Add workspaces settings to `apps/control-plane/src/platform/common/config.py`: `WORKSPACES_DEFAULT_NAME_TEMPLATE: str = "{display_name}'s Workspace"` and `WORKSPACES_DEFAULT_LIMIT: int = 0`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared enums, exceptions, and base schemas used by all user story phases.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 [P] Implement enums in `apps/control-plane/src/platform/workspaces/models.py`: `WorkspaceStatus` (active, archived, deleted), `WorkspaceRole` (owner, admin, member, viewer), `GoalStatus` (open, in_progress, completed, cancelled)
- [x] T005 [P] Implement `apps/control-plane/src/platform/workspaces/exceptions.py`: `WorkspacesError(PlatformError)` base; subclasses: `WorkspaceNotFoundError` (404), `WorkspaceLimitError` (403), `WorkspaceNameConflictError` (409), `WorkspaceAuthorizationError` (403), `LastOwnerError` (409), `MemberAlreadyExistsError` (409), `MemberNotFoundError` (404), `InvalidGoalTransitionError` (409), `GoalNotFoundError` (404)
- [x] T006 [P] Implement `apps/control-plane/src/platform/workspaces/state_machine.py`: `VALID_GOAL_TRANSITIONS: dict[GoalStatus, set[GoalStatus]]` — open→{in_progress, cancelled}; in_progress→{completed, cancelled}; completed→{}; cancelled→{}; `async def validate_goal_transition(current: GoalStatus, target: GoalStatus) -> None` raises `InvalidGoalTransitionError` if invalid

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Workspace CRUD and Data Isolation (Priority: P1) 🎯 MVP

**Goal**: Create, retrieve, list, update, archive, restore, and delete workspaces with full data isolation between workspace owners.

**Independent Test**: Create a workspace → get it by ID → update name → list (verify appears) → archive → list (verify absent from active listing) → restore → list (verify reappears). Create workspace as user B, verify user A cannot see it.

- [x] T007 [P] [US1] Implement `Workspace` SQLAlchemy model in `apps/control-plane/src/platform/workspaces/models.py`: inherits `Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin`; columns: `name: Mapped[str]`, `description: Mapped[str | None]`, `status: Mapped[WorkspaceStatus]`, `owner_id: Mapped[uuid.UUID]`, `is_default: Mapped[bool] = mapped_column(default=False)`; relationships to Membership, WorkspaceGoal, WorkspaceSettings, WorkspaceVisibilityGrant; table args with indexes defined in T002
- [x] T008 [P] [US1] Implement workspace Pydantic schemas in `apps/control-plane/src/platform/workspaces/schemas.py`: `CreateWorkspaceRequest` (name: str 1–100, description: str | None max 500), `UpdateWorkspaceRequest` (name: str | None 1–100, description: str | None), `WorkspaceResponse` (id, name, description, status, owner_id, is_default, created_at, updated_at), `WorkspaceListResponse` (items: list[WorkspaceResponse], total, page, page_size)
- [x] T009 [P] [US1] Implement workspace repository methods in `apps/control-plane/src/platform/workspaces/repository.py`: `WorkspacesRepository` class with `async def create_workspace(...)`, `async def get_workspace_by_id(workspace_id, user_id)` (returns None if not member), `async def list_workspaces_for_user(user_id, page, page_size, status_filter)`, `async def update_workspace(workspace_id, **fields)`, `async def archive_workspace(workspace_id)`, `async def restore_workspace(workspace_id)`, `async def delete_workspace(workspace_id)`, `async def count_owned_workspaces(owner_id)` — all use `AsyncSession`, all filter by workspace membership or owner_id for isolation
- [x] T010 [P] [US1] Implement workspace events in `apps/control-plane/src/platform/workspaces/events.py`: payload dataclasses and `async def publish_workspace_created(...)`, `publish_workspace_updated(...)`, `publish_workspace_archived(...)`, `publish_workspace_restored(...)`, `publish_workspace_deleted(...)` — all use `EventEnvelope` from `common.events.envelope`, topic `workspaces.events`, key `workspace_id`
- [x] T011 [US1] Implement workspace CRUD service methods in `apps/control-plane/src/platform/workspaces/service.py`: `WorkspacesService` class with `async def create_workspace(user_id, request)` (checks workspace limit via `accounts_service.get_user_workspace_limit`, checks name uniqueness, creates workspace + owner membership + default settings, emits event), `async def get_workspace(workspace_id, user_id)`, `async def list_workspaces(user_id, page, page_size, status_filter)`, `async def update_workspace(workspace_id, user_id, request)` (requires admin/owner role), `async def archive_workspace(workspace_id, user_id)` (requires owner), `async def restore_workspace(workspace_id, user_id)` (requires owner), `async def delete_workspace(workspace_id, user_id)` (requires owner, workspace must be archived first)
- [x] T012 [US1] Implement workspace CRUD router in `apps/control-plane/src/platform/workspaces/router.py`: 7 endpoints — `POST /`, `GET /`, `GET /{workspace_id}`, `PATCH /{workspace_id}`, `POST /{workspace_id}/archive`, `POST /{workspace_id}/restore`, `DELETE /{workspace_id}`; all thin — delegate to service; use `get_current_user` dependency from `common.dependencies`
- [x] T013 [US1] Write unit tests `apps/control-plane/tests/unit/test_workspaces_service.py` covering: create workspace (success, name conflict, limit exceeded), get (success, not member returns 404), list (pagination, status filter), update (success, forbidden for non-admin), archive/restore (success, already archived conflict), delete (requires archived first)
- [x] T014 [US1] Write integration test `apps/control-plane/tests/integration/test_workspace_crud_flow.py`: full create → update → archive → restore → delete flow; data isolation test (user B cannot access user A's workspace)

**Checkpoint**: US1 fully functional — workspace CRUD with data isolation

---

## Phase 4: User Story 2 — Membership Management (Priority: P1)

**Goal**: Add members with roles, change roles, remove members, list members; enforce last-owner guard and role-based authorization.

**Independent Test**: Add member as "member" role → list members (both appear) → change to "admin" → remove → list (only owner). Attempt to remove last owner → 409. Non-member access → 404.

- [x] T015 [P] [US2] Add `Membership` SQLAlchemy model to `apps/control-plane/src/platform/workspaces/models.py`: columns `workspace_id: Mapped[uuid.UUID]`, `user_id: Mapped[uuid.UUID]`, `role: Mapped[WorkspaceRole]`; `UniqueConstraint("workspace_id", "user_id")`, `Index("ix_memberships_user_id", "user_id")`; relationship back to Workspace
- [x] T016 [P] [US2] Add membership Pydantic schemas to `apps/control-plane/src/platform/workspaces/schemas.py`: `AddMemberRequest` (user_id: UUID, role: WorkspaceRole — validator rejects `owner`), `ChangeMemberRoleRequest` (role: WorkspaceRole — validator rejects `owner`), `MembershipResponse` (id, workspace_id, user_id, role, created_at), `MemberListResponse` (items: list[MembershipResponse], total)
- [x] T017 [P] [US2] Add membership repository methods to `apps/control-plane/src/platform/workspaces/repository.py`: `async def add_member(workspace_id, user_id, role)`, `async def get_membership(workspace_id, user_id) → Membership | None`, `async def list_members(workspace_id, page, page_size)`, `async def change_member_role(workspace_id, user_id, new_role)`, `async def remove_member(workspace_id, user_id)`, `async def count_owners(workspace_id) → int`
- [x] T018 [P] [US2] Add membership events to `apps/control-plane/src/platform/workspaces/events.py`: `publish_membership_added(workspace_id, user_id, role)`, `publish_membership_role_changed(workspace_id, user_id, old_role, new_role)`, `publish_membership_removed(workspace_id, user_id)` — topic `workspaces.events`
- [x] T019 [US2] Add membership service methods to `apps/control-plane/src/platform/workspaces/service.py`: `async def add_member(workspace_id, requester_id, request)` (requires admin/owner, rejects if already member), `async def list_members(workspace_id, requester_id, page, page_size)` (requires any role), `async def change_member_role(workspace_id, requester_id, target_user_id, request)` (requires admin/owner; admin cannot assign owner or demote owner), `async def remove_member(workspace_id, requester_id, target_user_id)` (requires admin/owner; last-owner guard via `count_owners`)
- [x] T020 [US2] Add membership router endpoints to `apps/control-plane/src/platform/workspaces/router.py`: `POST /{workspace_id}/members`, `GET /{workspace_id}/members`, `PATCH /{workspace_id}/members/{user_id}`, `DELETE /{workspace_id}/members/{user_id}`
- [x] T021 [US2] Write unit tests `apps/control-plane/tests/unit/test_workspaces_service.py` (membership section): add (success, already exists, role=owner rejected), change role (success, admin→owner rejected, demote owner rejected), remove (success, last owner rejected), list (pagination)
- [x] T022 [US2] Write integration test `apps/control-plane/tests/integration/test_membership_flow.py`: add → change role → remove + last-owner guard; verify events emitted for each change

**Checkpoint**: US1 + US2 functional — workspaces with full membership management

---

## Phase 5: User Story 3 — Default Workspace Provisioning (Priority: P1)

**Goal**: Automatically create a default workspace when `accounts.user.activated` Kafka event is received; operation must be idempotent.

**Independent Test**: Send `accounts.user.activated` Kafka message → workspace created with `is_default=true` → resend same message → no duplicate workspace created.

- [x] T023 [P] [US3] Add `async def create_default_workspace(user_id: UUID, display_name: str)` to `apps/control-plane/src/platform/workspaces/service.py`: checks if workspace with `owner_id=user_id, is_default=True` already exists (idempotency guard); if not, creates workspace with `name = settings.WORKSPACES_DEFAULT_NAME_TEMPLATE.format(display_name=display_name)`, `is_default=True`; adds owner membership; creates default settings; emits `workspace.created` event with `is_default=True` in payload
- [x] T024 [US3] Implement `apps/control-plane/src/platform/workspaces/consumer.py`: async Kafka consumer class `WorkspacesConsumer` subscribed to `accounts.events` topic; filters for `event_type == "accounts.user.activated"`; extracts `user_id` and `display_name` from event payload; calls `workspaces_service.create_default_workspace(user_id, display_name)`; uses `CorrelationContext` from event envelope; handles errors with logging (does not propagate — consumer must not crash on provisioning failure)
- [x] T025 [US3] Register `WorkspacesConsumer` in the app lifespan in `apps/control-plane/src/platform/main.py` (or app factory) — start consumer on startup, graceful shutdown on lifespan exit
- [x] T026 [US3] Write integration test `apps/control-plane/tests/integration/test_default_provisioning.py`: mock Kafka message delivery; verify workspace created with `is_default=True`; send same message again; verify no duplicate (idempotency); verify `workspace.created` event emitted with `is_default=True`

**Checkpoint**: US1 + US2 + US3 functional — new users get automatic default workspace

---

## Phase 6: User Story 4 — Workspace Goals (Priority: P2)

**Goal**: Create goals with auto-generated GID, list goals, update goal status with state machine enforcement.

**Independent Test**: Create goal → verify GID assigned, status=open → update to in_progress → update to completed → attempt to update completed goal → 409. Create, then cancel — verify cancelled is terminal.

- [x] T027 [P] [US4] Add `WorkspaceGoal` SQLAlchemy model to `apps/control-plane/src/platform/workspaces/models.py`: columns `workspace_id: Mapped[uuid.UUID]`, `title: Mapped[str]`, `description: Mapped[str | None]`, `status: Mapped[GoalStatus]`, `gid: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)`, `created_by: Mapped[uuid.UUID]`; `UniqueConstraint("gid")`, indexes `ix_goals_workspace_id`, `ix_goals_workspace_status`; relationship back to Workspace
- [x] T028 [P] [US4] Add goal Pydantic schemas to `apps/control-plane/src/platform/workspaces/schemas.py`: `CreateGoalRequest` (title: str 1–200, description: str | None max 2000), `UpdateGoalStatusRequest` (status: GoalStatus), `GoalResponse` (id, workspace_id, gid, title, description, status, created_by, created_at, updated_at), `GoalListResponse` (items: list[GoalResponse], total)
- [x] T029 [P] [US4] Add goal repository methods to `apps/control-plane/src/platform/workspaces/repository.py`: `async def create_goal(workspace_id, title, description, created_by) → WorkspaceGoal`, `async def get_goal(workspace_id, goal_id) → WorkspaceGoal | None`, `async def list_goals(workspace_id, page, page_size, status_filter) → tuple[list[WorkspaceGoal], int]`, `async def update_goal_status(workspace_id, goal_id, new_status) → WorkspaceGoal`
- [x] T030 [P] [US4] Add goal events to `apps/control-plane/src/platform/workspaces/events.py`: `publish_goal_created(workspace_id, gid, title, created_by)`, `publish_goal_status_changed(workspace_id, gid, old_status, new_status)` — both emit on `workspaces.events` with `gid` in payload for CorrelationContext
- [x] T031 [US4] Add goal service methods to `apps/control-plane/src/platform/workspaces/service.py`: `async def create_goal(workspace_id, requester_id, request)` (requires member role or above; generates GID via `uuid.uuid4()`), `async def get_goal(workspace_id, requester_id, goal_id)` (any role), `async def list_goals(workspace_id, requester_id, page, page_size, status_filter)` (any role), `async def update_goal_status(workspace_id, requester_id, goal_id, request)` (requires member or above; calls `validate_goal_transition`)
- [x] T032 [US4] Add goal router endpoints to `apps/control-plane/src/platform/workspaces/router.py`: `POST /{workspace_id}/goals`, `GET /{workspace_id}/goals`, `GET /{workspace_id}/goals/{goal_id}`, `PATCH /{workspace_id}/goals/{goal_id}`
- [x] T033 [US4] Write unit tests `apps/control-plane/tests/unit/test_workspaces_state_machine.py`: all valid transitions pass; all invalid transitions raise `InvalidGoalTransitionError`; terminal states (completed, cancelled) reject any change
- [x] T034 [US4] Write integration test `apps/control-plane/tests/integration/test_goal_flow.py`: create → update status → complete; create → cancel; attempt invalid transition; verify GID in events

**Checkpoint**: US1–US4 functional — workspaces with goals and GID correlation

---

## Phase 7: User Story 5 — Workspace Visibility Grants (Priority: P2)

**Goal**: Set, retrieve, update, and delete workspace-wide visibility grants (FQN pattern lists); expose internal service interface for registry context.

**Independent Test**: Set visibility grant with agent+tool patterns → get grant → verify patterns stored → update with new patterns → verify replaced → delete → get returns 404 → internal service interface returns None for workspace with no grant.

- [x] T035 [P] [US5] Add `WorkspaceVisibilityGrant` SQLAlchemy model to `apps/control-plane/src/platform/workspaces/models.py`: columns `workspace_id: Mapped[uuid.UUID]` (unique FK), `visibility_agents: Mapped[list[str]] = mapped_column(ARRAY(Text))`, `visibility_tools: Mapped[list[str]] = mapped_column(ARRAY(Text))`; `UniqueConstraint("workspace_id")`; relationship back to Workspace
- [x] T036 [P] [US5] Add visibility grant Pydantic schemas to `apps/control-plane/src/platform/workspaces/schemas.py`: `SetVisibilityGrantRequest` (visibility_agents: list[str], visibility_tools: list[str]), `VisibilityGrantResponse` (workspace_id, visibility_agents, visibility_tools, updated_at)
- [x] T037 [P] [US5] Add visibility grant repository methods to `apps/control-plane/src/platform/workspaces/repository.py`: `async def set_visibility_grant(workspace_id, visibility_agents, visibility_tools) → WorkspaceVisibilityGrant` (upsert), `async def get_visibility_grant(workspace_id) → WorkspaceVisibilityGrant | None`, `async def delete_visibility_grant(workspace_id) → bool`
- [x] T038 [P] [US5] Add visibility grant events to `apps/control-plane/src/platform/workspaces/events.py`: `publish_visibility_grant_updated(workspace_id, visibility_agents, visibility_tools)` — topic `workspaces.events`
- [x] T039 [US5] Add visibility grant service methods to `apps/control-plane/src/platform/workspaces/service.py`: `async def set_visibility_grant(workspace_id, requester_id, request)` (requires admin/owner), `async def get_visibility_grant(workspace_id, requester_id)` (any role), `async def delete_visibility_grant(workspace_id, requester_id)` (requires admin/owner), `async def get_workspace_visibility_grant(workspace_id) → VisibilityGrantResponse | None` (internal interface — no auth check, for registry context use)
- [x] T040 [US5] Add visibility grant router endpoints to `apps/control-plane/src/platform/workspaces/router.py`: `PUT /{workspace_id}/visibility`, `GET /{workspace_id}/visibility`, `DELETE /{workspace_id}/visibility`

**Checkpoint**: US1–US5 functional — visibility grants available for agent discovery

---

## Phase 8: User Story 6 — Workspace Limits and Settings (Priority: P3)

**Goal**: Enforce per-user workspace limits; store and retrieve workspace super-context subscription settings.

**Independent Test**: Set user limit to 2 → create 2 workspaces (succeed) → create 3rd (403 limit error). Update settings with subscribed agents/fleets/policies/connectors → get settings → verify all lists returned. Set limit to 0 → create 3rd workspace (succeed).

- [x] T041 [P] [US6] Add `WorkspaceSettings` SQLAlchemy model to `apps/control-plane/src/platform/workspaces/models.py`: columns `workspace_id: Mapped[uuid.UUID]` (unique FK), `subscribed_agents: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)`, `subscribed_fleets: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID), default=list)`, `subscribed_policies: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID), default=list)`, `subscribed_connectors: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID), default=list)`; relationship back to Workspace
- [x] T042 [P] [US6] Add settings Pydantic schemas to `apps/control-plane/src/platform/workspaces/schemas.py`: `UpdateSettingsRequest` (subscribed_agents: list[str] | None, subscribed_fleets: list[UUID] | None, subscribed_policies: list[UUID] | None, subscribed_connectors: list[UUID] | None), `SettingsResponse` (workspace_id, all subscribed_* lists, updated_at)
- [x] T043 [P] [US6] Add settings repository methods to `apps/control-plane/src/platform/workspaces/repository.py`: `async def get_settings(workspace_id) → WorkspaceSettings | None`, `async def update_settings(workspace_id, **fields) → WorkspaceSettings` (upsert — creates with defaults if not exists)
- [x] T044 [US6] Add settings service methods to `apps/control-plane/src/platform/workspaces/service.py`: `async def get_settings(workspace_id, requester_id)` (any role), `async def update_settings(workspace_id, requester_id, request)` (requires admin/owner); also wire limit check in `create_workspace()`: call `accounts_service.get_user_workspace_limit(user_id)`; if limit > 0 and `count_owned_workspaces >= limit`: raise `WorkspaceLimitError`; add `get_user_workspace_ids(user_id) → list[UUID]` internal interface for auth middleware
- [x] T045 [US6] Add settings router endpoints to `apps/control-plane/src/platform/workspaces/router.py`: `GET /{workspace_id}/settings`, `PATCH /{workspace_id}/settings`

**Checkpoint**: All 6 user stories functional — complete workspaces bounded context

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: DI wiring, router mount, test coverage audit, lint/type check.

- [x] T046 [P] Implement `apps/control-plane/src/platform/workspaces/dependencies.py`: `async def get_workspaces_service(session: AsyncSession = Depends(get_db), ...) → WorkspacesService` — DI factory injecting repository, kafka producer, accounts service reference
- [x] T047 [P] Mount workspaces router in `apps/control-plane/src/platform/api/__init__.py` (or `main.py`): `app.include_router(workspaces_router, prefix="/api/v1/workspaces", tags=["workspaces"])`
- [x] T048 [P] Write unit tests `apps/control-plane/tests/unit/test_workspaces_router.py`: TestClient tests for all 20 endpoints — verify correct HTTP status codes, request validation (422 on bad input), auth guard (401 without token), and error mapping (404, 409, 403)
- [x] T049 [P] Write unit tests `apps/control-plane/tests/unit/test_workspaces_schemas.py`: Pydantic validators — name length bounds, description length bounds, role validator rejects `owner` in AddMemberRequest, goal title length, empty list defaults
- [x] T050 Run `ruff check apps/control-plane/src/platform/workspaces/` and fix all linting errors
- [x] T051 Run `mypy --strict apps/control-plane/src/platform/workspaces/` and fix all type errors
- [x] T052 Run `pytest apps/control-plane/tests/ --cov=src/platform/workspaces --cov-report=term-missing` and verify ≥ 95% line coverage; add missing tests for any uncovered branches

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (stubs + migration) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 complete
- **US2 (Phase 4)**: Depends on Phase 1 + US1 (Membership model references Workspace; service methods check ownership via membership)
- **US3 (Phase 5)**: Depends on US1 + US2 (default provisioning creates workspace + owner membership)
- **US4 (Phase 6)**: Depends on Phase 2 only — goal model references Workspace; can parallel with US2/US3
- **US5 (Phase 7)**: Depends on Phase 2 only — visibility grant model references Workspace; can parallel with US2/US3/US4
- **US6 (Phase 8)**: Depends on US1 (creates default WorkspaceSettings on workspace creation); settings model references Workspace
- **Polish (Phase 9)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — no story dependencies. Start immediately.
- **US2 (P1)**: After US1 — Membership checks workspace ownership; service reuses workspace repository.
- **US3 (P1)**: After US1 + US2 — default provisioning creates workspace + owner membership in one operation.
- **US4 (P2)**: After Phase 2 — independent. WorkspaceGoal has workspace_id FK but no service coupling to US2/US3.
- **US5 (P2)**: After Phase 2 — independent. WorkspaceVisibilityGrant has workspace_id FK but no service coupling.
- **US6 (P3)**: After US1 — WorkspaceSettings is auto-created during workspace creation; limit check integrates into US1 `create_workspace()`.

### Within Each User Story

- Model task [P] and schema task [P] can run in parallel (different files)
- Repository task [P] can run in parallel with model + schema tasks
- Events task [P] can run in parallel with all above
- Service task follows completion of model + schema + repository + events
- Router task follows service task
- Tests follow service + router tasks

### Parallel Opportunities

- T002 (migration) and T003 (settings config): independent files, run in parallel
- T004 (enums), T005 (exceptions), T006 (state machine): all different files, all in parallel
- Within each US phase: model [P] + schema [P] + repository [P] + events [P] all in parallel
- US4, US5, US6 can all be started in parallel after Phase 2 completes (no inter-story dependencies between them)

---

## Parallel Example: US1 + US4 + US5 Concurrent (after Phase 2)

```bash
# Workstream A — US1 (Workspace CRUD)
Task T007: Workspace model (models.py)       # parallel
Task T008: Workspace schemas (schemas.py)    # parallel
Task T009: Workspace repository              # parallel
Task T010: Workspace events                  # parallel
  → Task T011: Workspace service (depends on T007–T010)
  → Task T012: Workspace router (depends on T011)
  → Task T013/T014: Tests

# Workstream B — US4 (Goals, no dependency on US1 service)
Task T027: WorkspaceGoal model               # parallel
Task T028: Goal schemas                      # parallel
Task T029: Goal repository                   # parallel
Task T030: Goal events                       # parallel
  → Task T031: Goal service
  → Task T032: Goal router

# Workstream C — US5 (Visibility Grants)
Task T035: WorkspaceVisibilityGrant model    # parallel
Task T036: Visibility schemas                # parallel
Task T037: Visibility repository             # parallel
Task T038: Visibility events                 # parallel
  → Task T039: Visibility service
  → Task T040: Visibility router
```

---

## Implementation Strategy

### MVP First (US1 Only — Working Workspace CRUD)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T006)
3. Complete Phase 3: US1 (T007–T014)
4. **STOP and VALIDATE**: Workspaces can be created, listed, updated, archived, restored with full isolation
5. Deploy/demo if ready

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation ready
2. + US1 (T007–T014) → Workspace CRUD → **MVP**
3. + US2 (T015–T022) → Multi-user workspaces with role-based access
4. + US3 (T023–T026) → New users get default workspace automatically
5. + US4 (T027–T034) → Workspace goals with GID correlation
6. + US5 (T035–T040) → Workspace-wide visibility grants
7. + US6 (T041–T045) → Workspace limits + settings
8. Phase 9 → Production-ready (DI wiring, lint, type check, full coverage)

### Parallel Team Strategy (2 Developers)

- **Dev A**: Phase 1 → Phase 2 → US1 → US2 → US3 (foundation + member-facing)
- **Dev B**: Phase 1 → Phase 2 → US4 → US5 → US6 (goals + visibility + settings — all independent after foundation)

---

## Notes

- [P] tasks operate on different files — no inter-task dependencies within the same phase
- US4, US5, and US6 each touch separate models/tables — they can be fully parallelized after Phase 2
- `WorkspaceSettings` is auto-created (with empty defaults) when a workspace is created (in `service.create_workspace()`) — T011 must create default settings as part of workspace creation before T044 adds settings CRUD
- The `accounts_service.get_user_workspace_limit()` call in T044 requires an in-process service reference injected via DI — ensure `WorkspacesService.__init__` accepts an optional `accounts_service` parameter
- Commit after each phase or logical group
- Verify quickstart.md test scenarios after each user story checkpoint
