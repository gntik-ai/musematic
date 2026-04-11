# Tasks: Accounts Bounded Context

**Input**: Design documents from `/specs/016-accounts-bounded-context/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/accounts-api.md ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Tests included per spec requirement: "Test coverage ≥95%"

---

## Phase 1: Setup (Bounded Context Scaffold)

**Purpose**: Create the `accounts/` package structure, migration, and settings. Unblocks all user story phases.

- [x] T001 Create `apps/control-plane/src/platform/accounts/` package with empty stubs: `__init__.py`, `models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`, `state_machine.py`, `email.py`
- [x] T002 Add accounts-specific settings to `apps/control-plane/src/platform/common/config.py` — `ACCOUNTS_SIGNUP_MODE: Literal["open", "invite_only", "admin_approval"] = "open"`, `ACCOUNTS_EMAIL_VERIFY_TTL_HOURS: int = 24`, `ACCOUNTS_INVITE_TTL_DAYS: int = 7`, `ACCOUNTS_RESEND_RATE_LIMIT: int = 3`
- [x] T003 Write Alembic migration `apps/control-plane/migrations/versions/003_accounts_tables.py` — create `accounts_users` (id, email UNIQUE, display_name, status enum, signup_source enum, invitation_id nullable FK, email_verified_at, activated_at, suspended_at/by/reason, blocked_at/by/reason, archived_at/by, created_at, updated_at, deleted_at), `accounts_email_verifications` (id, user_id FK, token_hash UNIQUE, expires_at, consumed), `accounts_invitations` (id, token_hash UNIQUE, inviter_id, invitee_email, invitee_message, roles_json, workspace_ids_json, status enum, expires_at, consumed_by_user_id, consumed_at, revoked_by, revoked_at), `accounts_approval_requests` (id, user_id UNIQUE FK, requested_at, reviewer_id, decision enum nullable, decision_at, reason); add indexes: `accounts_users(status)`, `accounts_users(created_at)`, `accounts_email_verifications(user_id)`, `accounts_invitations(inviter_id)`, `accounts_invitations(invitee_email)`

**Checkpoint**: `alembic upgrade head` creates all 4 tables. `alembic downgrade -1` drops them cleanly.

---

## Phase 2: Foundational (Shared Infrastructure)

**Purpose**: Enums, exceptions, state machine, and event infrastructure — required by ALL user story phases.

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [x] T004 [P] Write enums in `apps/control-plane/src/platform/accounts/models.py` — `UserStatus` (pending_verification, pending_approval, active, suspended, blocked, archived), `SignupSource` (self_registration, invitation), `InvitationStatus` (pending, consumed, expired, revoked), `ApprovalDecision` (approved, rejected) as `str, Enum` classes; SQLAlchemy enum types for each
- [x] T005 [P] Write `apps/control-plane/src/platform/accounts/exceptions.py` — `AccountsError(PlatformError)` base; `InvalidTransitionError(AccountsError)` with from_status/to_status fields; `InvalidOrExpiredTokenError(AccountsError)` (generic, anti-enumeration); `RateLimitError(AccountsError)` with retry_after field; `InvitationError(AccountsError)` subtypes: `InvitationAlreadyConsumedError`, `InvitationExpiredError`, `InvitationRevokedError`; `EmailAlreadyRegisteredError(AccountsError)` for invitation flow only; all inherit `PlatformError(code, message, details)`
- [x] T006 [P] Write `apps/control-plane/src/platform/accounts/state_machine.py` — `VALID_TRANSITIONS: dict[UserStatus, set[UserStatus]]` covering all valid transitions per data-model.md; `validate_transition(from_status: UserStatus, to_status: UserStatus) -> None` raises `InvalidTransitionError` on violation; module-level function, no class needed
- [x] T007 Write `apps/control-plane/src/platform/accounts/events.py` — `AccountsEventType` enum with all 15 event type strings (accounts.user.registered, accounts.user.email_verified, etc.); Pydantic payload models: `UserRegisteredPayload`, `UserActivatedPayload` (user_id, email, display_name, signup_source), `UserLifecyclePayload` (user_id, actor_id, reason), `InvitationPayload` (invitation_id, invitee_email, inviter_id); `publish_accounts_event(producer, event_type, payload, correlation_ctx)` async helper that wraps `EventEnvelope` from `common/events/envelope.py` and publishes to `accounts.events` topic

**Checkpoint**: `pytest tests/unit/test_accounts_state_machine.py` — all valid/invalid transitions covered.

---

## Phase 3: User Story 1 — Self-Registration and Email Verification (Priority: P1) 🎯 MVP

**Goal**: New users can register, receive a verification email, verify their address, and become active (open mode) or pending_approval (admin_approval mode).

**Independent Test**: Register with valid data → 202. Extract token from DB → POST /verify-email → 200, status=active (open mode). Register with duplicate email → 202 (same response). Submit expired token → 400 INVALID_OR_EXPIRED_TOKEN. Verify Kafka `accounts.user.registered` and `accounts.user.activated` events emitted.

### Tests for User Story 1

- [x] T008 [P] [US1] Write Vitest-equivalent unit tests for `apps/control-plane/tests/unit/test_accounts_state_machine.py` — test every valid transition returns None, every invalid transition raises `InvalidTransitionError` with correct from/to statuses, archived→anything raises InvalidTransitionError
- [x] T009 [P] [US1] Write unit tests for `apps/control-plane/tests/unit/test_accounts_schemas.py` — test `RegisterRequest` validates password strength (min 12 chars, uppercase, lowercase, digit, special char required), rejects missing fields, normalizes email to lowercase; test `VerifyEmailRequest` rejects empty token
- [x] T010 [P] [US1] Write unit tests for `apps/control-plane/tests/unit/test_accounts_service.py` — test `register()` creates User + EmailVerification, calls email.py, returns RegisterResponse; test `verify_email()` returns correct status for open mode vs admin_approval mode; test anti-enumeration (duplicate email still returns RegisterResponse, not error); test expired token raises InvalidOrExpiredTokenError; test consumed token raises same; all with mocked repository + Redis + auth_service
- [x] T011 [P] [US1] Write integration tests for `apps/control-plane/tests/integration/test_registration_flow.py` — full flow: register → verify → active (open mode); register → verify → pending_approval (admin_approval mode); resend verification; rate limit (4th resend returns 429); mock Kafka, verify events emitted

### Implementation for User Story 1

- [x] T012 [US1] Write `User` and `EmailVerification` SQLAlchemy models in `apps/control-plane/src/platform/accounts/models.py` — `User` inherits `Base, UUIDMixin, TimestampMixin, SoftDeleteMixin`; `EmailVerification` inherits `Base, UUIDMixin, TimestampMixin`; use enums from T004; all columns per data-model.md; `__tablename__` = `accounts_users` / `accounts_email_verifications`
- [x] T013 [US1] Write registration + verification Pydantic schemas in `apps/control-plane/src/platform/accounts/schemas.py` — `RegisterRequest` with `@field_validator("password")` enforcing strength rules and `@field_validator("email")` lowercasing; `VerifyEmailRequest`; `ResendVerificationRequest`; `RegisterResponse` (hardcoded anti-enumeration message); `VerifyEmailResponse` (user_id, status)
- [x] T014 [US1] Write registration + verification repository methods in `apps/control-plane/src/platform/accounts/repository.py` — `AccountsRepository.__init__(self, session: AsyncSession)`; async methods: `create_user(email, display_name, status, signup_source) -> User`; `get_user_by_email(email) -> User | None`; `update_user_status(user_id, new_status, **kwargs) -> User`; `create_email_verification(user_id, token_hash, expires_at) -> EmailVerification`; `get_active_verification_by_token_hash(token_hash) -> EmailVerification | None`; `consume_verification(verification_id) -> None`; `get_resend_count(redis_client, user_id) -> int` and `increment_resend_count(redis_client, user_id) -> int` using Redis `INCR` + `EXPIRE`
- [x] T015 [US1] Write `apps/control-plane/src/platform/accounts/email.py` — `send_verification_email(user_id, email, token, display_name)` async stub that logs in dev or calls notifications service interface; accepts notification client from DI
- [x] T016 [US1] Write registration + verification service methods in `apps/control-plane/src/platform/accounts/service.py` — `AccountsService.__init__(self, repo, redis, kafka_producer, auth_service, settings)`; `async register(request: RegisterRequest) -> RegisterResponse`: checks signup mode, hashes token with `hashlib.sha256`, creates User + EmailVerification, calls `email.send_verification_email()`, returns `RegisterResponse` (always — never raises for duplicate email); `async verify_email(request: VerifyEmailRequest) -> VerifyEmailResponse`: hashes token, calls `repo.get_active_verification_by_token_hash()`, validates expiry + consumed=False, calls `validate_transition()`, updates user status (active or pending_approval based on settings), creates `ApprovalRequest` if pending_approval, emits events; `async resend_verification(request: ResendVerificationRequest) -> ResendVerificationResponse`: checks Redis rate limit, creates new EmailVerification if user in pending_verification (silent no-op if not), returns anti-enumeration response
- [x] T017 [US1] Write registration + verification endpoints in `apps/control-plane/src/platform/accounts/router.py` — `APIRouter(prefix="/api/v1/accounts", tags=["accounts"])`; `POST /register` → `RegisterResponse` 202; `POST /verify-email` → `VerifyEmailResponse` 200; `POST /resend-verification` → `ResendVerificationResponse` 202; signup mode guard on `/register`; error handlers for `InvalidOrExpiredTokenError` → 400, `RateLimitError` → 429

**Checkpoint**: `pytest tests/integration/test_registration_flow.py` all pass. Manual: `POST /register` returns 202. `POST /verify-email` with valid token returns 200 with correct status.

---

## Phase 4: User Story 2 — Admin Approval Workflow (Priority: P1)

**Goal**: Admins can view, approve, and reject pending accounts. Approved users become active; rejected users are archived.

**Independent Test**: Set `ACCOUNTS_SIGNUP_MODE=admin_approval`. Register + verify. `GET /pending-approvals` returns user. `POST /{user_id}/approve` → 200, status=active, `accounts.user.activated` event emitted. Register + verify another. `POST /{user_id}/reject` with reason → 200, status=archived. Attempt double-approve → 409.

### Tests for User Story 2

- [x] T018 [P] [US2] Write unit tests in `apps/control-plane/tests/unit/test_accounts_service.py` (append) — test `approve_user()` calls validate_transition(pending_approval→active), updates status, emits approved+activated events; test `reject_user()` transitions to archived, emits rejected event; test double-approve raises `InvalidTransitionError`; test approve on active user raises `InvalidTransitionError`; all with mocked repo
- [x] T019 [P] [US2] Write integration tests in `apps/control-plane/tests/integration/test_approval_flow.py` — register+verify in admin_approval mode, approve as admin, verify status=active and events; register+verify, reject with reason, verify status=archived; attempt approve already-approved user, verify 409

### Implementation for User Story 2

- [x] T020 [US2] Add `ApprovalRequest` SQLAlchemy model to `apps/control-plane/src/platform/accounts/models.py` — inherits `Base, UUIDMixin, TimestampMixin`; columns: user_id (UNIQUE FK), requested_at, reviewer_id (nullable), decision (ApprovalDecision enum nullable), decision_at (nullable), reason (nullable); `__tablename__` = `accounts_approval_requests`
- [x] T021 [US2] Add approval schemas to `apps/control-plane/src/platform/accounts/schemas.py` — `ApproveUserRequest(reason: str | None = None)`; `RejectUserRequest(reason: str)`; `PendingApprovalItem(user_id, email, display_name, registered_at, email_verified_at)`; `PendingApprovalsResponse(items, total, page, page_size, has_next, has_prev)`; `UserLifecycleResponse(user_id: UUID, status: UserStatus)`
- [x] T022 [US2] Add approval repository methods to `apps/control-plane/src/platform/accounts/repository.py` — `create_approval_request(user_id, requested_at) -> ApprovalRequest`; `get_pending_approvals(page, page_size) -> tuple[list[PendingApprovalItem], int]` — JOIN accounts_users + accounts_approval_requests WHERE status=pending_approval, ORDER BY requested_at ASC; `get_user_for_update(user_id) -> User` using `SELECT ... FOR UPDATE` within active transaction (prevents concurrent approve/reject)
- [x] T023 [US2] Add approval service methods to `apps/control-plane/src/platform/accounts/service.py` — `async approve_user(user_id, reviewer_id, reason) -> UserLifecycleResponse`: calls `get_user_for_update()`, `validate_transition(current→active)`, updates User status + activated_at, updates ApprovalRequest (decision=approved), calls `auth_service.invalidate_user_sessions()` not needed here (activating, not suspending), emits `accounts.user.approved` + `accounts.user.activated`; `async reject_user(user_id, reviewer_id, reason) -> UserLifecycleResponse`: similar but transitions to archived, emits `accounts.user.rejected`; `async get_pending_approvals(page, page_size) -> PendingApprovalsResponse`
- [x] T024 [US2] Add approval endpoints to `apps/control-plane/src/platform/accounts/router.py` — `GET /pending-approvals` (requires workspace_admin/superadmin JWT); `POST /{user_id}/approve` (workspace_admin/superadmin); `POST /{user_id}/reject` (workspace_admin/superadmin); use existing `get_current_user` DI from auth context to extract reviewer identity; error handlers for `InvalidTransitionError` → 409

**Checkpoint**: `pytest tests/integration/test_approval_flow.py` all pass. Manual: approval queue returns pending users. Approve changes status. Double-approve returns 409.

---

## Phase 5: User Story 3 — Invitation-Based Registration (Priority: P2)

**Goal**: Admins create time-limited invitation links; invitees use them to register directly as active users (bypassing verification + approval).

**Independent Test**: Admin creates invitation → 201. `GET /invitations/{token}` → 200 with details. Accept invitation with display_name + password → 201, status=active. Use same token again → 400. Use expired token → 400. Revoke pending invitation → 200. Verify `accounts.invitation.created` + `accounts.invitation.accepted` + `accounts.user.activated` events emitted.

### Tests for User Story 3

- [x] T025 [P] [US3] Write unit tests for invitation service in `apps/control-plane/tests/unit/test_accounts_service.py` (append) — test `create_invitation()` generates token, creates record, calls email; test `accept_invitation()` creates user as active, marks consumed, calls `auth_service.create_user_credential()`; test already-consumed token raises InvitationAlreadyConsumedError; test expired token raises InvitationExpiredError; test revoked token raises InvitationRevokedError; test `revoke_invitation()` by inviter succeeds, by non-inviter raises AuthorizationError
- [x] T026 [P] [US3] Write integration tests in `apps/control-plane/tests/integration/test_invitation_flow.py` — create invitation as admin, view details as unauthenticated user, accept invitation, verify account active and roles assigned, verify events; consume same invitation again → 400; revoke pending invitation → 200; accept revoked invitation → 400; create invitation for already-registered email → 409

### Implementation for User Story 3

- [x] T027 [US3] Add `Invitation` SQLAlchemy model to `apps/control-plane/src/platform/accounts/models.py` — inherits `Base, UUIDMixin, TimestampMixin`; columns per data-model.md; `__tablename__` = `accounts_invitations`
- [x] T028 [US3] Add invitation schemas to `apps/control-plane/src/platform/accounts/schemas.py` — `CreateInvitationRequest(email, roles: list[RoleType], workspace_ids: list[UUID] | None, message: str | None)`; `AcceptInvitationRequest(token, display_name, password)` with `@field_validator("password")` strength check; `InvitationResponse(id, invitee_email, roles, workspace_ids, status, expires_at, created_at)`; `InvitationDetailsResponse(invitee_email, inviter_display_name, roles, message, expires_at)`; `AcceptInvitationResponse(user_id, email, status, display_name)`
- [x] T029 [US3] Add invitation repository methods to `apps/control-plane/src/platform/accounts/repository.py` — `create_invitation(inviter_id, invitee_email, token_hash, roles_json, workspace_ids_json, message, expires_at) -> Invitation`; `get_invitation_by_token_hash(token_hash) -> Invitation | None`; `consume_invitation(invitation_id, user_id) -> None` sets status=consumed, consumed_by_user_id, consumed_at; `revoke_invitation(invitation_id, revoked_by) -> None` sets status=revoked; `list_invitations_by_inviter(inviter_id, status_filter, page, page_size) -> tuple[list[Invitation], int]`; `get_invitation_by_id(invitation_id) -> Invitation | None`
- [x] T030 [US3] Add invitation service methods to `apps/control-plane/src/platform/accounts/service.py` — `async create_invitation(request, inviter_id) -> InvitationResponse`: checks invitee_email not already active, generates `secrets.token_urlsafe(32)`, SHA-256 hashes it, creates Invitation, sends invite email, emits `accounts.invitation.created`; `async get_invitation_details(token) -> InvitationDetailsResponse`: hashes token, looks up Invitation (404/400 for invalid/expired/consumed/revoked), fetches inviter display_name; `async accept_invitation(request) -> AcceptInvitationResponse`: hashes token, validates status (raises typed errors), creates User with status=active + signup_source=invitation, calls `auth_service.create_user_credential(user.id, request.password)`, marks invitation consumed, emits `accounts.invitation.accepted` + `accounts.user.activated`, returns response; `async revoke_invitation(invitation_id, requestor_id) -> None`: checks requestor is inviter or superadmin, validates status=pending, calls `repo.revoke_invitation()`, emits `accounts.invitation.revoked`; `async list_invitations(inviter_id, status, page, page_size) -> PaginatedInvitationsResponse`
- [x] T031 [US3] Add invitation endpoints to `apps/control-plane/src/platform/accounts/router.py` — `GET /invitations/{token}` (no auth); `POST /invitations/{token}/accept` (no auth) → 201; `POST /invitations` (workspace_admin/superadmin) → 201; `GET /invitations` (workspace_admin/superadmin, filtered to current user's invitations); `DELETE /invitations/{invitation_id}` (workspace_admin/superadmin); error handlers: `InvitationAlreadyConsumedError` → 400, `InvitationExpiredError` → 400, `InvitationRevokedError` → 400, `EmailAlreadyRegisteredError` → 409

**Checkpoint**: `pytest tests/integration/test_invitation_flow.py` all pass. Manual: full invite → accept flow creates active account with assigned roles.

---

## Phase 6: User Story 4 — Admin Account Lifecycle Management (Priority: P1)

**Goal**: Admins can suspend, reactivate, block, unblock, archive, reset MFA, reset password, and unlock users. All actions invalidate sessions (where applicable) and emit events.

**Independent Test**: Active user → suspend → cannot login (verify via auth service) → reactivate → can login. Block user → verify status=blocked, sessions invalidated. Archive user → status=archived, not in user lists. Reset MFA → auth service MFA cleared. Reset password → auth service initiates reset. Unlock → auth lockout cleared. Invalid transitions → 409.

### Tests for User Story 4

- [x] T032 [P] [US4] Write unit tests for lifecycle service in `apps/control-plane/tests/unit/test_accounts_service.py` (append) — test each lifecycle action (suspend, reactivate, block, unblock, archive) calls `validate_transition()` then `update_user_status()` then `auth_service.invalidate_user_sessions()` (for status changes that disable login); test reset_mfa calls `auth_service.reset_mfa()`; test reset_password calls `auth_service.initiate_password_reset()`; test unlock calls `auth_service.clear_lockout()`; test each emits correct Kafka event; all with mocked auth_service
- [x] T033 [P] [US4] Write integration tests in `apps/control-plane/tests/integration/test_lifecycle_flow.py` — suspend active user, verify status + events; reactivate, verify status; block user, verify status; unblock, verify status; archive, verify soft-delete; reset MFA (mock auth service); reset password (mock auth service); unlock (mock auth service); test invalid transitions (suspend archived → 409, reactivate active → 409)

### Implementation for User Story 4

- [x] T034 [US4] Add lifecycle schemas to `apps/control-plane/src/platform/accounts/schemas.py` — `SuspendUserRequest(reason: str)`; `BlockUserRequest(reason: str)`; `ArchiveUserRequest(reason: str | None = None)`; `ReactivateUserRequest(reason: str | None = None)`; `UnblockUserRequest(reason: str | None = None)`; `ResetPasswordRequest(force_change_on_login: bool = True)`; `ResetMfaResponse(user_id: UUID, mfa_cleared: bool)`; `ResetPasswordResponse(user_id: UUID, password_reset_initiated: bool)`; `UnlockResponse(user_id: UUID, unlocked: bool)`
- [x] T035 [US4] Add lifecycle service methods to `apps/control-plane/src/platform/accounts/service.py` — private `async _transition_user(user_id, actor_id, to_status, event_type, reason, **status_fields) -> UserLifecycleResponse` helper: `get_user_for_update()`, `validate_transition()`, `update_user_status()`, optionally `auth_service.invalidate_user_sessions()` (for suspended, blocked, archived), emit event; public methods: `suspend_user(user_id, actor_id, reason)`, `reactivate_user(user_id, actor_id, reason)`, `block_user(user_id, actor_id, reason)`, `unblock_user(user_id, actor_id, reason)`, `archive_user(user_id, actor_id, reason)`; separate methods: `reset_mfa(user_id, actor_id) -> ResetMfaResponse`: calls `auth_service.reset_mfa(user_id)`, emits `accounts.user.mfa_reset`; `reset_password(user_id, actor_id, force_change) -> ResetPasswordResponse`: calls `auth_service.initiate_password_reset(user_id, force_change_on_login)`, emits `accounts.user.password_reset_initiated`; `unlock_user(user_id, actor_id) -> UnlockResponse`: calls `auth_service.clear_lockout(user_id)`, no status transition (lockout is auth domain), emits `accounts.user.unlocked` (or omit event — lockout is not a lifecycle transition)
- [x] T036 [US4] Add lifecycle endpoints to `apps/control-plane/src/platform/accounts/router.py` — `POST /{user_id}/suspend` (workspace_admin/superadmin); `POST /{user_id}/reactivate` (workspace_admin/superadmin); `POST /{user_id}/block` (superadmin only); `POST /{user_id}/unblock` (superadmin only); `POST /{user_id}/archive` (superadmin only); `POST /{user_id}/reset-mfa` (workspace_admin/superadmin); `POST /{user_id}/reset-password` (workspace_admin/superadmin); `POST /{user_id}/unlock` (workspace_admin/superadmin); all return `UserLifecycleResponse` or specific response types; RBAC enforced via DI decorator or dependency

**Checkpoint**: `pytest tests/integration/test_lifecycle_flow.py` all pass. Suspend + reactivate cycle changes login behavior. Invalid transition returns 409.

---

## Phase 7: User Story 5 — Default Workspace Provisioning on Activation (Priority: P2)

**Goal**: When a user transitions to "active" for the first time, emit `accounts.user.activated` with full payload so the workspace bounded context can create a default workspace.

**Independent Test**: Register + verify (open mode) → Kafka consumer mock receives `accounts.user.activated` with `user_id`, `email`, `display_name`, `signup_source`. Approve via admin approval → same event emitted. Accept invitation → same event. Reactivate suspended user → NO new event (not first activation).

### Tests for User Story 5

- [x] T037 [P] [US5] Write unit tests in `apps/control-plane/tests/unit/test_accounts_service.py` (append) — test `accounts.user.activated` event payload contains `user_id`, `email`, `display_name`, `signup_source`; test event is emitted when `activated_at` was None (first activation); test event is NOT emitted on reactivation from suspended (activated_at already set); all with mocked Kafka producer
- [x] T038 [P] [US5] Write integration test in `apps/control-plane/tests/integration/test_workspace_provisioning.py` — mock Kafka consumer subscribed to `accounts.events`; activate user via registration flow; verify `accounts.user.activated` message received with correct fields; activate via approval flow; activate via invitation; reactivate from suspended; verify no second activation event

### Implementation for User Story 5

- [x] T039 [US5] Verify `accounts.user.activated` event emission in `apps/control-plane/src/platform/accounts/service.py` — in `verify_email()`, `approve_user()`, and `accept_invitation()` methods: check if `user.activated_at is None` before emitting `accounts.user.activated`; if already set (reactivation from suspended does NOT emit this event, just emits `accounts.user.reactivated`); ensure `UserActivatedPayload` includes `user_id`, `email`, `display_name`, `signup_source` per data-model.md events table
- [x] T040 [US5] Add `UserActivatedPayload` to `apps/control-plane/src/platform/accounts/events.py` — `UserActivatedPayload(user_id: UUID, email: str, display_name: str, signup_source: SignupSource)`; ensure this is the payload used in all three activation paths (open registration, admin approval, invitation acceptance)

**Checkpoint**: T037/T038 tests pass. Mock Kafka consumer receives `accounts.user.activated` on all first-activation paths. No duplicate event on reactivation.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: DI wiring, router mounting, coverage audit, lint/type check.

- [x] T041 Write `apps/control-plane/src/platform/accounts/dependencies.py` — `get_accounts_service(session: AsyncSession = Depends(get_db), redis = Depends(get_redis), producer = Depends(get_kafka_producer), auth_service = Depends(get_auth_service), settings: PlatformSettings = Depends(get_settings)) -> AccountsService`; `get_accounts_repository(session: AsyncSession = Depends(get_db)) -> AccountsRepository`
- [x] T042 Mount accounts router in `apps/control-plane/src/platform/api/__init__.py` or `apps/control-plane/src/platform/main.py` — `from platform.accounts.router import router as accounts_router; app.include_router(accounts_router)`
- [x] T043 [P] Run full coverage audit: `pytest tests/ --cov=src/platform/accounts --cov-report=term-missing` — identify and fill gaps to reach ≥95% line coverage on all `accounts/` modules
- [x] T044 [P] Run `ruff check src/platform/accounts/` — fix ALL warnings and errors until output is clean
- [x] T045 [P] Run `mypy src/platform/accounts/ --strict` — fix ALL type errors until output is clean
- [ ] T046 Verify quickstart.md steps all pass end-to-end per `specs/016-accounts-bounded-context/quickstart.md` — registration, approval, invitation, lifecycle, anti-enumeration flows

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Requires Phase 1 — blocks ALL user story phases
- **Phase 3 (US1)**: Requires Phase 2 — all features depend on User model and state machine
- **Phase 4 (US2)**: Requires Phase 3 — approval workflow is triggered by email verification (pending_approval path)
- **Phase 5 (US3)**: Requires Phase 3 — invitation acceptance calls auth credential creation; depends on User model from US1
- **Phase 6 (US4)**: Requires Phase 3 — lifecycle management operates on User model; suspend/block/archive call session invalidation via auth service
- **Phase 7 (US5)**: Requires Phase 3 (registration path), Phase 4 (approval path), Phase 5 (invitation path) — all three activation paths must exist before verifying event emission
- **Phase 8 (Polish)**: Requires all phases complete

### User Story Dependencies

```
Phase 1 (Setup: package stubs, migration, settings)
    ↓
