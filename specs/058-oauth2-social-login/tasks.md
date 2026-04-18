# Tasks: OAuth2 Social Login (Google and GitHub)

**Input**: Design documents from `specs/058-oauth2-social-login/`
**Branch**: `058-oauth2-social-login`
**Date**: 2026-04-18

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no inter-task dependencies)
- **[Story]**: User story this task belongs to (US1–US6)
- Exact file paths in every description

---

## Phase 1: Setup

No new project setup required — brownfield addition to existing auth bounded context.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema, SQLAlchemy models, Pydantic schemas, and settings that ALL user stories require before any implementation can begin.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T001 Create Alembic migration 045 with upgrade (CREATE TABLE oauth_providers, oauth_links, oauth_audit_entries + 4 indexes) and downgrade in `apps/control-plane/migrations/versions/045_oauth_providers_and_links.py`
- [x] T002 Append OAuthProvider, OAuthLink, OAuthAuditEntry SQLAlchemy model classes to `apps/control-plane/src/platform/auth/models.py` (field definitions, relationships, constraints per data-model.md)
- [x] T003 [P] Append OAuth Pydantic schemas to `apps/control-plane/src/platform/auth/schemas.py`: OAuthProviderCreate, OAuthProviderUpdate, OAuthProviderPublic, OAuthProviderAdminResponse, OAuthLinkResponse, OAuthAuthorizeResponse, OAuthAuditEntryResponse
- [x] T004 [P] Add OAuth config fields to AuthSettings in `apps/control-plane/src/platform/common/config.py`: oauth_state_secret, oauth_state_ttl (600), oauth_jwks_cache_ttl (3600), oauth_rate_limit_max (10), oauth_rate_limit_window (60)

**Checkpoint**: `alembic upgrade head` succeeds; `alembic downgrade -1` succeeds; Python imports of models and schemas raise no errors.

---

## Phase 3: User Story 1 — Administrator Configures a Provider (Priority: P1) 🎯 MVP

**Goal**: Admin can create/update a provider configuration via the API and admin settings panel, and it appears on the public providers list.

**Independent Test**: Configure Google via `PUT /api/v1/admin/oauth/providers/google` (enabled=false), verify it appears in `GET /api/v1/admin/oauth/providers` with all fields. Enable it, verify it appears in `GET /api/v1/auth/oauth/providers` public list. Disable it, verify it disappears from public list.

- [x] T005 [US1] Create OAuthRepository class with provider CRUD methods (get_provider_by_type, get_all_providers, upsert_provider) in `apps/control-plane/src/platform/auth/repository_oauth.py`
- [x] T006 [P] [US1] Append 6 OAuth event type constants and Pydantic payload models to `apps/control-plane/src/platform/auth/events.py`: AUTH_OAUTH_SIGN_IN_SUCCEEDED, AUTH_OAUTH_SIGN_IN_FAILED, AUTH_OAUTH_USER_PROVISIONED, AUTH_OAUTH_ACCOUNT_LINKED, AUTH_OAUTH_ACCOUNT_UNLINKED, AUTH_OAUTH_PROVIDER_CONFIGURED
- [x] T007 [US1] Create OAuthService class skeleton with admin methods (list_providers, upsert_provider, write_audit_entry) in `apps/control-plane/src/platform/auth/services/oauth_service.py`; upsert_provider writes oauth_audit_entries row (action='provider_configured') and publishes AUTH_OAUTH_PROVIDER_CONFIGURED Kafka event
- [x] T008 [US1] Create auth/dependencies_oauth.py with build_oauth_service factory function (same DI pattern as auth/dependencies.py:build_auth_service) in `apps/control-plane/src/platform/auth/dependencies_oauth.py`
- [x] T009 [P] [US1] Create oauth_router APIRouter with admin endpoints GET /api/v1/admin/oauth/providers and PUT /api/v1/admin/oauth/providers/{provider} in `apps/control-plane/src/platform/auth/router_oauth.py`; also add GET /api/v1/auth/oauth/providers (public, no auth) as it's needed to validate admin enable/disable
- [x] T010 [US1] Mount oauth_router in `apps/control-plane/src/platform/main.py` by adding import and app.include_router(oauth_router) after the existing app.include_router(auth_router) call (~line 748)
- [x] T011 [P] [US1] Create OAuthProviderAdminPanel.tsx React component with React Hook Form + Zod form for all provider fields (display_name, enabled, client_id, client_secret_ref, redirect_uri, scopes, domain_restrictions, org_restrictions, group_role_mapping, default_role, require_mfa) — save via PUT /api/v1/admin/oauth/providers/{provider} useMutation in `apps/web/components/features/auth/OAuthProviderAdminPanel.tsx`
- [x] T012 [US1] Add "OAuth Providers" tab to existing shadcn Tabs component in `apps/web/app/(main)/admin/settings/page.tsx` rendering OAuthProviderAdminPanel

