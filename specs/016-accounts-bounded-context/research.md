# Research: Accounts Bounded Context — User Registration, Lifecycle, and Invitations

**Feature**: 016-accounts-bounded-context  
**Date**: 2026-04-11  
**Phase**: 0 — Pre-design research

---

## Decision 1: Email Verification Token Storage and Format

**Decision**: Generate tokens using `secrets.token_urlsafe(32)` (256-bit entropy). Store the SHA-256 hash in the `EmailVerification` PostgreSQL table — never store the plaintext token. Send the plaintext token in the email link. Verify by hashing the submitted token and comparing to the stored hash. Default expiry: 24 hours (configurable via `ACCOUNTS_EMAIL_VERIFY_TTL_HOURS`). Tokens are single-use (marked `consumed=True` after first successful verification).

**Rationale**: Same pattern used for service account API keys in the auth context (feature 014). SHA-256 for email tokens (not Argon2id) is appropriate — these tokens are high-entropy random values, not user-chosen passwords. Storing the hash prevents a database breach from yielding usable tokens. PostgreSQL durability is needed for 24h tokens (Redis TTL imprecision + data loss risk for 24h window). The `consumed` flag + expiry check prevents replay.

**Alternatives considered**:
- JWT-signed tokens: Self-contained but cannot be revoked without a blocklist. Rejected — revocation is needed for re-send flows.
- Redis with TTL: Simpler but risks data loss and imprecise 24h TTL management. Rejected for primary storage.
- Plaintext in DB: Token breach would yield usable links. Rejected on security grounds.

---

## Decision 2: Invitation Token Storage and Format

**Decision**: Same pattern as email verification tokens — `secrets.token_urlsafe(32)` plaintext sent in invitation link, SHA-256 hash stored in `Invitation` table. Default expiry: 7 days (configurable via `ACCOUNTS_INVITE_TTL_DAYS`). Tokens are single-use. Revocation by setting `status='revoked'` on the `Invitation` record. On acceptance, status becomes `'consumed'`.

**Rationale**: Consistent with the email verification token pattern. The 7-day expiry aligns with industry norms for invitation links (long enough to be convenient, short enough to limit exposure window). Status enum (`pending`, `consumed`, `expired`, `revoked`) allows precise audit trail.

**Alternatives considered**:
- Reusing the EmailVerification model: Conceptually different entities with different actors and lifecycle. Keeping separate allows independent expiry policies and audit queries. Rejected.
- JWT invitations with embedded role claims: Cannot be revoked before expiry without a blocklist. Rejected.

---

## Decision 3: Lifecycle State Machine Implementation

**Decision**: Implement a `state_machine.py` module in `accounts/` exporting `VALID_TRANSITIONS: dict[UserStatus, set[UserStatus]]` and `validate_transition(from_status, to_status)`. The service layer calls `validate_transition` before any status change; invalid transitions raise `InvalidTransitionError` (a subclass of `PlatformError`). State machine:

```
pending_verification → pending_approval, active (no further transitions to these from outside verify flow)
pending_approval → active, archived
active → suspended, blocked, archived
suspended → active, blocked, archived
blocked → active, archived
archived → (no transitions — terminal state)
```

**Rationale**: Service-layer enforcement is consistent with the bounded context pattern — no DB triggers (which would cross the single-responsibility line), no ORM events (opaque, hard to test). The dict-based approach is testable in isolation and observable: every transition attempt is logged with from/to status and acting user.

**Alternatives considered**:
- Python-statemachine / transitions libraries: External dependency for a simple 6-state machine. Rejected — dict approach is sufficient and keeps dependencies minimal.
- DB constraints: Cannot provide actionable error messages. Rejected.
- FSM embedded in the model: Couples persistence model to business logic. Rejected.

---

## Decision 4: Cross-Boundary Session Invalidation

