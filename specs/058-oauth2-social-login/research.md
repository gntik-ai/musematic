# Research: OAuth2 Social Login (Google and GitHub)

**Phase 0 output for**: [plan.md](plan.md)  
**Date**: 2026-04-18  
**Feature**: specs/058-oauth2-social-login

## D-01: Alembic Migration Number

- **Decision**: Migration `045` — file `apps/control-plane/migrations/versions/045_oauth_providers_and_links.py`
- **Rationale**: Latest migration is `044_ibor_and_decommission.py` (feature 056). Three new tables (`oauth_providers`, `oauth_links`, `oauth_audit_entries`) go in one migration because `oauth_links` FKs into `oauth_providers` — they must be created atomically.
- **Alternatives considered**: One migration per table — rejected; FK dependency between `oauth_links` → `oauth_providers` requires joint deployment.

## D-02: Model File Placement

- **Decision**: Append OAuth models (`OAuthProvider`, `OAuthLink`, `OAuthAuditEntry`) to the existing `auth/models.py`.
- **Rationale**: Brownfield Rule 1 (no rewrites) + Rule 4 (use existing patterns). `auth/models.py` is the flat-file convention for this bounded context. Creating `auth/models/` would require renaming the existing file and updating every import in tests and services. The `registry/` bounded context uses a `models/` subdirectory, but it was designed that way from day 1 — auth was not.
- **Alternatives considered**: `auth/models/oauth.py` with `__init__.py` re-export — requires structural refactoring touching all import paths. Rejected.

## D-03: Schema File Placement

- **Decision**: Append OAuth Pydantic schemas to the existing `auth/schemas.py`.
- **Rationale**: Same reasoning as D-02. `auth/schemas.py` exists as a flat file; the flat-file pattern is the auth bounded context convention.
- **Alternatives considered**: `auth/schemas/oauth.py` — same structural-refactoring concern. Rejected.

## D-04: Redis Key Schema for OAuth State

- **Decision**: Key = `oauth:state:{state_token}` where `state_token` is `secrets.token_urlsafe(32)`. Value: JSON `{code_verifier, provider_type, created_at}`. TTL: `AUTH_OAUTH_STATE_TTL` (default 600 s). State integrity is verified via a separate HMAC field embedded in the state URL parameter: `{state_token}.{hmac}`. HMAC = `HMAC-SHA256(state_token, OAUTH_STATE_SECRET)[:16]`.
- **Rationale**: Follows `ratelimit:{resource}:{key}` and `auth:mfa:{token}` patterns already in `common/clients/redis.py` and `auth/`. Single-use: entry deleted immediately on first successful validation (FR-006). TTL enforces the stale-session edge case.
- **Alternatives considered**: PostgreSQL session table — requires cleanup job; Redis TTL is the established auth-state pattern. Nonce-only without HMAC — no integrity protection; rejected.

## D-05: Google JWKS Caching

- **Decision**: Cache Google JWKS JSON in Redis at key `cache:google-jwks:certs` with TTL = `AUTH_OAUTH_JWKS_CACHE_TTL` (default 3600 s). On cache miss or unknown key ID, refresh from Google's discovery endpoint (`https://www.googleapis.com/oauth2/v3/certs`) via `httpx.AsyncClient` and re-cache.
- **Rationale**: Follows existing `cache:{context}:{key}` Redis pattern. Per-process in-memory caching violates Principle III / Critical Reminder 7 (shared state in Redis). 1-hour TTL balances freshness vs. latency. Key-ID miss handles graceful key rotation without waiting for full TTL expiry.
- **Alternatives considered**: PyJWT `jwks_client` — additional external dependency; `httpx` + Redis is already available and follows established patterns.

## D-06: PKCE Implementation

- **Decision**: Stdlib-only:
  ```python
  code_verifier = secrets.token_urlsafe(96)  # 128-char base64url, within RFC 7636 bounds
  digest = hashlib.sha256(code_verifier.encode()).digest()
  code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
  ```
- **Rationale**: No new dependency. `secrets`, `hashlib`, `base64` are stdlib. FR-007.
- **Alternatives considered**: `pkce` library — adds a dependency for 3 lines of code; rejected.

## D-07: HMAC State Signing