**Checkpoint**: Admin can configure both Google and GitHub, toggle enabled/disabled, and verify the public list endpoint reflects the enabled state.

---

## Phase 4: User Story 2 — New User Signs In and Is Auto-Provisioned (Priority: P1)

**Goal**: A new user can click "Sign in with Google" or "Sign in with GitHub" on the login page, complete the provider consent flow, and receive a platform session with a newly-created user account.

**Independent Test**: Run Scenario 1 and Scenario 2 from quickstart.md (with mocked provider APIs). Verify new user in DB, oauth_link created, session cookie issued within 15 seconds.

- [x] T013 [P] [US2] Create GoogleOAuthProvider class with get_auth_url, exchange_code, validate_id_token (JWKS fetch/cache in Redis key cache:google-jwks:certs, RS256 via PyJWT + cryptography), check_domain, fetch_groups methods in `apps/control-plane/src/platform/auth/services/oauth_providers/__init__.py` (empty) and `apps/control-plane/src/platform/auth/services/oauth_providers/google.py`
- [x] T014 [P] [US2] Create GitHubOAuthProvider class with get_auth_url, exchange_code, fetch_user, fetch_emails, check_org_membership, fetch_teams methods in `apps/control-plane/src/platform/auth/services/oauth_providers/github.py`; all HTTP calls via httpx.AsyncClient(timeout=10.0), errors mapped to PlatformError
- [x] T015 [US2] Add OAuthRepository link methods (get_link_by_external, get_links_for_user, create_link, update_link_attributes, count_auth_methods) to `apps/control-plane/src/platform/auth/repository_oauth.py`
- [x] T016 [US2] Implement OAuthService.get_authorization_url (PKCE code_verifier via secrets.token_urlsafe(96), code_challenge = base64url(sha256(verifier)), state = nonce + HMAC using connectors/security.compute_hmac_sha256, store oauth:state:{nonce} in Redis TTL=oauth_state_ttl) and handle_callback (validate state + HMAC, delete state key, check provider enabled, exchange code, validate ID token/fetch user, check domain_restrictions, check org_restrictions, fetch groups, apply group_role_mapping via _resolve_role, find-or-create user + oauth_link, update external attrs, write audit entry, publish Kafka event, create_session via AuthService) in `apps/control-plane/src/platform/auth/services/oauth_service.py`
- [x] T017 [US2] Add rate_limit_callback FastAPI dependency (Redis INCR + EXPIRE on key ratelimit:oauth-callback:{ip}, raises 429 with Retry-After header when count > oauth_rate_limit_max, runs BEFORE state lookup) to `apps/control-plane/src/platform/auth/dependencies_oauth.py`
- [x] T018 [US2] Add GET /api/v1/auth/oauth/{provider}/authorize and GET /api/v1/auth/oauth/{provider}/callback (with Depends(rate_limit_callback)) endpoints to `apps/control-plane/src/platform/auth/router_oauth.py`
- [x] T019 [P] [US2] Create OAuthProviderButtons.tsx component that fetches GET /api/v1/auth/oauth/providers via TanStack Query and renders a shadcn Button per enabled provider; on click performs browser redirect to GET /api/v1/auth/oauth/{provider}/authorize; renders nothing when list is empty in `apps/web/components/features/auth/OAuthProviderButtons.tsx`
- [x] T020 [US2] Update login page to render OAuthProviderButtons below the existing login form with a divider in `apps/web/app/(auth)/login/page.tsx`