**Decision**: When accounts transitions a user to `suspended`, `blocked`, or `archived`, it calls `auth_service.invalidate_user_sessions(user_id: UUID)` — an in-process service interface call within the Python monolith. This is §IV-compliant: cross-boundary communication via well-defined internal service interfaces (Python function calls). The accounts service does NOT access the auth context's Redis session keys or the `user_sessions:{user_id}` set directly.

**Rationale**: Sessions are auth's domain (feature 014). Accounts must not access auth's Redis namespace or DB tables. The in-process call pattern is the correct mechanism within the modular monolith (§I, §IV). The auth service interface exposes `invalidate_user_sessions(user_id)` as a callable from sibling contexts.

**Alternatives considered**:
- Kafka event `accounts.user.suspended` → auth consumer deletes sessions: Async — creates a window where the user can still authenticate after suspension. Security-sensitive enough to require synchronous invalidation. Rejected.
- Direct Redis access from accounts: Cross-boundary violation per §IV. Rejected.

---

## Decision 5: Password Hashing and Credential Creation Delegation

**Decision**: During registration, the accounts service calls `auth_service.create_user_credential(user_id, plaintext_password)` as an in-process call. The auth context owns `UserCredential` and handles Argon2id hashing. The accounts context owns the `User` record. Password strength validation (minimum 12 chars, complexity) is enforced in `accounts/schemas.py` as a Pydantic field validator (`RegisterRequest.password`). This validates before the credential is handed to auth.

**Rationale**: The accounts context is responsible for the registration input contract (what is a valid registration?), so password strength validation belongs here. The actual cryptographic operation belongs to auth, which owns the credential storage format. This preserves bounded context ownership while avoiding code duplication.

**Alternatives considered**:
- Duplicate Argon2id hashing in accounts: auth would then be bypassed. Rejected.
- Send plaintext password to auth via Kafka event: Secrets on Kafka is a §XI violation. Rejected.
- Accounts owns the full User+Credential model: Merges authentication and account management. Spec explicitly separates them. Rejected.

---

## Decision 6: Resend Verification Rate Limiting

**Decision**: Use Redis counter `resend_verify:{user_id}` with sliding TTL. On each resend request: `INCR resend_verify:{user_id}` then `EXPIRE resend_verify:{user_id} 3600` (only on first increment — use Lua script or `SETNX`). If counter > 3, return `RateLimitError`. Rate: max 3 resends per hour (configurable via `ACCOUNTS_RESEND_RATE_LIMIT`). Redis key TTL approach provides the 1-hour sliding window.

**Rationale**: Constitution §III mandates Redis for hot state and rate limiting. The key `resend_verify:{user_id}` follows the project key pattern from CLAUDE.md (`ratelimit:{resource}:{key}`). The Lua script approach is consistent with `rate_limit_check.lua` already used for other rate limiting.

**Alternatives considered**:
- PostgreSQL timestamp query: Requires a DB query per resend attempt. Redis is the mandated caching layer. Rejected.
- In-memory dict: Shared state across workers — not viable in multi-process deployment. Rejected.

---

## Decision 7: Concurrent Approval Prevention

**Decision**: In `AccountsRepository.get_approval_request_for_update(user_id)`, use `SELECT ... FOR UPDATE` on the `User` row (or a dedicated `ApprovalRequest` row). If the status has already changed (no longer `pending_approval`), raise `ConflictError`. This provides optimistic concurrency via database row locking for the critical approval/rejection path.

**Rationale**: Email verifications, approvals, and other state transitions are idempotent check-and-update operations that must be atomic. `SELECT FOR UPDATE` within an async SQLAlchemy session provides the simplest correct concurrency guarantee without application-level locking complexity.

**Alternatives considered**:
- Redis distributed lock: Overkill for a low-frequency admin operation. Rejected.
- Optimistic locking with version column: More complex; `SELECT FOR UPDATE` is simpler for this use case. Rejected.

---

## Decision 8: Kafka Topic for Accounts Events

