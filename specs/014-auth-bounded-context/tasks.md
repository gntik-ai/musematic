# Tasks: Auth Bounded Context — Authentication, Authorization, and Session Management

**Input**: Design documents from `specs/014-auth-bounded-context/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/auth-api.md ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story to enable independent implementation and testing.  
**Tests**: Required by spec (SC-010: ≥95% coverage).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)

---

## Phase 1: Setup

**Purpose**: Bounded context package structure and shared auth settings

- [X] T001 Create `apps/control-plane/src/platform/auth/` package with empty `__init__.py`
- [X] T002 Add auth-specific settings to `apps/control-plane/src/platform/common/config.py` — extend `AuthSettings` with `jwt_private_key: str`, `jwt_public_key: str`, `access_token_ttl: int = 900`, `refresh_token_ttl: int = 604800`, `lockout_threshold: int = 5`, `lockout_duration: int = 900`, `mfa_encryption_key: str = ""`, `mfa_enrollment_ttl: int = 600`, `session_ttl: int = 604800`, `password_reset_ttl: int = 3600`

**Checkpoint**: Auth package importable; settings loaded from env

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure — migration, exceptions, schemas — MUST be complete before any user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Write `apps/control-plane/migrations/versions/002_auth_tables.py` — Alembic migration creating all 7 tables: `user_credentials`, `mfa_enrollments`, `auth_attempts`, `password_reset_tokens`, `service_account_credentials`, `user_roles`, `role_permissions`; include seed `INSERT` for full permission matrix (10 roles × resource types × actions per `data-model.md` Permission Matrix)
- [X] T004 [P] Implement `apps/control-plane/src/platform/auth/exceptions.py` — auth-specific exceptions inheriting from `PlatformError`: `InvalidCredentialsError` (401, code `INVALID_CREDENTIALS`), `AccountLockedError` (403, code `ACCOUNT_LOCKED`), `InvalidMfaCodeError` (401, code `INVALID_MFA_CODE`), `InvalidMfaTokenError` (401, code `INVALID_MFA_TOKEN`), `MfaAlreadyEnrolledError` (409, code `MFA_ALREADY_ENROLLED`), `NoPendingEnrollmentError` (404, code `NO_PENDING_ENROLLMENT`), `InvalidRefreshTokenError` (401, code `INVALID_REFRESH_TOKEN`), `ApiKeyInvalidError` (401, code `INVALID_API_KEY`)
- [X] T005 [P] Implement `apps/control-plane/src/platform/auth/schemas.py` — all Pydantic v2 schemas and enums per `data-model.md`: `RoleType`, `AuthOutcome`, `MfaStatus`, `CredentialStatus` enums; `LoginRequest`, `LoginResponse`, `MfaChallengeResponse`, `MfaVerifyRequest`, `RefreshRequest`, `TokenPair`, `MfaEnrollResponse`, `PermissionCheckRequest`, `PermissionCheckResponse`, `ServiceAccountCreateRequest`, `ServiceAccountCreateResponse`

**Checkpoint**: Migration runs cleanly; exceptions importable; schemas validate

---

## Phase 3: User Story 1 — Email/Password Login with JWT Issuance (Priority: P1) 🎯 MVP

**Goal**: Full login → token pair → refresh → logout flow using email/password with Argon2id, RS256 JWT pair, Redis-backed sessions

**Independent Test**: `POST /api/v1/auth/login` with correct credentials → 200 with access+refresh tokens. Use access token on protected endpoint → 200. Use refresh token → new access token. `POST /api/v1/auth/logout` → session destroyed. Verify subsequent refresh fails.

### Tests for User Story 1

- [X] T006 [P] [US1] Write `apps/control-plane/tests/unit/test_auth_password.py` — tests for `hash_password()` produces PHC-format Argon2id string, `verify_password()` returns True for correct password and False for wrong, `needs_rehash()` detects outdated params
- [X] T007 [P] [US1] Write `apps/control-plane/tests/unit/test_auth_tokens.py` — tests for `create_token_pair()` produces access+refresh JWTs with correct expiry claims, `decode_token()` verifies RS256 signature and returns claims, `decode_token()` raises `InvalidRefreshTokenError` for expired/invalid tokens
- [X] T008 [P] [US1] Write `apps/control-plane/tests/unit/test_auth_session.py` — tests for `create_session()` sets Redis hash + user_sessions set with correct TTL, `get_session()` retrieves session data, `delete_session()` removes hash and updates set, `delete_all_sessions()` removes all sessions for user (mocked Redis)

### Implementation for User Story 1

- [X] T009 [P] [US1] Implement `apps/control-plane/src/platform/auth/models.py` — all 7 SQLAlchemy models per `data-model.md`: `UserCredential` (UUIDMixin, TimestampMixin, SoftDeleteMixin), `MfaEnrollment` (UUIDMixin, TimestampMixin), `AuthAttempt` (UUIDMixin — append-only, no TimestampMixin), `PasswordResetToken` (UUIDMixin, TimestampMixin), `ServiceAccountCredential` (UUIDMixin, TimestampMixin, SoftDeleteMixin), `UserRole` (UUIDMixin, TimestampMixin) with UniqueConstraint, `RolePermission` (UUIDMixin) with UniqueConstraint
- [X] T010 [P] [US1] Implement `apps/control-plane/src/platform/auth/password.py` — `hash_password(plain: str) -> str` using `argon2.PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16).hash(plain)`; `verify_password(plain: str, hashed: str) -> bool` using `ph.verify(hashed, plain)` returning False on `VerifyMismatchError`; `needs_rehash(hashed: str) -> bool` using `ph.check_needs_rehash(hashed)`
- [X] T011 [P] [US1] Implement `apps/control-plane/src/platform/auth/tokens.py` — `create_token_pair(user_id: UUID, email: str, session_id: UUID, roles: list[dict], settings: AuthSettings) -> tuple[str, str]` generates access token (15min, claims: sub, email, roles, session_id, iat, exp) and refresh token (7d, claims: sub, session_id, jti, iat, exp) both RS256-signed; `decode_token(token: str, settings: AuthSettings) -> dict` verifies RS256 signature and returns claims, raises `InvalidRefreshTokenError` on ExpiredSignatureError/DecodeError
- [X] T012 [US1] Implement `apps/control-plane/src/platform/auth/session.py` — async `RedisSessionStore` wrapping `AsyncRedisClient`; `async create_session(user_id, session_id, email, roles, ip, device, refresh_jti) -> None` sets `session:{user_id}:{session_id}` hash with TTL + adds to `user_sessions:{user_id}` set; `async get_session(user_id, session_id) -> dict | None`; `async delete_session(user_id, session_id) -> None`; `async delete_all_sessions(user_id) -> int` (returns count deleted)
- [X] T013 [US1] Implement `apps/control-plane/src/platform/auth/repository.py` — `AuthRepository` class with `AsyncSession`; `async get_credential_by_email(email: str) -> UserCredential | None`; `async create_credential(user_id: UUID, email: str, password_hash: str) -> UserCredential`; `async update_password_hash(user_id: UUID, new_hash: str) -> None`; `async get_user_roles(user_id: UUID, workspace_id: UUID | None) -> list[UserRole]`; `async get_role_permissions(role: str) -> list[RolePermission]`; `async record_auth_attempt(user_id: UUID | None, email: str, ip: str, user_agent: str, outcome: str) -> None`
- [X] T014 [US1] Implement `apps/control-plane/src/platform/auth/service.py` — `AuthService` with `login(email, password, ip, device, session_id) -> LoginResponse | MfaChallengeResponse`: (1) get credential, (2) if locked raise `AccountLockedError`, (3) verify password or increment failure counter, (4) if MFA active return challenge, (5) create session, (6) issue JWT pair, (7) emit event; `refresh_token(refresh_token_str) -> TokenPair`: decode refresh JWT, verify jti matches session, issue new access token; `logout(user_id, session_id) -> None`; `logout_all(user_id) -> int`
- [X] T015 [US1] Implement `apps/control-plane/src/platform/auth/router.py` — `router = APIRouter(prefix="/api/v1/auth", tags=["auth"])`; `POST /login` → `AuthService.login`; `POST /refresh` → `AuthService.refresh_token`; `POST /logout` → `AuthService.logout` (requires JWT); `POST /logout-all` → `AuthService.logout_all` (requires JWT); responses match `contracts/auth-api.md`
- [X] T016 [US1] Write `apps/control-plane/tests/unit/test_auth_service.py` — unit tests for `AuthService.login` happy path (mocked repository + Redis), `AuthService.login` with wrong password (increments counter), `AuthService.refresh_token` with valid refresh JWT, `AuthService.logout` deletes session

**Checkpoint**: `POST /api/v1/auth/login` → JWT pair. `POST /api/v1/auth/refresh` → new access token. `POST /api/v1/auth/logout` → 200. All US1 unit tests pass.

---

## Phase 4: User Story 2 — Account Lockout and Throttling (Priority: P1)

**Goal**: Redis counter tracks failed attempts; account locked after threshold; lockout auto-expires; audit attempt recording; `auth.user.locked` event emitted

**Independent Test**: 5 consecutive wrong-password attempts → 6th attempt (even with correct password) returns 403 `ACCOUNT_LOCKED`. Wait lockout duration or flush Redis → login succeeds. Verify `auth_attempts` rows created for each attempt.

### Tests for User Story 2

- [X] T017 [P] [US2] Write `apps/control-plane/tests/unit/test_auth_lockout.py` — tests for `increment_failure()` increments counter and sets TTL, `is_locked()` returns True when locked key exists, `lock_account()` sets locked key with TTL, `reset_failure_counter()` deletes both keys; verify lockout integrates into login flow (mocked Redis + service)

### Implementation for User Story 2

- [X] T018 [P] [US2] Implement `apps/control-plane/src/platform/auth/lockout.py` — async `LockoutManager` wrapping `AsyncRedisClient`; `async is_locked(user_id: UUID) -> bool` checks `auth:locked:{user_id}` key; `async increment_failure(user_id: UUID, threshold: int, duration: int) -> int` increments `auth:lockout:{user_id}` counter (set TTL on first increment), calls `lock_account()` when threshold reached, returns current count; `async lock_account(user_id: UUID, duration: int) -> None` sets `auth:locked:{user_id}` with TTL; `async reset_failure_counter(user_id: UUID) -> None` deletes both keys
- [X] T019 [US2] Integrate lockout into `apps/control-plane/src/platform/auth/service.py` `login()` — (1) before password verification, check `lockout.is_locked()` → raise `AccountLockedError` if True; (2) on password failure, call `lockout.increment_failure()`; (3) on success, call `lockout.reset_failure_counter()`
- [X] T020 [US2] Add auth attempt recording to `apps/control-plane/src/platform/auth/service.py` `login()` — call `repository.record_auth_attempt()` with correct `AuthOutcome` after each login attempt (success, failure_password, failure_locked, failure_mfa)
- [X] T021 [P] [US2] Implement `apps/control-plane/src/platform/auth/events.py` — Pydantic payload schemas per `data-model.md` (`UserAuthenticatedPayload`, `UserLockedPayload`, `SessionRevokedPayload`, `MfaEnrolledPayload`, `PermissionDeniedPayload`, `ApiKeyRotatedPayload`); async `publish_auth_event(event_type: str, payload: BaseModel, correlation_id: UUID, producer: EventProducer) -> None` builds `EventEnvelope` and publishes to `auth.events` topic
- [X] T022 [US2] Emit `auth.user.locked` event in `apps/control-plane/src/platform/auth/lockout.py` `lock_account()` — call `publish_auth_event("auth.user.locked", UserLockedPayload(...), ...)` via injected producer

**Checkpoint**: 5 wrong-password attempts → account locked. Correct password while locked → 403. `auth_attempts` table populated. `auth.user.locked` event on `auth.events` topic.

---

## Phase 5: User Story 4 — Role-Based Access Control (Priority: P1)

**Goal**: RBAC engine checks `(role, resource_type, action, workspace_id)` against permission matrix; superadmin bypass; workspace-scoped roles; `auth.permission.denied` event on denial

**Independent Test**: User with "viewer" role → `check_permission("agent", "read", workspace_id)` returns True; `check_permission("agent", "write", workspace_id)` returns False with 403. User with "superadmin" → all checks return True.

### Tests for User Story 4

- [X] T023 [P] [US4] Write `apps/control-plane/tests/unit/test_auth_rbac.py` — tests for `check_permission()`: viewer can read, cannot write; superadmin bypasses all; wrong workspace_id denied; multiple roles evaluated together; permission denied event emitted on denial (mocked producer)
- [X] T024 [P] [US4] Write `apps/control-plane/tests/integration/test_auth_rbac_flow.py` — integration test: assign user a role via `UserRole`, call `check_permission()` against live PostgreSQL permissions seed data, verify allow/deny results match expected matrix

### Implementation for User Story 4

- [X] T025 [P] [US4] Extend `apps/control-plane/src/platform/auth/repository.py` — add `async get_all_role_permissions() -> list[RolePermission]` for cache loading; add `async assign_user_role(user_id: UUID, role: str, workspace_id: UUID | None) -> UserRole`; add `async revoke_user_role(user_role_id: UUID) -> None`
- [X] T026 [US4] Implement `apps/control-plane/src/platform/auth/rbac.py` — `RBACEngine` class; `async load_permissions(repository: AuthRepository) -> None` loads all `RolePermission` rows into in-memory dict `{role: {(resource_type, action, scope)}}` on startup; `async check_permission(user_id: UUID, resource_type: str, action: str, workspace_id: UUID | None, db: AsyncSession, redis_client: AsyncRedisClient) -> PermissionCheckResponse`: (1) load user roles from repository, (2) superadmin → allow, (3) match against permission matrix, (4) emit `auth.permission.denied` on denial; module-level `rbac_engine = RBACEngine()`
- [X] T027 [US4] Implement `apps/control-plane/src/platform/auth/dependencies.py` — `async get_auth_service(...)`, `async require_permission(resource_type: str, action: str) -> Callable` — factory that returns a FastAPI dependency checking RBAC for the current user on the specified resource

**Checkpoint**: Viewer role → read allowed, write denied with 403. Superadmin → all allowed. `auth.permission.denied` event emitted. Integration test passes against seeded permission matrix.

---

## Phase 6: User Story 3 — Multi-Factor Authentication TOTP (Priority: P2)

**Goal**: TOTP enrollment generates encrypted secret + recovery codes; login challenges MFA-enabled users; TOTP and recovery code verification; MFA confirm endpoint

**Independent Test**: `POST /mfa/enroll` → secret + provisioning_uri + recovery_codes. `POST /mfa/confirm` with valid TOTP → MFA active. Subsequent login → returns MFA challenge. `POST /mfa/verify` with valid TOTP → full token pair. Recovery code used once → works; second use → fails.

### Tests for User Story 3

- [X] T028 [P] [US3] Write `apps/control-plane/tests/unit/test_auth_mfa.py` — tests for `generate_totp_secret()` returns base32 string, `encrypt_secret()`/`decrypt_secret()` roundtrip via Fernet, `verify_totp_code()` accepts valid code and rejects invalid, `generate_recovery_codes()` returns 10 codes, `verify_recovery_code()` matches and marks consumed, `create_provisioning_uri()` returns valid otpauth:// URI

### Implementation for User Story 3

- [X] T029 [P] [US3] Implement `apps/control-plane/src/platform/auth/mfa.py` — `generate_totp_secret() -> str` uses `pyotp.random_base32()`; `encrypt_secret(secret: str, key: str) -> str` Fernet-encrypts; `decrypt_secret(encrypted: str, key: str) -> str`; `create_provisioning_uri(secret: str, email: str) -> str` using `pyotp.TOTP(secret).provisioning_uri(email, issuer_name="Musematic")`; `verify_totp_code(secret: str, code: str) -> bool` using `pyotp.TOTP(secret).verify(code, valid_window=1)`; `generate_recovery_codes(count: int = 10) -> tuple[list[str], list[str]]` returns (raw_codes, hashed_codes) — raw = 8 uppercase alphanumeric, hashed with Argon2id; `verify_recovery_code(candidate: str, hashes: list[str]) -> int | None` returns index of matching hash
- [X] T030 [P] [US3] Extend `apps/control-plane/src/platform/auth/repository.py` — add `async get_mfa_enrollment(user_id: UUID) -> MfaEnrollment | None`; `async create_mfa_enrollment(user_id: UUID, encrypted_secret: str, recovery_hashes: list[str], expires_at: datetime) -> MfaEnrollment`; `async activate_mfa_enrollment(enrollment_id: UUID) -> None` sets status=active, enrolled_at=now; `async consume_recovery_code(enrollment_id: UUID, code_index: int, updated_hashes: list[str]) -> None`
- [X] T031 [US3] Add MFA challenge to `apps/control-plane/src/platform/auth/service.py` `login()` — after password success: check `repository.get_mfa_enrollment()` for active enrollment; if active, generate short-lived MFA token (Redis-stored, 5-minute TTL), return `MfaChallengeResponse`; add `async verify_mfa(mfa_token: str, totp_code: str) -> TokenPair` method that retrieves pending session from Redis, verifies TOTP or recovery code, then completes session creation and token issuance; add `async enroll_mfa(user_id: UUID) -> MfaEnrollResponse`; add `async confirm_mfa(user_id: UUID, totp_code: str) -> None`
- [X] T032 [US3] Extend `apps/control-plane/src/platform/auth/router.py` — add `POST /mfa/enroll` → `AuthService.enroll_mfa` (requires JWT); `POST /mfa/confirm` → `AuthService.confirm_mfa` (requires JWT); `POST /mfa/verify` → `AuthService.verify_mfa` (no JWT — uses mfa_token); emit `auth.mfa.enrolled` event on confirm

**Checkpoint**: Full MFA flow works per quickstart.md test scenario. Recovery code works once. Second use fails.

---

## Phase 7: User Story 5 — Purpose-Bound Authorization (Priority: P2)

**Goal**: Agent identities (role=`agent`) have declared purpose that constrains allowed `(resource_type, action)` pairs; purpose check runs after RBAC passes; `auth.permission.denied` with `reason="purpose_violation"` on denial

**Independent Test**: Agent with purpose `"data-analysis"` → `check_purpose("agent:data-analysis", "analytics", "read")` passes. `check_purpose("agent:data-analysis", "agent", "delete")` raises `PolicyViolationError`.

### Tests for User Story 5

- [X] T033 [P] [US5] Write `apps/control-plane/tests/unit/test_auth_purpose.py` — tests for `check_purpose_bound()` allows aligned actions, denies out-of-purpose actions, does NOT apply to non-agent identities, emits permission denied event on violation

### Implementation for User Story 5

- [X] T034 [P] [US5] Implement `apps/control-plane/src/platform/auth/purpose.py` — `PURPOSE_ACTION_MAP: dict[str, set[tuple[str, str]]]` mapping purpose strings to allowed `(resource_type, action)` sets (loaded from config or hardcoded YAML); `async check_purpose_bound(identity_type: str, agent_purpose: str | None, resource_type: str, action: str, producer: EventProducer, correlation_id: UUID) -> None`: if `identity_type != "agent"` → return (no check for humans); if `(resource_type, action)` not in `PURPOSE_ACTION_MAP.get(agent_purpose, set())` → emit `auth.permission.denied` with `reason="purpose_violation"` and raise `PolicyViolationError`
- [X] T035 [US5] Integrate purpose check into `apps/control-plane/src/platform/auth/rbac.py` `check_permission()` — after RBAC passes, call `purpose.check_purpose_bound()` if identity type is `"agent"`; caller provides `agent_purpose` from JWT claims

**Checkpoint**: Agent identities pass purpose check for aligned actions and fail with `PolicyViolationError` for out-of-purpose actions. Human users bypass purpose check entirely.

---

## Phase 8: User Story 6 — Service Account API Key Authentication (Priority: P2)

**Goal**: Service accounts authenticate via `X-API-Key: msk_...` header; keys hashed with Argon2id; rotation generates new key and invalidates old; revocation invalidates all requests; `auth.apikey.rotated` event on rotation

**Independent Test**: Create service account → API key shown once. Request with `X-API-Key` → authenticated with SA role. Rotate key → old key rejected, new key works. Revoke SA → all keys rejected.

### Tests for User Story 6

- [X] T036 [P] [US6] Write `apps/control-plane/tests/unit/test_auth_service_accounts.py` — tests for `create_service_account()` generates `msk_`-prefixed key and stores Argon2id hash, `verify_api_key()` returns credential for valid key and None for invalid, `rotate_api_key()` marks old hash as rotated and stores new hash, `revoke_service_account()` sets status=revoked

### Implementation for User Story 6

- [X] T037 [P] [US6] Extend `apps/control-plane/src/platform/auth/repository.py` — add `async get_active_service_accounts() -> list[ServiceAccountCredential]`; `async create_service_account_credential(sa_id: UUID, name: str, key_hash: str, role: str, workspace_id: UUID | None) -> ServiceAccountCredential`; `async update_service_account_key_hash(sa_id: UUID, new_hash: str, status: str) -> None`; `async get_service_account_by_id(sa_id: UUID) -> ServiceAccountCredential | None`; `async revoke_service_account(sa_id: UUID) -> None`
- [X] T038 [US6] Add service account methods to `apps/control-plane/src/platform/auth/service.py` — `async create_service_account(name: str, role: str, workspace_id: UUID | None) -> ServiceAccountCreateResponse`: generate `msk_` + `secrets.token_urlsafe(40)` key, hash with Argon2id, store credential, return response with raw key shown once; `async verify_api_key(raw_key: str) -> ServiceAccountCredential | None`: iterate active credentials and verify hash match; `async rotate_api_key(sa_id: UUID) -> str`: generate new key, update hash, mark old as rotated, emit event; `async revoke_service_account(sa_id: UUID) -> None`
- [X] T039 [US6] Add `X-API-Key` header handling to `apps/control-plane/src/platform/common/auth_middleware.py` — before JWT check, inspect `X-API-Key` header; if present, call `AuthService.verify_api_key()`; if valid, set `request.state.user` with SA identity and role; if invalid, return 401; if absent, fall through to JWT check
- [X] T040 [US6] Extend `apps/control-plane/src/platform/auth/router.py` — add `POST /service-accounts` → `AuthService.create_service_account` (requires JWT + platform_admin role); `POST /service-accounts/{sa_id}/rotate` → `AuthService.rotate_api_key`; `DELETE /service-accounts/{sa_id}` → `AuthService.revoke_service_account`

**Checkpoint**: `X-API-Key: msk_...` authenticates service account. Old key after rotation returns 401. Revoked account returns 401 for all keys.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Wire router into app factory, register events, integration tests, linting

- [X] T041 Register auth router in `apps/control-plane/src/platform/main.py` `create_app()` — `app.include_router(auth_router)` for `api` profile
- [X] T042 [P] Register all 6 auth event types in `EventTypeRegistry` — call `event_registry.register("auth.user.authenticated", UserAuthenticatedPayload)` etc. during app startup in `main.py` lifespan
- [X] T043 [P] Write `apps/control-plane/tests/integration/test_auth_login_flow.py` — full integration test against real PostgreSQL + Redis: register credential, login, use access token, refresh, logout, verify session destroyed; mark `@pytest.mark.integration`
- [X] T044 Run `ruff check apps/control-plane/src/platform/auth/ --fix` and `mypy --strict apps/control-plane/src/platform/auth/` — resolve all violations before marking complete
- [X] T045 Run `pytest apps/control-plane/tests/ -k "auth" --cov=src/platform/auth --cov-report=term-missing --cov-fail-under=95` — verify ≥95% coverage; add targeted tests for any uncovered branches

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1)**: Depends on Phase 2 — first MVP deliverable; all P1 stories can start after
- **Phase 4 (US2)**: Depends on Phase 3 (integrates into service.py login flow)
- **Phase 5 (US4)**: Depends on Phase 2; can parallelize with US1 — only needs repository pattern established
- **Phase 6 (US3)**: Depends on Phase 3 (extends service.py login); independent of US2 and US4
- **Phase 7 (US5)**: Depends on Phase 5 (RBAC must exist before purpose augments it)
- **Phase 8 (US6)**: Depends on Phase 3 (extends service.py); independent of US2/US3/US4
- **Phase 9 (Polish)**: Depends on all previous phases

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational only — delivers login, JWT, sessions
- **US2 (P1)**: Depends on US1 (extends service.py login flow with lockout)
- **US4 (P1)**: Depends on Foundational only — can parallelize with US1 (different modules)
- **US3 (P2)**: Depends on US1 (extends service.py login with MFA challenge)
- **US5 (P2)**: Depends on US4 (RBAC must exist to add purpose check)
- **US6 (P2)**: Depends on US1 (extends service.py and auth_middleware.py)

### Within Each User Story

- Tests written first (mark as failing before implementation)
- Models before repository before service before router
- Story complete and independently testable before next priority

### Parallel Opportunities

- T006, T007, T008 (US1 tests) all parallel — different test files
- T009, T010, T011 (models, password, tokens) all parallel — different files, no dependencies
- T025 (extend repository for US4) can run parallel with US1 implementation
- T033, T034 (US5) can run parallel — different files

---

## Parallel Example: User Story 1

```bash
# All tests and foundational modules can be written simultaneously:
Task T006: "Write test_auth_password.py"
Task T007: "Write test_auth_tokens.py"
Task T008: "Write test_auth_session.py"
Task T009: "Implement models.py"
Task T010: "Implement password.py"
Task T011: "Implement tokens.py"

