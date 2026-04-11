# Research: Auth Bounded Context — Authentication, Authorization, and Session Management

**Feature**: 014-auth-bounded-context  
**Date**: 2026-04-11  
**Phase**: 0 — Pre-design research

---

## Decision 1: Password Hashing — Argon2id via argon2-cffi

**Decision**: Use `argon2-cffi` (version 23+) with the Argon2id variant and OWASP-recommended parameters: `time_cost=3`, `memory_cost=65536` (64 MiB), `parallelism=4`, `hash_len=32`, `salt_len=16`. The `PasswordHasher` class from `argon2` handles hashing and verification. Hash format follows the PHC string format (`$argon2id$v=19$m=65536,t=3,p=4$...`) stored directly in the `password_hash` column.

**Rationale**: Constitution §2.1 mandates `argon2-cffi 23+` with Argon2id. OWASP recommends Argon2id with the above parameters as the gold standard for password hashing. The PHC string format is self-describing — it embeds algorithm, version, and parameters, allowing future parameter upgrades without database schema changes. `argon2-cffi` provides `needs_rehash()` for transparent parameter migration on next login.

**Alternatives considered**:
- bcrypt: Weaker against GPU attacks; constitution mandates Argon2id. Rejected.
- scrypt: Less widely adopted; constitution mandates Argon2id. Rejected.
- Custom parameters (higher memory): 64 MiB balances security vs. server memory under concurrent logins. Can be tuned per deployment.

---

## Decision 2: JWT Token Pair — RS256 with Access + Refresh Pattern

**Decision**: Upon successful authentication, issue two JWTs:

- **Access token**: RS256-signed, 15-minute expiry, contains `sub` (user_id UUID), `email`, `roles` (list of workspace-role mappings), `session_id`, `iat`, `exp`. Stateless verification — no Redis lookup required.
- **Refresh token**: RS256-signed, 7-day expiry, contains `sub`, `session_id`, `jti` (unique token ID), `iat`, `exp`. On refresh, the `jti` is checked against Redis to ensure the session is still active and the refresh token hasn't been revoked.

Token refresh produces a new access token only (refresh token is reused until expiry or rotation). On logout, the session is deleted from Redis, which invalidates both the refresh token (jti check fails) and effectively any new access token issuance.

**Rationale**: Constitution mandates `PyJWT 2.x` with RS256. Access tokens are short-lived and stateless to minimize Redis lookups on every request. Refresh tokens are validated against Redis to support session revocation. The `session_id` in both tokens links them to the Redis session, enabling logout-all by deleting all sessions for a user.

**Alternatives considered**:
- HS256 symmetric signing: Constitution mandates RS256. Rejected.
- Access token with Redis check on every request: Adds latency to every request; defeats the purpose of JWTs. Rejected — only refresh checks Redis.
- Rotating refresh tokens (new refresh token on each refresh): Adds complexity; single refresh token per session is sufficient with session-based revocation. Rejected for v1.

---

## Decision 3: Session Storage — Redis Hash per Session

**Decision**: Each session is stored as a Redis hash at key `session:{user_id}:{session_id}`. Fields: `user_id`, `email`, `roles_json`, `device_info`, `ip_address`, `created_at`, `last_activity`, `refresh_jti`. TTL set to 7 days (matching refresh token expiry). Sessions are created on login and deleted on logout.

To support logout-all, maintain a Redis set at `user_sessions:{user_id}` containing all `session_id` values. On logout-all, iterate and delete all session hashes, then delete the set.

**Rationale**: Constitution mandates Redis for all caching and hot state (Principle III). Redis hashes provide O(1) field access. Per-session keys with TTL ensure automatic cleanup. The `user_sessions` set enables efficient logout-all without scanning.

**Alternatives considered**:
- PostgreSQL session table: Violates constitution Principle III (use Redis for sessions, not PostgreSQL). Rejected.
- Single Redis key per user with JSON blob: Doesn't support per-device session management. Rejected.
- JWT blacklist approach: Grows unbounded until tokens expire; session-based is cleaner. Rejected.

---

## Decision 4: TOTP MFA — pyotp with Encrypted Storage

**Decision**: Use `pyotp` (version 2.x) to generate TOTP secrets (20 bytes, base32-encoded). The TOTP provisioning URI is generated via `pyotp.TOTP(secret).provisioning_uri(email, issuer_name="Musematic")`. The secret is encrypted at rest using Fernet symmetric encryption (key from `AUTH_MFA_ENCRYPTION_KEY` environment variable) before storing in PostgreSQL. Recovery codes: generate 10 codes, each 8 alphanumeric characters, stored as Argon2id hashes (one-way — original shown to user once).

Enrollment flow: (1) User calls `/mfa/enroll` → generates secret + recovery codes, stores encrypted secret and hashed recovery codes with `status=pending`. (2) User verifies with a TOTP code from their app via `/mfa/verify` → status changes to `active`. (3) Pending enrollments expire after 10 minutes (background cleanup).