**Decision**: New topic `accounts.events` with key `user_id`. The accounts context produces all user lifecycle events to this topic. Event types follow the `accounts.{entity}.{action}` naming convention:
- `accounts.user.registered`
- `accounts.user.email_verified`
- `accounts.user.approved`
- `accounts.user.rejected`
- `accounts.user.activated` (emitted on first activation — triggers workspace provisioning)
- `accounts.user.suspended`
- `accounts.user.reactivated`
- `accounts.user.blocked`
- `accounts.user.unblocked`
- `accounts.user.archived`
- `accounts.user.mfa_reset`
- `accounts.user.password_reset_initiated`
- `accounts.invitation.created`
- `accounts.invitation.accepted`
- `accounts.invitation.revoked`

The workspace bounded context subscribes to `accounts.user.activated` for default workspace provisioning.

**Rationale**: Constitution §III mandates Kafka for all async event coordination. A dedicated `accounts.events` topic (not sharing `auth.events`) maintains bounded context isolation — workspace provisioning is triggered by account lifecycle, not authentication events. Adding `accounts.events` to the Kafka Topics Registry in the constitution is required as a follow-up.

**Alternatives considered**:
- Sharing `auth.events` topic: Mixes authentication events with account lifecycle events. Different consumers need different subsets. Rejected.
- Direct service call to workspace context for provisioning: Tight coupling; workspace may not be initialized. Kafka event allows async, resilient provisioning. Rejected.

---

## Decision 9: Signup Mode Configuration

**Decision**: Signup mode stored as a platform-level configuration in `PlatformSettings` via environment variable `ACCOUNTS_SIGNUP_MODE` with values `open | invite_only | admin_approval` (default: `open`). The accounts service reads this setting via dependency injection at request time. No database-backed configuration — the mode is an operational setting, not per-workspace data.

**Rationale**: Signup mode is deployment configuration, not per-request data. Environment variables are the constitution's prescribed mechanism for configuration (§ Coding Conventions). Database-backed config adds complexity without benefit for a rarely-changed setting.

**Alternatives considered**:
- Database-backed configuration table: Runtime changeability, but adds a config management bounded context dependency. Rejected.
- Per-workspace signup mode: Overcomplicated for the current scope. Spec explicitly states platform-level. Rejected.

---

## Decision 10: User Enumeration Prevention

**Decision**: The `POST /register` endpoint always returns `HTTP 202 Accepted` with the message "If this email is not already registered, a verification email has been sent" — regardless of whether the email is new or already exists. The `POST /resend-verification` endpoint similarly returns the same response regardless. The `POST /verify-email` endpoint returns `HTTP 400` with a generic "Invalid or expired token" message for both invalid tokens and tokens belonging to already-active accounts.

**Rationale**: FR-014 mandates prevention of user enumeration. Standard timing-safe design: never reveal in a response whether an email exists. This is consistent with OWASP Account Enumeration prevention guidelines.

**Alternatives considered**:
- Return 409 Conflict on duplicate registration: Reveals email existence. Rejected.
- Rate-limit without response differentiation: Does not fully prevent enumeration with careful timing. Defense-in-depth: constant responses are the primary control.

---

## Decision 11: Anti-Pattern Avoided — Accounts Does Not Own Auth Credentials

**Decision**: The `User` model in the accounts context does NOT include a `password_hash` column. Accounts owns: identity (`id`, `email`, `display_name`), lifecycle status, signup metadata. Auth (feature 014) owns: `UserCredential` with the Argon2id password hash, JWT, sessions, MFA enrollment. The `User.id` is the foreign key that links these two contexts — auth's `UserCredential.user_id` references accounts' `User.id`.

**Rationale**: Strict bounded context ownership per §IV. Auth owns credentials; accounts owns the user identity and lifecycle. This separation allows the auth context to evolve its credential storage independently (e.g., adding passkeys) without touching accounts models.

**Alternatives considered**:
- Combined User model with password_hash in accounts: Merges two bounded contexts. Rejected.
- Auth-owned User table: Auth would need to manage registration, lifecycle, invitations. Outside auth's charter. Rejected.