Phase 2 (Foundational: enums, exceptions, state machine, events)
    ↓
Phase 3 (US1: registration + email verification) ← P1 critical path
    ↓                    ↓                   ↓
Phase 4 (US2: admin    Phase 5 (US3:       Phase 6 (US4:
 approval) P1 ←         invitations) P2 ←   lifecycle) P1 ←
 depends on US1         depends on US1       depends on US1
    ↓                    ↓                   ↓
Phase 7 (US5: workspace provisioning event — depends on all 3 activation paths)
    ↓
Phase 8 (Polish)
```

### Parallel Opportunities After Phase 3

Once US1 (Phase 3) is complete, US2, US3, and US4 can proceed in parallel:
- **Developer A**: Phase 4 — Admin Approval (US2)
- **Developer B**: Phase 5 — Invitations (US3)
- **Developer C**: Phase 6 — Lifecycle Management (US4)

---

## Parallel Examples

### Phase 2 — Foundational (all 4 tasks on different files)

```
Parallel:
  T004 models.py (enums)
  T005 exceptions.py
  T006 state_machine.py
Sequential after above:
  T007 events.py (depends on enums from T004)
```

### Phase 3 — US1 (tests parallel with each other; impl sequential)

```
Tests (parallel):
  T008 test_accounts_state_machine.py
  T009 test_accounts_schemas.py
  T010 test_accounts_service.py
  T011 test_registration_flow.py