**Rationale**: Constitution mandates `pyotp 2.x`. Encrypting the TOTP secret at rest prevents an attacker with database read access from generating valid TOTP codes. Recovery codes are one-way hashed so they cannot be recovered even from the database. Fernet is included in `cryptography` (already a dependency of `argon2-cffi`).

**Alternatives considered**:
- Store TOTP secret in plaintext: Database breach would compromise all MFA. Rejected.
- Hardware security module for TOTP secrets: Overkill for this stage; Fernet encryption is sufficient. Rejected for v1.
- WebAuthn/FIDO2: Valuable but separate feature; TOTP covers 90%+ of MFA needs. Deferred.

---

## Decision 5: RBAC Permission Model — Predefined Matrix in Code

**Decision**: The 10 roles are defined as a Python enum. Permissions are stored as `RolePermission` rows in PostgreSQL with columns: `role` (enum), `resource_type` (string), `action` (string, e.g., `read`, `write`, `delete`, `admin`), `scope` (enum: `global`, `workspace`, `own`). The permission matrix is seeded via Alembic migration.

The RBAC check function: `async def check_permission(user_roles: list[UserRole], resource_type: str, action: str, workspace_id: UUID | None) -> bool`. For each role the user holds in the target workspace, check if a matching `RolePermission` exists. Superadmin bypasses all checks.

**Roles**: `superadmin`, `platform_admin`, `workspace_owner`, `workspace_admin`, `creator`, `operator`, `viewer`, `auditor`, `agent`, `service_account`.

User-to-role mapping is stored in `UserRole` table: `user_id`, `role`, `workspace_id` (nullable for global roles like superadmin). A user can hold multiple roles across workspaces.

**Rationale**: Predefined roles in code + seeded permissions provide fast lookups (O(1) via in-memory cache after startup) and prevent accidental permission drift. The permission matrix is auditable via migration history. Workspace-scoped roles follow the multi-tenant architecture.

**Alternatives considered**:
- Dynamic role creation via API: Adds complexity and risk of permission sprawl. Deferred to a future feature per spec assumptions.
- Attribute-based access control (ABAC): More flexible but significantly more complex to implement and reason about. RBAC covers the defined requirements. Rejected for v1.
- Permissions stored in Redis: Permissions change infrequently; PostgreSQL is the source of truth, cached in memory on startup. Rejected.

---

## Decision 6: Purpose-Bound Authorization — Declarative Purpose Mapping

**Decision**: Agent purpose is stored in the `AgentProfile` (owned by the Registry bounded context, not Auth). The Auth context receives the agent's declared purpose via the JWT claims or a cross-context service call. Purpose-to-action mapping is defined as a configuration: each purpose string maps to a set of allowed `(resource_type, action)` tuples.

The purpose check function: `async def check_purpose_bound(agent_purpose: str, resource_type: str, action: str) -> bool`. This is called AFTER RBAC passes, only for agent-type identities (not human users). If the action is not in the purpose's allowed set, a `PolicyViolationError` is raised.

**Rationale**: Purpose-bound authorization is an additional layer per the spec (supplements RBAC, both must pass). Loading purpose mappings from configuration keeps the Auth context decoupled from the Registry context — it doesn't need to query the agent profile table directly (respecting Principle IV: no cross-boundary DB access).

**Alternatives considered**:
- Free-text purpose matching via LLM: Non-deterministic; security decisions must be deterministic. Rejected.
- Purpose stored in Auth context: Would duplicate agent profile data, violating bounded context ownership. Rejected.
- Purpose check in middleware: Too early in the request lifecycle; needs resource_type and action context. Must be called from the service layer. Rejected.

---

## Decision 7: Service Account API Keys — Prefixed, Hashed, Single-Use Display

**Decision**: API keys are generated as `msk_` + 40 bytes of `secrets.token_urlsafe(40)`, yielding approximately 53 characters. The raw key is shown to the administrator exactly once at creation time. The stored form is an Argon2id hash of the full key (including prefix). On each request, the system hashes the provided key and compares against stored hashes.

Key rotation: Generate a new key, store its hash, mark the old key hash as `rotated` (immediately invalid). Revocation: Mark the credential as `revoked`, delete associated session data.

API keys are submitted via `X-API-Key` header. The auth middleware checks this header before JWT — if present, it takes precedence.

**Rationale**: The `msk_` prefix allows immediate identification of key type in logs and alerts without revealing the key. Hashing with Argon2id ensures compromised database doesn't expose usable keys. `secrets.token_urlsafe` provides cryptographically secure randomness. 40 bytes provides 320 bits of entropy — well beyond brute-force feasibility.

**Alternatives considered**:
- Store API keys encrypted (reversible): Encryption key compromise exposes all keys. Hashing is one-way and safer. Rejected.
- SHA-256 hash for API key storage: Faster but weaker against targeted attacks. Argon2id is consistent with password hashing approach. Rejected.
- OAuth2 client credentials flow: More complex; API keys are simpler for machine-to-machine auth. Deferred.