**Checkpoint**: New user clicking "Sign in with Google" (mocked provider) reaches platform home with a valid session. User row and oauth_link row exist in DB. Audit entry written with no token values.

---

## Phase 5: User Story 3 — Existing User Links an External Identity (Priority: P2)

**Goal**: An authenticated user can link a provider to their existing platform account and subsequently sign in using either their local password or the linked provider.

**Independent Test**: Run Scenario 4 from quickstart.md. Verify POST /auth/oauth/{provider}/link returns redirect_url, link flow creates oauth_link row for existing user (no duplicate user), and subsequent callback logs into existing user.

- [x] T021 [US3] Add OAuthService.get_link_authorization_url (generates state with link_for_user_id embedded) and handle_callback branch for link flows (creates/updates oauth_link for existing user, rejects if external identity already linked to a different user, writes audit entry action='account_linked') to `apps/control-plane/src/platform/auth/services/oauth_service.py`
- [x] T022 [US3] Add POST /api/v1/auth/oauth/{provider}/link endpoint (authenticated, Depends(get_current_user)) returning OAuthAuthorizeResponse redirect_url to `apps/control-plane/src/platform/auth/router_oauth.py`
- [x] T023 [P] [US3] Create ConnectedAccountsSection.tsx component showing linked providers (linked_at date) with "Link {provider}" buttons for unlinked ones; Link button calls POST /auth/oauth/{provider}/link and navigates to returned redirect_url in `apps/web/components/features/auth/ConnectedAccountsSection.tsx`

**Checkpoint**: Authenticated user can link Google or GitHub to their account. Profile shows the linked provider. Sign-out and sign-in via linked provider logs into the same existing user account.

---

## Phase 6: User Story 4 — Domain/Org Restrictions and Group-Role Mapping (Priority: P2)

**Goal**: Administrators can enforce that only users from a specific Google Workspace domain or GitHub organization can sign in, and that external group membership maps to platform roles at auto-provision time.

**Independent Test**: Run Scenarios 5, 14, 15 from quickstart.md. Domain-blocked user receives error redirect. Group-mapped user is provisioned with mapped role (not default_role). Org-blocked GitHub user receives error redirect.