- **Decision**: Reuse `compute_hmac_sha256()` from `apps/control-plane/src/platform/connectors/security.py` (same monolith — in-process call per Principle I). State URL parameter = `{nonce}.{compute_hmac_sha256(oauth_state_secret, nonce.encode())}`. Verification: split on `.`, recompute HMAC, compare with `hmac.compare_digest`.
- **Rationale**: The utility already exists; deduplication follows Rule 4.
- **Alternatives considered**: Duplicate HMAC helper in auth module — violates DRY. `itsdangerous` library — new dependency for functionality already present.

## D-08: Callback Rate Limiting

- **Decision**: Redis counter per source IP, key `ratelimit:oauth-callback:{ip}`, INCR + EXPIRE within a fixed window. Implemented as a FastAPI dependency injected into the callback route. Limit defaults: `AUTH_OAUTH_RATE_LIMIT_MAX=10`, `AUTH_OAUTH_RATE_LIMIT_WINDOW=60`. Returns 429 with `Retry-After` header. Rate check happens **before** any state lookup so rejection does not consume state (FR-020).
- **Rationale**: Existing brute-force counter in `auth/lockout.py` uses the same Redis INCR + EXPIRE pattern. Avoids adding `slowapi` as a new dependency.
- **Alternatives considered**: `slowapi` — new dependency; Redis counter is established. Per-user limits — state is not yet associated with a user at callback time; per-IP is the correct axis.

## D-09: Session Issuance After OAuth

- **Decision**: After successful callback validation, call the existing `AuthService.create_session(user_id)` (or equivalent internal method in `auth/services/auth_service.py`) to issue a platform session token. `OAuthService` receives an `AuthService` instance via dependency injection at construction time.
- **Rationale**: FR-018 requires OAuth sessions to be indistinguishable from local-auth sessions. Reusing the existing factory satisfies this with no duplication — session format, TTL, Redis backing, and downstream RBAC checks are identical.
- **Alternatives considered**: Duplicate session creation logic in OAuthService — violates DRY and would diverge over time. Rejected.

## D-10: Kafka Event Topic

- **Decision**: Publish OAuth lifecycle events to the **existing** `auth.events` topic via the existing `publish_auth_event()` in `auth/events.py`. New event types: `auth.oauth.sign_in_succeeded`, `auth.oauth.sign_in_failed`, `auth.oauth.user_provisioned`, `auth.oauth.account_linked`, `auth.oauth.account_unlinked`, `auth.oauth.provider_configured`.
- **Rationale**: `auth.events` is the established topic for all authentication lifecycle events (FR-026). Adding OAuth types keeps consumers simple. No new Kafka topic, no Strimzi chart changes.
- **Alternatives considered**: New `oauth.events` topic — operational overhead for no architectural gain; rejected.

## D-11: Audit Record Persistence

- **Decision**: New `oauth_audit_entries` PostgreSQL table. Written synchronously within the request handler **before** the response is returned. Additionally published to Kafka (fire-and-forget). No background job.
- **Rationale**: SC-008 requires audit records within 5 seconds; synchronous DB write guarantees this even during Kafka lag. Pattern matches `AuthAttempt` in `auth/models.py` which records login attempts in the same request.
- **Alternatives considered**: Kafka-only — cannot guarantee 5-second SLA under consumer lag. OpenSearch direct write — adds complexity; PostgreSQL is the system of record.

## D-12: Client Secret Reference Resolution

- **Decision**: `client_secret_ref` stores a resolution reference string (e.g., `k8s:platform-control/oauth-google/client-secret`). `OAuthProviderService.resolve_secret(ref: str) -> str` resolves it at exchange time using the existing Kubernetes secret-resolution mechanism already in the platform. The resolved value exists only within the token-exchange HTTP call scope — never logged, stored in memory, or returned in any response.
- **Rationale**: FR-005. Consistent with IBOR connector's `credential_refs` pattern introduced in feature 056. Vault integration is explicitly Out of Scope in the spec.
- **Alternatives considered**: Vault — out of scope. Plaintext in DB — explicitly prohibited by FR-005.

## D-13: Dependency Injection for OAuthService

- **Decision**: Follow the exact pattern from `auth/dependencies.py` (lines 26–41): `_get_redis_client(request)` reads from `request.app.state.clients["redis"]`; `build_oauth_service(request, db)` constructs `OAuthService` with repository, redis_client, settings, producer, and auth_service.
- **Rationale**: Brownfield Rule 4 (use existing patterns). Every other service in the platform uses this same dependency factory pattern.