# Then sequentially:
Task T012: "Implement session.py" (depends on AsyncRedisClient)
Task T013: "Implement repository.py" (depends on models.py)
Task T014: "Implement service.py" (depends on password, tokens, session, repository)
Task T015: "Implement router.py" (depends on service.py)
```

---

## Implementation Strategy

### MVP First (US1 + US2 — Core Login with Security)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T005)
3. Complete Phase 3: US1 (T006–T016)
4. **STOP and VALIDATE**: Login works, tokens validate, logout works
5. Complete Phase 4: US2 (T017–T022)
6. **STOP and VALIDATE**: Lockout engaged after 5 failures; audit trail populated

### Incremental Delivery

1. Setup + Foundational → Auth package ready
2. US1 → Working login + token lifecycle (MVP)
3. US2 → Brute-force protection (security hardening)
4. US4 → RBAC enforcement (authorization)
5. US3 → TOTP MFA (opt-in security upgrade)
6. US5 → Purpose-bound auth (agent-specific security)
7. US6 → Service accounts (integration/CI access)
8. Polish → Events wired, integration tests, coverage

### Note on US1 + US4 Parallelism

US4 (RBAC) depends on Foundational only — `models.py`, `schemas.py`, `repository.py` are needed, all established in US1 tasks T009 and T013. Once T009 and T013 are complete, US4 can proceed in parallel with the rest of US1 (service.py, router.py).

---

## Notes

- [P] tasks = different files, no cross-dependencies within the phase
- [Story] label maps task to user story for traceability
- All code must pass `ruff check` and `mypy --strict` continuously (not just at T044)
- `AuthAttempt` is append-only — no `updated_at`, no soft delete, no mixin beyond `UUIDMixin`
- `MfaEnrollment.recovery_codes_hash` is `JSONB` list — update the whole list when a recovery code is consumed
- Auth middleware in `common/auth_middleware.py` must be modified in T039 — coordinate to avoid conflicts with 013 scaffold tasks
- Service account API key verification iterates credentials — consider caching active hashes if performance becomes an issue
- JWT MFA token (temporary, 5-minute): store in Redis at `mfa:pending:{mfa_token}` with 5-minute TTL containing pending session state