- [x] T024 [US4] Add OAuthService._resolve_role helper method (iterates group_role_mapping against user's external_groups, returns matched role or provider.default_role) and ensure it is called in handle_callback before user provisioning in `apps/control-plane/src/platform/auth/services/oauth_service.py`
- [x] T025 [P] [US4] Add FR-028 compliance: call OAuthRepository.update_link_attributes on every successful sign-in to refresh external_email, external_name, external_avatar_url, external_groups so downstream role-mapping re-evaluation reflects provider's current state in `apps/control-plane/src/platform/auth/services/oauth_service.py`

**Checkpoint**: Configured domain restriction blocks sign-in from disallowed domain. Configured org restriction blocks non-member GitHub user. Group-mapped user lands with mapped role instead of default_role.

---

## Phase 7: User Story 5 — User Unlinks an External Identity (Priority: P3)

**Goal**: An authenticated user can remove a previously-linked provider from their account, provided at least one other authentication method remains.

**Independent Test**: Run Scenarios 6 and 11 from quickstart.md. User with local+Google can unlink Google (204, link row deleted). User with only Google cannot unlink (409 with clear message).

- [x] T026 [US5] Add OAuthService.unlink_account method (calls OAuthRepository.count_auth_methods, rejects with PlatformError if count ≤ 1, deletes oauth_link row, writes audit entry action='account_unlinked', publishes AUTH_OAUTH_ACCOUNT_UNLINKED Kafka event) to `apps/control-plane/src/platform/auth/services/oauth_service.py`
- [x] T027 [US5] Add DELETE /api/v1/auth/oauth/{provider}/link endpoint (authenticated, Depends(get_current_user)) to `apps/control-plane/src/platform/auth/router_oauth.py`; returns 204 on success, 409 when last auth method
- [x] T028 [US5] Add Unlink button to ConnectedAccountsSection.tsx (calls DELETE /api/v1/auth/oauth/{provider}/link via TanStack Query useMutation with ConfirmDialog; surfaces 409 as inline error "Cannot unlink: this is your only authentication method") in `apps/web/components/features/auth/ConnectedAccountsSection.tsx`

**Checkpoint**: User with two auth methods can unlink one. Platform rejects unlink when it would leave user with no auth method. Both outcomes produce correct audit entries.

---

## Phase 8: User Story 6 — Security Operator Audits OAuth Activity (Priority: P3)

**Goal**: A security operator can query all OAuth sign-in attempts (success and failure) for a user or provider, with full event details but no secret values present in any record.

**Independent Test**: Run Scenario 17 from quickstart.md (regex scan of audit entries). All 6 action types present after running Scenarios 1–6. No long token-like strings in any audit record.

- [x] T029 [US6] Audit completeness review: verify that every code path in oauth_service.py (handle_callback success, handle_callback failure, handle_link_callback, unlink_account, upsert_provider) writes an oauth_audit_entries row with correct action, outcome, source_ip, user_agent, external_id — and that no row contains client_secret, access_token, id_token, authorization_code or refresh_token values in `apps/control-plane/src/platform/auth/services/oauth_service.py`
- [x] T030 [P] [US6] Add GET /api/v1/admin/oauth/audit endpoint with query params user_id, provider_type, outcome, start_time, end_time, limit (default 50) — queries oauth_audit_entries, returns OAuthAuditEntryResponse list — to `apps/control-plane/src/platform/auth/router_oauth.py` and add get_audit_entries(filters) method to `apps/control-plane/src/platform/auth/repository_oauth.py`

**Checkpoint**: Security operator can query audit records scoped to a user or provider. No audit record contains a raw token value (verifiable by Scenario 17 automated scan).

---

## Phase 9: Polish & Cross-Cutting Concerns

- [x] T031 [P] Write PKCE unit tests (test_code_verifier_length_bounds, test_code_challenge_derivation, test_state_hmac_verification, test_state_tamper_detection) in `apps/control-plane/tests/unit/auth/test_oauth_pkce.py`
- [x] T032 [P] Write provider unit tests using respx mocks (test_google_id_token_valid, test_google_id_token_invalid_iss, test_google_id_token_expired, test_google_domain_allowed, test_google_domain_blocked, test_github_org_member, test_github_org_non_member) in `apps/control-plane/tests/unit/auth/test_oauth_providers.py`
- [x] T033 Write callback flow integration tests (test_google_new_user_provision, test_github_new_user_provision, test_returning_user_sign_in, test_stale_state_rejected, test_hmac_tamper_rejected, test_provider_disabled_mid_flow, test_duplicate_email_blocked, test_audit_entry_no_token_values) in `apps/control-plane/tests/integration/auth/test_oauth_callback_flow.py`
- [x] T034 [P] Write rate limit integration tests (test_callback_rate_limit_429_with_retry_after, test_rate_limit_does_not_consume_state) in `apps/control-plane/tests/integration/auth/test_oauth_rate_limit.py`
- [x] T035 [P] Verify frontend TypeScript compiles with no errors: `pnpm --filter web type-check` in `apps/web/`
- [ ] T036 Run full quickstart.md validation: verify all 17 scenarios pass against local dev environment
- [x] T037 Grep for any vendor-specific strings accidentally introduced: `grep -rn "MINIO\|minio" apps/control-plane/src/platform/auth/` — expected: no matches (per Critical Reminder 25)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundation (Phase 2)**: No dependencies — start immediately. BLOCKS all user stories.
- **US1 (Phase 3)**: Depends on Foundation. Can start as soon as T001–T004 complete.
- **US2 (Phase 4)**: Depends on Foundation. Can start in parallel with US1 after Foundation.
- **US3 (Phase 5)**: Depends on US2 (requires link callback logic built on handle_callback from T016).
- **US4 (Phase 6)**: Depends on US2 (T016 must be complete). T024/T025 are minor additions to existing service.
- **US5 (Phase 7)**: Depends on Foundation + OAuthRepository (T015). Independent of US2/US3/US4.
- **US6 (Phase 8)**: Depends on US2 (service methods must exist to audit). Mostly verification + one new endpoint.
- **Polish (Phase 9)**: Depends on all desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Start after Foundation. No dependency on other user stories.
- **US2 (P1)**: Start after Foundation. No dependency on US1 (provider data loaded from DB; admin must configure before testing but not before coding).
- **US3 (P2)**: Depends on US2 (T016 handle_callback flow must exist to extend for link flows).
- **US4 (P2)**: Depends on US2 (extends T016 with _resolve_role + update_link_attributes).
- **US5 (P3)**: Depends on Foundation (T001–T004). Independent of US2–US4.
- **US6 (P3)**: Depends on US2 (audit writes are part of service methods from T016).

### Parallel Opportunities Within US2

T013 (google.py) and T014 (github.py) are completely independent — run in parallel.  
T015 (repository link methods) is independent of T013/T014 — run in parallel with both.  
T019 (OAuthProviderButtons.tsx) is pure frontend — run in parallel with any backend task.

### Parallel Opportunities Within US1

T006 (events.py), T009 (router_oauth.py admin endpoints), T011 (OAuthProviderAdminPanel.tsx) are all independent — run in parallel after T005 and T007.

---

## Parallel Execution Examples

### Foundation Phase

```
# All 4 can be parallelized after T001 completes:
T001 → run first (migration must succeed before models can be imported)
T002 → after T001
T003 [P] → after T001 (no dependency on T002)
T004 [P] → independent of T002/T003
```

### US1 Phase

```
# After T005, T007, T008:
T006 [P] → events.py (independent)
T009 [P] → router_oauth.py admin endpoints
T011 [P] → OAuthProviderAdminPanel.tsx (frontend, fully independent)
```

### US2 Phase

```
# Can all start in parallel after Foundation:
T013 [P] → google.py
T014 [P] → github.py
T015 [P] → repository link methods
T019 [P] → OAuthProviderButtons.tsx (frontend, always independent)
```

---

## Implementation Strategy

### MVP (US1 + US2 only)

1. Complete Foundation (T001–T004) — ~2 hours
2. Complete US1 (T005–T012) — ~3 hours — admin can configure providers
3. Complete US2 (T013–T020) — ~4 hours — new users can sign in
4. **STOP AND VALIDATE**: Run Scenarios 1–3, 7–10 from quickstart.md
5. Deploy/demo — this is the minimum viable OAuth feature

### Full Delivery

1. Foundation + US1 + US2 = MVP (above)
2. Add US3 (T021–T023) → existing users can link accounts
3. Add US4 (T024–T025) → restrictions and group mapping verified
4. Add US5 (T026–T028) → users can unlink
5. Add US6 (T029–T030) → audit queryable
6. Polish (T031–T037) → tests + validation

Each story adds value without breaking previous stories.

---

## Notes

- [P] = different files, no inter-task dependencies, safe to run in parallel
- [Story] label maps each task to a user story for traceability
- T013 and T014 must both complete before T016 (oauth_service uses both providers)
- T016 is the most complex task (~150 lines); break into sub-steps if needed: (a) state generation, (b) state validation, (c) code exchange, (d) find-or-create, (e) session issuance
- Frontend tasks (T011, T019, T023, T028) are always independent — can be worked on by a separate developer in parallel with any backend task
- Commit after each checkpoint at minimum