---

## Decision 8: Account Lockout — Redis Counter with TTL

**Decision**: Failed login attempts are tracked in Redis at key `auth:lockout:{user_id}` as a simple integer counter with TTL equal to the lockout duration (default: 15 minutes). On each failed attempt: increment counter. If counter reaches the threshold (default: 5), set a separate key `auth:locked:{user_id}` with TTL = lockout duration. On successful login: delete both keys.

The login flow checks `auth:locked:{user_id}` first — if it exists, immediately reject without attempting password verification. This prevents timing attacks (password hash computation takes ~100ms with Argon2id).

**Rationale**: Redis provides atomic increment and TTL-based expiration. No background job needed for lockout cleanup — Redis handles it. Separate locked key prevents the counter from decrementing during the lockout window. Checking the locked key before password verification avoids CPU waste on locked accounts.

**Alternatives considered**:
- PostgreSQL-based lockout: Adds write load to PostgreSQL on every failed attempt. Redis is designed for this. Rejected per Principle III.
- In-memory counter: Not shared across control plane replicas. Rejected.
- Sliding window rate limit: More complex; simple counter with TTL covers the spec requirement. Rejected for v1.

---

## Decision 9: Auth Events — Kafka Canonical Envelope

**Decision**: The Auth context publishes events to the `auth.events` Kafka topic using the canonical `EventEnvelope` from `common/events/envelope.py`. Event types:

| Event Type | Payload | When |
|---|---|---|
| `auth.user.authenticated` | `{user_id, session_id, ip, device}` | Successful login |
| `auth.user.locked` | `{user_id, attempt_count, locked_until}` | Account lockout triggered |
| `auth.session.revoked` | `{user_id, session_id, reason}` | Logout or logout-all |
| `auth.mfa.enrolled` | `{user_id, method: "totp"}` | MFA enrollment completed |
| `auth.permission.denied` | `{user_id, resource_type, action, reason}` | RBAC or purpose-bound denial |
| `auth.apikey.rotated` | `{service_account_id}` | API key rotation |

All events carry `CorrelationContext` with `correlation_id` and optionally `workspace_id`. Events are registered in the `EventTypeRegistry` with Pydantic schemas for payload validation.

**Rationale**: Constitution mandates Kafka for all async event coordination and canonical EventEnvelope for all events. These events enable the audit bounded context to build a complete security audit trail without direct database access to the auth context (Principle IV).

**Alternatives considered**:
- Direct database writes to audit tables: Violates Principle IV (cross-boundary DB access). Rejected.
- HTTP callbacks: Less reliable than Kafka. Rejected.
- Redis Pub/Sub: Not durable; messages lost if consumer is down. Rejected.

---

## Decision 10: Auth Attempt Logging — PostgreSQL Append-Only Table

**Decision**: Every authentication attempt (success or failure) is recorded in the `auth_attempts` table in PostgreSQL. Columns: `id` (UUID), `user_id` (UUID nullable — null for unknown emails), `email` (string), `ip_address` (string), `user_agent` (string), `outcome` (enum: `success`, `failure_password`, `failure_locked`, `failure_mfa`), `created_at` (timestamp). This table is append-only within the auth bounded context. No updates, no deletes.

**Rationale**: FR-015 requires recording all authentication attempts with timestamp, origin, and user agent. PostgreSQL is the system-of-record for structured audit data. Append-only ensures audit integrity. The `user_id` is nullable to record attempts with unknown emails (for detecting enumeration attacks).

**Alternatives considered**:
- ClickHouse for auth attempts: ClickHouse is for analytics aggregations, not transactional audit records. Auth attempts need ACID guarantees. Rejected per Principle III.
- Kafka-only (no PostgreSQL): Kafka is for event streaming; the auth context needs to query its own attempt history (e.g., for lockout counter verification). Rejected.

---

## Decision 11: Password Reset Tokens — Short-Lived, Hash-Stored

**Decision**: Password reset tokens are generated as `secrets.token_urlsafe(32)` (256 bits of entropy). The raw token is sent to the user (via email, handled by Notifications context). The stored form is a SHA-256 hash (not Argon2id — reset tokens are single-use and short-lived, so fast hashing is acceptable). Columns: `id`, `user_id`, `token_hash`, `expires_at` (default: 1 hour), `consumed_at` (nullable). On password reset: verify hash match, check not expired, check not consumed, update password, mark consumed.

**Rationale**: Password reset tokens are ephemeral and single-use. SHA-256 is sufficient since the token has high entropy (256 bits) and short lifetime. Argon2id would add unnecessary latency for a non-reusable credential. Storing the hash prevents token recovery from database access.

**Alternatives considered**:
- Argon2id hash for reset tokens: Unnecessarily slow for ephemeral, high-entropy tokens. Rejected.
- JWT-based reset tokens: Would require blacklisting on consumption; database-stored hash is simpler. Rejected.
