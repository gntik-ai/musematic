# Implementation Plan: OAuth2 Social Login (Google and GitHub)

**Branch**: `058-oauth2-social-login` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/058-oauth2-social-login/spec.md`

## Summary

The platform's auth bounded context currently supports only local username/password authentication. This feature adds Google and GitHub as external identity providers using the OAuth2 authorization-code-with-PKCE flow. It is fully additive — no existing auth code is modified, only extended. New files: 6 Python source files + 1 Alembic migration. Modified files: 5 targeted edits (append-only to models, schemas, events; new settings fields in config; one import+mount in main.py). Frontend: 3 UI additions (login page provider buttons, profile connected-accounts section, admin configuration panel). All dependencies (`httpx`, `PyJWT`, `cryptography`) are already in `requirements.txt`. No new Python library dependencies.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), TypeScript 5.x (frontend)  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, redis-py 5.x, httpx 0.27+, PyJWT 2.x, cryptography (JWKS RSA key parsing) — all already in requirements.txt  
**Storage**: PostgreSQL (3 new tables), Redis (3 new key patterns for state + JWKS cache + rate limit)  
**Testing**: pytest + pytest-asyncio 8.x (Python); Vitest + RTL (frontend)  
**Target Platform**: Linux / Kubernetes (same as control plane)  
**Project Type**: Brownfield feature extension — new models, service, router added to existing auth bounded context  
**Performance Goals**: SC-001/SC-002 — sign-in completes within 15 seconds. SC-008 — audit records written within 5 seconds of event.  
**Constraints**: Brownfield Rules 1–8; no rewrites; Alembic migration 045; `MINIO_*` → `S3_*` already handled by feature 057; existing local-auth flow must be unchanged; client secrets never in LLM context (Principle XI)  
**Scale/Scope**: 6 new Python files + 1 migration + 5 targeted file modifications + 3 frontend UI additions

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|---|---|---|
| Modular monolith (Principle I) | ✅ PASS | All new code lives in `auth/` bounded context; communicates with other contexts only via `AuthService.create_session()` (in-process) and `auth.events` Kafka topic |
| Dedicated data stores (Principle III) | ✅ PASS | OAuth state in Redis (short-lived hot state); JWKS cache in Redis; PostgreSQL for persistent records; no cross-store misuse |
| No cross-boundary DB access (Principle IV) | ✅ PASS | `OAuthService` accesses only `oauth_*` tables and `users` (same bounded context); no direct access to other bounded contexts' tables |
| Secrets not in LLM context (Principle XI) | ✅ PASS | `client_secret_ref` is a reference string; `OAuthProviderService.resolve_secret()` resolves at exchange time only; resolved value scoped to a single HTTP call; FR-005 enforced |
| Brownfield Rule 1 (no rewrites) | ✅ PASS | All changes are additive: append to `auth/models.py`, `auth/schemas.py`, `auth/events.py`; new `common/config.py` fields; new service/router files |
| Brownfield Rule 2 (Alembic only) | ✅ PASS | Three new tables via migration `045_oauth_providers_and_links` |
| Brownfield Rule 3 (preserve tests) | ✅ PASS | Existing auth tests unmodified; new OAuth tests added |
| Brownfield Rule 4 (use existing patterns) | ✅ PASS | Redis DI pattern from `auth/dependencies.py`; HMAC from `connectors/security.py`; event publishing from `auth/events.py`; Redis counter rate-limiting from `auth/lockout.py` |
| Brownfield Rule 5 (reference existing files) | ✅ PASS | All 5 modified files cited with line ranges in data-model.md |
| Brownfield Rule 7 (backward-compatible) | ✅ PASS | Existing `/auth/*` endpoints unchanged; new OAuth fields in settings have defaults; new OAuth config added to `AuthSettings` with defaults |
| Critical Reminder 15 (secrets) | ✅ PASS | Secret resolved by platform at runtime, never in LLM or DB as value |
| Critical Reminder 3 (no cross-boundary tables) | ✅ PASS | `users` table is owned by auth bounded context — no cross-boundary access |

**Post-design re-check**: No violations.

## Project Structure

### Documentation (this feature)

```text
specs/058-oauth2-social-login/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── rest-api.md      # Phase 1 output — 7 REST endpoint contracts
└── checklists/
    └── requirements.md  # Spec quality checklist (all pass)
```

### Source Code — What Changes

```text
apps/control-plane/src/platform/
├── auth/
│   ├── models.py                    MODIFIED — append OAuthProvider, OAuthLink,
│   │                                           OAuthAuditEntry SQLAlchemy models
│   ├── schemas.py                   MODIFIED — append OAuth Pydantic schemas
│   ├── events.py                    MODIFIED — append 6 new OAuth event types
│   ├── repository_oauth.py          NEW — OAuthRepository (DB queries for oauth tables)
│   ├── services/
│   │   ├── oauth_service.py         NEW — OAuthService (PKCE, state, find-or-create,
│   │   │                                           link/unlink, session issuance)
│   │   └── oauth_providers/
│   │       ├── __init__.py          NEW — package marker
│   │       ├── google.py            NEW — GoogleOAuthProvider (JWKS validation,
│   │       │                                           domain check, group fetch)
│   │       └── github.py            NEW — GitHubOAuthProvider (user/email/org/team APIs)
│   ├── router_oauth.py              NEW — FastAPI router (7 endpoints)
│   └── dependencies_oauth.py        NEW — build_oauth_service() + rate_limit_callback
│
├── common/
│   └── config.py                    MODIFIED — append to AuthSettings:
│                                               oauth_state_secret, oauth_state_ttl,
│                                               oauth_jwks_cache_ttl,
│                                               oauth_rate_limit_max,
│                                               oauth_rate_limit_window
│
└── main.py                          MODIFIED — import + mount oauth_router (1 import,
                                                1 include_router call after auth_router)

apps/control-plane/migrations/versions/
└── 045_oauth_providers_and_links.py NEW — creates oauth_providers, oauth_links,
                                             oauth_audit_entries tables + indexes

apps/web/
├── app/(auth)/login/
│   └── page.tsx                     MODIFIED — append provider buttons section
│                                               (conditional on /auth/oauth/providers)
├── app/(main)/admin/settings/
│   └── page.tsx                     MODIFIED — append OAuth Providers tab
└── components/features/auth/
    ├── OAuthProviderButtons.tsx      NEW — login page provider buttons
    ├── ConnectedAccountsSection.tsx  NEW — profile page link/unlink
    └── OAuthProviderAdminPanel.tsx   NEW — admin settings OAuth config panel
```

## Implementation Phases

### Phase 1: Schema Foundation (US1/US2 prerequisite)

**Goal**: New tables deployed, models and schemas available for use in later phases.

**Files**:
1. `apps/control-plane/migrations/versions/045_oauth_providers_and_links.py`:
   - `upgrade()`: `CREATE TABLE oauth_providers`, `CREATE TABLE oauth_links` (with FKs), `CREATE TABLE oauth_audit_entries`, all 4 indexes
   - `downgrade()`: `DROP TABLE oauth_audit_entries`, `DROP TABLE oauth_links`, `DROP TABLE oauth_providers` (reverse order)

2. `apps/control-plane/src/platform/auth/models.py` (append after line ~220):
   - Add `OAuthProvider(Base, UUIDMixin, TimestampMixin)` class
   - Add `OAuthLink(Base, UUIDMixin)` class with `__table_args__` for unique constraints
   - Add `OAuthAuditEntry(Base, UUIDMixin)` class
   - See data-model.md for full field definitions

3. `apps/control-plane/src/platform/auth/schemas.py` (append):
   - `OAuthProviderCreate` — request for `PUT /admin/oauth/providers/{provider}`
   - `OAuthProviderUpdate` — partial update (all fields optional except type)
   - `OAuthProviderPublic` — public response (type + display_name only)
   - `OAuthProviderAdminResponse` — full config response (ref, never resolved secret)
   - `OAuthLinkResponse` — linked provider info for profile UI
   - `OAuthAuthorizeResponse` — `{redirect_url: str}`
   - `OAuthAuditEntryResponse` — audit query response

4. `apps/control-plane/src/platform/common/config.py` (modify `AuthSettings` class):
   - Add `oauth_state_secret: str = Field(default_factory=lambda: secrets.token_hex(32))`
   - Add `oauth_state_ttl: int = 600`
   - Add `oauth_jwks_cache_ttl: int = 3600`
   - Add `oauth_rate_limit_max: int = 10`
   - Add `oauth_rate_limit_window: int = 60`

**Independent test**: `alembic upgrade head` succeeds; `alembic downgrade -1` succeeds. Python import of models + schemas raises no errors.

---

### Phase 2: Provider Libraries (US2/US4 foundation)

**Goal**: Isolated, testable provider-specific logic for Google and GitHub API calls.

**Files**:
5. `auth/services/oauth_providers/__init__.py` — empty (package marker)

6. `auth/services/oauth_providers/google.py` — `GoogleOAuthProvider` class:
   - `get_auth_url(client_id, redirect_uri, scopes, state, code_challenge)` → `str`
   - `exchange_code(client_id, client_secret, redirect_uri, code, code_verifier)` → `dict` (tokens)
   - `validate_id_token(id_token, client_id, settings)` → `dict` (claims: sub, email, name, picture, hd)
     - Fetch/cache JWKS from `cache:google-jwks:certs` (Redis TTL = `oauth_jwks_cache_ttl`)
     - Verify RS256 signature using `cryptography` + `PyJWT`
     - Verify `iss`, `aud`, `exp`, `nbf`
   - `check_domain(hd: str | None, restrictions: list[str])` → `bool`
   - `fetch_groups(access_token: str)` → `list[str]`
     - Calls `https://www.googleapis.com/oauth2/v1/tokeninfo` (or Workspace Admin SDK if scoped)
   - All HTTP calls via `httpx.AsyncClient`, timeout 10 s, errors mapped to `PlatformError`

7. `auth/services/oauth_providers/github.py` — `GitHubOAuthProvider` class:
   - `get_auth_url(client_id, redirect_uri, scopes, state)` → `str` (PKCE in GitHub uses state, challenge sent in next step)
   - `exchange_code(client_id, client_secret, code)` → `dict` (access_token)
   - `fetch_user(access_token: str)` → `dict` (id, login, name, avatar_url)
   - `fetch_emails(access_token: str)` → `str` (primary verified email)
   - `check_org_membership(access_token: str, org: str)` → `bool`
   - `fetch_teams(access_token: str, org: str)` → `list[str]`

**Independent test**: Unit test each method with `respx` (mock httpx) or `httpretty`. All provider methods callable without a live provider. PKCE challenge verifiable from code verifier.

---

### Phase 3: Core OAuth Service and Repository (US1–US6)

**Goal**: Full OAuth flow orchestration — state management, find-or-create, audit, events, link/unlink.

**Files**:
8. `auth/repository_oauth.py` — `OAuthRepository` class (async, SQLAlchemy):
   - `get_provider_by_type(provider_type: str)` → `OAuthProvider | None`
   - `get_all_providers()` → `list[OAuthProvider]`
   - `upsert_provider(data: OAuthProviderCreate)` → `OAuthProvider`
   - `get_link_by_external(provider_id: UUID, external_id: str)` → `OAuthLink | None`
   - `get_links_for_user(user_id: UUID)` → `list[OAuthLink]`
   - `create_link(user_id, provider_id, external_id, ...)` → `OAuthLink`
   - `update_link(link: OAuthLink, ...)` → `OAuthLink` (update external attrs on sign-in)
   - `delete_link(link: OAuthLink)` → `None`
   - `count_auth_methods(user_id: UUID)` → `int` (local credentials + OAuth links)
   - `create_audit_entry(...)` → `OAuthAuditEntry`

9. `auth/services/oauth_service.py` — `OAuthService` class:

   ```python
   class OAuthService:
       def __init__(
           self,
           repository: OAuthRepository,
           redis_client: AsyncRedisClient,
           settings: PlatformSettings,
           producer: EventProducer,
           auth_service: AuthService,
       ): ...

       async def get_authorization_url(
           self, provider_type: str, link_for_user_id: UUID | None = None
       ) -> OAuthAuthorizeResponse:
           # 1. Load provider, verify enabled
           # 2. Generate: nonce = token_urlsafe(32); verifier = token_urlsafe(96)
           # 3. code_challenge = base64url(sha256(verifier))
           # 4. state = f"{nonce}.{hmac(nonce, oauth_state_secret)}"
           # 5. Store oauth:state:{nonce} → {code_verifier, provider_type, link_for_user_id, created_at}  TTL=oauth_state_ttl
           # 6. Build provider auth URL with state + code_challenge

       async def handle_callback(
           self, provider_type: str, code: str, raw_state: str,
           source_ip: str, user_agent: str
       ) -> SessionToken:
           # 1. Split raw_state → nonce + hmac; verify HMAC with hmac.compare_digest
           # 2. Fetch + DELETE oauth:state:{nonce} from Redis
           # 3. Check provider still enabled
           # 4. Exchange code → tokens (provider-specific)
           # 5. Validate ID token / fetch user profile
           # 6. Apply domain / org restrictions (FR-011, FR-012)
           # 7. Fetch external groups (FR-010)
           # 8. Find link by (provider_id, external_id)
           #    OR find user by email match
           #    OR auto-provision new user
           # 9. Update external attrs (FR-028)
           # 10. Write oauth_audit_entries + publish auth.events Kafka
           # 11. If link_for_user_id → link account, return None (no new session)
           # 12. Else → auth_service.create_session(user_id) → SessionToken

       async def handle_link_callback(
           self, user_id: UUID, provider_type: str, code: str, raw_state: str
       ) -> OAuthLink:
           # Same validation flow but creates/updates link for existing user
           # Rejects if external identity already linked to different user (FR-016 edge case)

       async def unlink_account(self, user_id: UUID, provider_type: str) -> None:
           # Count auth methods; reject if count <= 1 (FR-017)
           # Delete link, write audit entry, publish event
   ```

10. `auth/events.py` (append after existing event type constants):
    ```python
    AUTH_OAUTH_SIGN_IN_SUCCEEDED = "auth.oauth.sign_in_succeeded"
    AUTH_OAUTH_SIGN_IN_FAILED    = "auth.oauth.sign_in_failed"
    AUTH_OAUTH_USER_PROVISIONED  = "auth.oauth.user_provisioned"
    AUTH_OAUTH_ACCOUNT_LINKED    = "auth.oauth.account_linked"
    AUTH_OAUTH_ACCOUNT_UNLINKED  = "auth.oauth.account_unlinked"
    AUTH_OAUTH_PROVIDER_CONFIGURED = "auth.oauth.provider_configured"
    ```
    Plus corresponding Pydantic payload models registered in the event schema registry.

**Independent test**: Scenarios 1–6, 11, 14 from quickstart.md using mocked provider APIs (`respx`). Unit test state HMAC generation and verification. Unit test PKCE challenge derivation.

---

### Phase 4: Router, Rate Limiting, and Wiring (all US)

**Goal**: Endpoints available via HTTP. Rate limiting on callback. OAuth router mounted in app.

**Files**:
11. `auth/dependencies_oauth.py`:
    - `get_redis_client(request: Request)` → `AsyncRedisClient` (same pattern as `auth/dependencies.py:26`)
    - `build_oauth_service(request, db)` → `OAuthService` (same factory pattern as `build_auth_service`)
    - `rate_limit_callback(request: Request, redis: AsyncRedisClient)` — FastAPI dependency:
      - Key = `ratelimit:oauth-callback:{request.client.host}`
      - INCR + EXPIRE within `auth.oauth_rate_limit_window`
      - If count > `auth.oauth_rate_limit_max`: raise `HTTPException(429)` with `Retry-After` header

12. `auth/router_oauth.py` — 7 endpoints as per contracts/rest-api.md:
    - `GET /api/v1/auth/oauth/providers` — public, no auth
    - `GET /api/v1/auth/oauth/{provider}/authorize` — no auth
    - `GET /api/v1/auth/oauth/{provider}/callback` — no auth, `Depends(rate_limit_callback)`
    - `POST /api/v1/auth/oauth/{provider}/link` — `Depends(get_current_user)`
    - `DELETE /api/v1/auth/oauth/{provider}/link` — `Depends(get_current_user)`
    - `GET /api/v1/admin/oauth/providers` — `Depends(require_platform_admin)`
    - `PUT /api/v1/admin/oauth/providers/{provider}` — `Depends(require_platform_admin)`

13. `apps/control-plane/src/platform/main.py` (modify, after `app.include_router(auth_router)`, ~line 748):
    ```python
    from platform.auth.router_oauth import oauth_router
    app.include_router(oauth_router)
    ```

**Independent test**: Scenarios 7, 8, 9, 12, 13, 16 from quickstart.md. Integration test with mocked providers verifies full callback round-trip returns a session cookie.

---

### Phase 5: Frontend (US1/US2/US3/US5)

**Goal**: Login page shows provider buttons; profile shows connected accounts; admin can configure providers.

**Files**:
14. `apps/web/components/features/auth/OAuthProviderButtons.tsx` (NEW):
    - Fetches `GET /api/v1/auth/oauth/providers` via TanStack Query
    - Renders a `<Button>` per provider (Google = Google icon + "Sign in with Google", etc.)
    - On click: navigates to `GET /api/v1/auth/oauth/{provider}/authorize` (browser redirect — not XHR)
    - Renders nothing if list is empty (FR-024)

15. `apps/web/app/(auth)/login/page.tsx` (MODIFY — append after existing login form):
    - Import and render `<OAuthProviderButtons />` with a divider ("or continue with")
    - Only shown when `GET /api/v1/auth/oauth/providers` returns non-empty (handled inside the component)

16. `apps/web/components/features/auth/ConnectedAccountsSection.tsx` (NEW):
    - Fetches `GET /api/v1/auth/oauth/providers` (all) and linked accounts from user profile
    - For each linked provider: shows provider name + linked date + "Unlink" button
    - "Unlink" button: confirms with `ConfirmDialog`, calls `DELETE /api/v1/auth/oauth/{provider}/link`
    - For unlinked providers: shows "Link {provider}" button → navigates to `POST /api/v1/auth/oauth/{provider}/link` redirect URL
    - Error handling: 409 (last auth method) surfaces as inline error message

17. `apps/web/components/features/auth/OAuthProviderAdminPanel.tsx` (NEW):
    - Admin panel: fetches `GET /api/v1/admin/oauth/providers`
    - For each provider: form with `client_id`, `client_secret_ref`, `redirect_uri`, `domain_restrictions`, `org_restrictions`, `group_role_mapping`, `default_role`, `require_mfa`, `enabled` toggle
    - Save: `PUT /api/v1/admin/oauth/providers/{provider}` via TanStack Query `useMutation`
    - Form validation with `React Hook Form` + `Zod` (per platform convention — feature 015)

18. `apps/web/app/(main)/admin/settings/page.tsx` (MODIFY — append new "OAuth Providers" tab):
    - New tab "OAuth Providers" in the existing 6-tab `shadcn/ui Tabs` component
    - Renders `<OAuthProviderAdminPanel />`

**Independent test**: Scenario 13, 16 from quickstart.md with MSW mocks. Login page renders provider buttons when API returns providers; renders nothing when list empty.

---

### Phase 6: Tests

**Goal**: Full test coverage for security invariants, flow correctness, and edge cases.

**Files**:
19. `apps/control-plane/tests/unit/auth/test_oauth_pkce.py`:
    - `test_code_verifier_length_bounds` — verifier 43–128 chars per RFC 7636
    - `test_code_challenge_derivation` — SHA256 base64url, no padding
    - `test_state_hmac_generation_and_verification`
    - `test_state_tamper_detection` — modified HMAC fails `compare_digest`

20. `apps/control-plane/tests/unit/auth/test_oauth_providers.py`:
    - `test_google_id_token_validation_valid`
    - `test_google_id_token_invalid_iss`
    - `test_google_id_token_expired`
    - `test_google_domain_restriction_allowed`
    - `test_google_domain_restriction_blocked`
    - `test_github_org_check_member`
    - `test_github_org_check_non_member`
    - All using `respx` mocks for httpx

21. `apps/control-plane/tests/integration/auth/test_oauth_callback_flow.py`:
    - `test_google_new_user_auto_provision` — full mock callback, verifies DB state
    - `test_github_new_user_auto_provision`
    - `test_returning_user_sign_in` — existing link, no duplicate user
    - `test_domain_restriction_rejected` — 302 to login with error
    - `test_stale_state_rejected` — deleted state → 302 error
    - `test_provider_disabled_mid_flow` — disable before callback → 302 error
    - `test_duplicate_email_collision_blocked` — email match on unlinked user → prompt
    - `test_unlink_last_method_rejected` — 409
    - `test_audit_entry_no_token_values` — regex scan on audit records

22. `apps/control-plane/tests/integration/auth/test_oauth_rate_limit.py`:
    - `test_callback_rate_limit_429_with_retry_after`
    - `test_rate_limit_does_not_consume_state`

**Independent test**: `pytest tests/unit/auth/ tests/integration/auth/ -v` all pass.

---

## API Endpoints Used / Modified

| Endpoint | Status | Change |
|---|---|---|
| `GET /api/v1/auth/oauth/providers` | New | Public provider list |
| `GET /api/v1/auth/oauth/{provider}/authorize` | New | Initiate flow, return redirect URL |
| `GET /api/v1/auth/oauth/{provider}/callback` | New | Handle callback, issue session |
| `POST /api/v1/auth/oauth/{provider}/link` | New | Initiate account linking |
| `DELETE /api/v1/auth/oauth/{provider}/link` | New | Unlink provider from account |
| `GET /api/v1/admin/oauth/providers` | New | Admin list all providers |
| `PUT /api/v1/admin/oauth/providers/{provider}` | New | Admin create/update provider |
| All existing `/api/v1/auth/*` endpoints | Existing | **Unchanged** |

---

## Dependencies

- **Feature 014 (auth bounded context)**: Direct dependency. `OAuthService` reuses `AuthService.create_session()`, Redis session store, `publish_auth_event()` from `auth/events.py`, and `AuthRepository` patterns.
- **Feature 013 (FastAPI scaffold)**: `PlatformSettings`, `app.state.clients`, dependency injection patterns, `EventProducer`.
- **Feature 027 (admin settings panel)**: New "OAuth Providers" tab added to existing admin settings tabs component.
- **Feature 016 (accounts)**: `User` model and registration state machine (existing user referenced via FK from `oauth_links.user_id`).

---

## Complexity Tracking

No constitution violations.

| Category | Count |
|---|---|
| New Python source files | 6 (repository_oauth, oauth_service, google, github, router_oauth, dependencies_oauth) + 1 package __init__.py |
| Modified Python source files | 5 (models.py, schemas.py, events.py, config.py, main.py — all targeted appends/additions) |
| New Alembic migrations | 1 (045) |
| New REST endpoints | 7 |
| New frontend components | 3 |
| Modified frontend pages | 2 (login, admin settings) |
| New library dependencies | 0 (httpx, PyJWT, cryptography already present) |
| New DB tables | 3 (oauth_providers, oauth_links, oauth_audit_entries) |
| New Redis key patterns | 3 (oauth:state:*, cache:google-jwks:*, ratelimit:oauth-callback:*) |
| New Kafka event types | 6 (all on existing auth.events topic) |
| New Kafka topics | 0 |
| New gRPC services | 0 |