Implementation (sequential):
  T012 models.py (User + EmailVerification)
  → T013 schemas.py (RegisterRequest with validator)
  → T014 repository.py (CRUD methods)
  → T015 email.py (send stub)
  → T016 service.py (register + verify_email + resend)
  → T017 router.py (3 endpoints)
```

### Phase 4+5+6 — After US1 (fully parallel across stories)

```
Phase 4 (US2) and Phase 5 (US3) and Phase 6 (US4) can run concurrently
  Each adds to models.py, schemas.py, repository.py, service.py, router.py
  in distinct, non-conflicting sections
```

---

## Implementation Strategy

### MVP First (US1 + US4 only — operational platform)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 (registration + email verification) → **users can register and activate**
4. Complete Phase 6: US4 (lifecycle management) → **admins can suspend/block/archive**
5. **STOP and VALIDATE**: Registration flow works end-to-end. Lifecycle actions work.
6. Deploy — platform has usable user onboarding and admin tools

### Incremental Delivery

1. Setup + Foundational → infrastructure ready
2. US1 → self-registration works **(MVP)**
3. US2 → admin approval workflow **(enterprise onboarding)**
4. US3 → invitations **(controlled onboarding)**
5. US4 → lifecycle management **(admin operations)**
6. US5 → workspace provisioning event **(full onboarding chain)**
7. Polish → coverage + type safety verified

---

## Notes

- [P] tasks within a phase operate on different files — safe to parallelize
- `SELECT FOR UPDATE` in T022/T035 prevents concurrent approve/reject and concurrent lifecycle transitions — do NOT remove
- `auth_service` is injected via DI; accounts never directly imports auth models or Redis keys
- Anti-enumeration: `register()` and `resend_verification()` MUST return the same response shape regardless of whether email exists — verified by T009/T010
- `accounts.user.activated` MUST NOT be emitted on reactivation from suspended — only on first-ever activation (check `user.activated_at is None`) — enforced by T037/T039
- `token_hash` is SHA-256 hex digest: `hashlib.sha256(token.encode()).hexdigest()` — 64 hex chars = String(64) in model
- The `accounts.events` Kafka topic is new and must be created before integration tests run — add to Kafka topic configuration alongside existing topics
