# Tasks: UPD-042 — User-Facing Notification Center and Self-Service Security

**Feature**: 092-user-notification-self-service
**Branch**: `092-user-notification-self-service`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — User reviews missed notifications via `<NotificationBell>` (existing 152-line component upgraded) + `/notifications` inbox + filters + bulk mark-all-read.
- **US2 (P1)** — User configures notification preferences via event × channel matrix (6 channels per spec correction §1) + digest mode + quiet hours + mandatory events forced-on.
- **US3 (P1)** — Developer manages personal API tokens via `/settings/api-keys` with MFA step-up + one-time display + max-10 limit per Rule 31.
- **US4 (P1)** — User enrolls in MFA via dedicated `/settings/security/mfa` page (existing backend endpoints reused per spec correction §4).
- **US5 (P2)** — User revokes a stolen session via `/settings/security/sessions` (per-session revoke + revoke-others; current-session-refusal per design D7).
- **US6 (P1)** — User submits self-service GDPR DSR via `/settings/privacy/dsr` (same backing service as admin-DSR per design D8).
- **US7 (P2)** — User revokes consent via `/settings/privacy/consent` with consequences dialog + history tab.

Independent-test discipline: every US MUST be verifiable in isolation. US1 = 15 seeded `UserAlert` rows + bell badge + inbox pagination. US2 = matrix UI persists + mandatory events locked + quiet hours bypass for critical. US3 = MFA step-up + one-time display + revocation propagation. US4 = stepper enrollment + backup codes + admin-policy disable refusal. US5 = list rendering + per-session revoke ≤ 60s + current-session refusal. US6 = identical row to admin-DSR + audit `source=self_service`. US7 = revoke + consequences dialog + history.

**Wave-17 sub-division** (per plan.md "Effort & Wave"):
- W17.0 — Setup: T001-T004
- W17A — Track A Backend `/me/*` aggregator + extensions (depends on UPD-040 + UPD-041 / Waves 15-16): T005-T036
- W17B — Track B Frontend pages + `<NotificationBell>` upgrade (depends on Track A schemas): T037-T079
- W17C — Track C E2E + journey extensions: T080-T093
- W17D — Cross-cutting verification (Rule 31 + Rule 46 + audit emission): T094-T097
- W17E — SC verification + documentation polish: T098-T108

---

## Phase 1: Setup

- [X] T001 [W17.0] Verify the on-disk repo state per plan.md "Phase 0 — Research" + spec.md scope-discipline section: confirm UPD-040 (Wave 15) + UPD-041 (Wave 16) are on `main`; confirm `apps/control-plane/src/platform/common/secret_provider.py` exists; confirm `apps/web/components/features/alerts/notification-bell.tsx` is 152 lines with full implementation per research R1 (NOT a placeholder per spec correction §6); confirm `apps/control-plane/src/platform/notifications/router.py:20-84` has the existing 6 `/me/alerts*` endpoints; confirm `apps/control-plane/src/platform/auth/router.py:88-109` has `/logout` + `/logout-all` endpoints; confirm `apps/control-plane/src/platform/auth/session.py` has `delete_session` + `delete_all_sessions` but NO `list_sessions_by_user` per research R6; confirm migration sequence at `069_oauth_provider_env_bootstrap.py` so `070` is the next slot per research R10. Document inventory in `specs/092-user-notification-self-service/contracts/repo-inventory.md` (NEW file). If UPD-040 OR UPD-041 is NOT merged, BLOCK UPD-042 implementation per spec correction §7.
- [X] T002 [P] [W17.0] Verify the constitutional anchors per plan.md Constitutional Anchors table: open `.specify/memory/constitution.md` and confirm Rule 9 (PII audit), Rule 30 (admin role gates — NOT applicable to `/me/*`), Rule 31 (lines 203-207 — never log secrets), Rule 34 (impersonation double-audit), Rule 41 (AA accessibility), Rule 45 (lines 258-262 — every user-facing backend capability has UI), Rule 46 (lines 263-267 — `/me/*` endpoints scoped to current_user, no user_id parameter). If any rule has been renumbered or rewritten, escalate via spec amendment. Document confirmation in `specs/092-user-notification-self-service/contracts/constitution-confirmation.md` (NEW file).
- [X] T003 [P] [W17.0] Verify the migration sequence per research R10: open `apps/control-plane/migrations/versions/` and confirm the highest existing migration number; if UPD-040/UPD-041's migrations have shifted past 069 (because UPD-040 may own multiple slots), document the actual next sequence in `specs/092-user-notification-self-service/contracts/migration-sequence.md` (NEW file). UPD-042's migration uses the verified next sequence (default `070`; may shift to `071`+).
- [X] T004 [P] [W17.0] Cross-feature coordination check per plan.md "Cross-feature dependency map": confirm UPD-036 (Administrator Workbench — feature 086) admin equivalents are on `main`; confirm UPD-037 (Public Signup — feature 087) consent capture is on `main`; confirm UPD-077 (Multi-Channel Notifications) has shipped 6 deliverers per spec correction §1 (verified at `notifications/deliverers/` per research §1); confirm UPD-039 (Documentation — feature 089) status — if landed, runbooks land in `docs/operator-guide/`; if not landed, runbooks live in `specs/092-user-notification-self-service/contracts/` per design D14. Document in `specs/092-user-notification-self-service/contracts/cross-feature-deps.md` (NEW file).

---

## Phase 2: Track A — Backend `/me/*` Aggregator + Extensions

**Story goal**: NEW `me/router.py` aggregator (16 endpoints) + 1 endpoint on existing notifications router; Alembic migration `070` (3 JSONB columns on `UserAlertSettings` + 1 column on `service_account_credentials`); `RedisSessionStore.list_sessions_by_user` extension; `AuditChainService.list_entries_by_actor_or_subject` extension; 10 new audit-event types; FR-657 + Rule 9 + Rule 31 + Rule 45 + Rule 46 honored.

### Alembic migration

- [X] T005 [W17A] [US1, US2, US3] Create `apps/control-plane/migrations/versions/070_user_self_service_extensions.py` (or the verified next-sequence number from T003) per plan.md design D2 + D13: 3 ALTER TABLE statements adding NEW JSONB columns to `user_alert_settings` per spec correction §7 — `per_channel_preferences: JSONB DEFAULT '{}'` (event_type → list of enabled channels), `digest_mode: JSONB DEFAULT '{}'` (channel → "immediate" / "hourly" / "daily"), `quiet_hours: JSONB DEFAULT NULL` (`{start_time, end_time, timezone}`). 1 ALTER TABLE adding `created_by_user_id: UUID FK to users.id NULLABLE` to `service_account_credentials` per spec correction §3 + design D3. Reversible downgrade.
- [ ] T006 [W17A] Run `alembic upgrade head` locally against a test DB; verify the migration applies cleanly with existing rows preserved (per spec correction §5 — backward-compat default values); verify `alembic downgrade -1` removes the 4 columns without data loss per SC-019.

### Model + repository extensions

- [X] T007 [W17A] [US1, US2] Modify `apps/control-plane/src/platform/notifications/models.py:51-79` per plan.md design D2: add 3 new mapped columns on `UserAlertSettings` — `per_channel_preferences: Mapped[dict[str, list[str]]] = mapped_column(JSONB, default=dict)`, `digest_mode: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)`, `quiet_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)`. Preserve the existing 3 columns (`state_transitions`, `delivery_method`, `webhook_url`) unchanged for backward compatibility.
- [X] T008 [W17A] [US3] Modify `apps/control-plane/src/platform/auth/models.py:111-129` per plan.md design D3: add `created_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)` to `ServiceAccountCredential`. Preserve the existing 7 columns unchanged.
- [X] T009 [W17A] [US5] Modify `apps/control-plane/src/platform/auth/session.py` per plan.md design D6 + research R6: add NEW method `async def list_sessions_by_user(self, user_id: UUID) -> list[dict[str, Any]]:` on `RedisSessionStore`. Implementation queries the existing `user_sessions:{user_id}` Redis set, fetches each session's detail via the existing `get_session(user_id, session_id)`, sorts by `last_activity` DESC. Returns a list of dicts containing all session metadata (device_info, ip_address, created_at, last_activity, refresh_jti) — but EXCLUDES the `refresh_jti` from the public response shape per Rule 31 (only the existing internal use of refresh_jti is preserved; the response shape is sanitized by the service-layer per T013).
- [ ] T010 [W17A] [US3] Verify the existing `service_account_service.py` exists at `apps/control-plane/src/platform/auth/services/` (verify during T010 — may live under `auth/service.py` instead). Add NEW user-self methods per plan.md design D4 + D5: `async def create_for_current_user(self, user_id, name, scopes, expiry, mfa_token) -> ServiceAccountCredential` (validates max-10-per-user count via SQL + scope-subset enforcement against user's permissions + MFA step-up if `current_user.mfa_enrolled`); `async def list_for_current_user(self, user_id) -> list[ServiceAccountCredential]` (filters `WHERE created_by_user_id = :user_id`); `async def revoke_for_current_user(self, user_id, sa_id) -> None` (validates ownership before revoke).
- [X] T011 [W17A] [US7] Modify `apps/control-plane/src/platform/privacy_compliance/services/consent_service.py` per research R7: add NEW public methods `async def list_for_user(self, user_id) -> list[PrivacyConsentRecord]` (returns all consents for the user); `async def list_history_for_user(self, user_id) -> list[ConsentHistoryEntry]` (returns chronological grants + revocations). The existing `revoke(user_id, consent_type)` method is reused unchanged.
- [X] T012 [W17A] [US6] Modify `apps/control-plane/src/platform/privacy_compliance/services/dsr_service.py` per research R8 + plan.md design D8: add NEW public method `async def list_for_subject(self, subject_user_id, limit, cursor) -> list[DSRResponse]` (cursor-based pagination over user's own DSRs). The existing `create_request(payload, requested_by)` method is reused unchanged for self-service per design D8.
- [X] T013 [W17A] [US5] Modify `apps/control-plane/src/platform/auth/services/auth_service.py` (verify exact path during T013) per plan.md design D7: add NEW methods `async def list_user_sessions(self, user_id) -> list[SessionDetail]` (delegates to T009's `list_sessions_by_user`; sanitizes the response shape — strips `refresh_jti` per Rule 31; computes city-level geolocation from `ip_address` for the public response); `async def revoke_session_by_id(self, user_id, session_id, current_session_id) -> None` (refuses with `ValueError("cannot revoke current session")` if `session_id == current_session_id` per design D7); `async def revoke_other_sessions(self, user_id, current_session_id) -> int` (bulk revoke ALL EXCEPT current; returns count).
- [X] T014 [W17A] [US-FR657] Modify `apps/control-plane/src/platform/audit/service.py` per research R9 + plan.md design D9: add NEW method `async def list_entries_by_actor_or_subject(self, actor_id: UUID | None, subject_id: UUID | None, start_ts: datetime | None, end_ts: datetime | None, limit: int, cursor: str | None) -> tuple[list[AuditChainEntry], str | None]` (returns entries + next_cursor). OR-semantics: `WHERE actor_id = :actor_id OR subject_id = :subject_id` per design D9.
- [X] T015 [W17A] [US-FR657] Modify `apps/control-plane/src/platform/audit/repository.py` per research R9: add the underlying SQL query for T014's new method. Cursor-based pagination via composite cursor `(timestamp DESC, id DESC)`. Verify a composite index `idx_audit_chain_actor_subject_ts ON audit_chain_entries (actor_id, subject_id, timestamp DESC)` exists or add it via the same Alembic migration `070`.

### `me/` BC: aggregator router + Pydantic schemas + service

- [X] T016 [W17A] Create `apps/control-plane/src/platform/me/__init__.py` (NEW empty module).
- [X] T017 [W17A] Create `apps/control-plane/src/platform/me/schemas.py` (NEW per plan.md "Source Code" section): all Pydantic request/response schemas for the 16 new endpoints — `UserSessionListResponse`, `UserSessionDetail`, `RevokeOtherSessionsResponse`, `UserServiceAccountListResponse`, `UserServiceAccountCreateRequest`, `UserServiceAccountCreateResponse` (returns one-time API key value per design D10 + Rule 31), `UserServiceAccountSummary` (no key value), `UserConsentListResponse`, `UserConsentRevokeRequest`, `UserConsentHistoryResponse`, `UserDSRSubmitRequest` (no `subject_user_id` field — auto-filled per Rule 46), `UserDSRListResponse`, `UserDSRDetailResponse`, `UserActivityListResponse`, `UserActivityCursor`, `UserNotificationPreferencesResponse`, `UserNotificationPreferencesUpdateRequest`, `UserNotificationTestResponse`. Validators: mandatory events server-side check per design D11 + FR-651.
- [X] T018 [W17A] Create `apps/control-plane/src/platform/me/service.py` (NEW per plan.md "Source Code" section): orchestrator `MeService` that delegates to existing services (`AuthService`, `ConsentService`, `DSRService`, `NotificationsService`, `AuditChainService`, `ServiceAccountService`) per spec scope discipline. Each public method takes `current_user_id: UUID` from the dependency-injected JWT claims; NEVER accepts a `user_id` parameter from request body or query string per Rule 46.
- [X] T019 [W17A] Create `apps/control-plane/src/platform/me/router.py` (NEW per plan.md design D1) with FastAPI `APIRouter(prefix="/me", tags=["me"])` declaration. All endpoints depend on `Depends(get_current_user)` per Rule 46; NO `Depends(require_admin)` or `Depends(_require_platform_admin)`. Helper function `_user_id(current_user) -> UUID` reuses the pattern from `notifications/router.py:24-25` (verified per research R2).

### Sessions endpoints (US5)

- [X] T020 [W17A] [US5] Add `GET /me/sessions` endpoint to `me/router.py` per FR-654: handler `async def list_user_sessions(current_user, me_service)`; calls `me_service.list_sessions(current_user_id)` which internally calls T013's `auth_service.list_user_sessions`; returns `UserSessionListResponse` with the current session marked via `is_current=True` flag (compared to `current_user.session_id` from JWT).
- [X] T021 [W17A] [US5] Add `DELETE /me/sessions/{session_id}` endpoint per FR-654 + design D7: handler validates `session_id != current_user.session_id` (refuses with HTTP 400 + clear error if equal); calls `me_service.revoke_session(current_user_id, session_id, current_session_id)`; emits `auth.session.revoked` audit entry per spec correction §10 + Rule 9.
- [X] T022 [W17A] [US5] Add `POST /me/sessions/revoke-others` endpoint per FR-654: handler calls `me_service.revoke_other_sessions(current_user_id, current_session_id)`; emits `auth.session.revoked_all_others` audit entry; returns count of sessions revoked.

### Service-account self-service endpoints (US3)

- [X] T023 [W17A] [US3] Add `GET /me/service-accounts` endpoint per FR-652: handler calls `me_service.list_service_accounts(current_user_id)`; returns `UserServiceAccountListResponse` with metadata only (no api_key values, only hash prefixes for identification per Rule 31).
- [ ] T024 [W17A] [US3] Add `POST /me/service-accounts` endpoint per FR-652 + plan.md design D4 + D5 + D10: handler validates max-10-per-user + scope-subset + MFA step-up via `me_service.create_service_account(...)`. On success, returns `UserServiceAccountCreateResponse` containing the raw API key value ONCE per design D10 (the response is the ONLY time the value is exposed). Subsequent `GET` calls return only hash prefix (`msk_...3a4f` for identification). Emits `auth.api_key.created` audit entry with `created_by=user_self` source classification.
- [X] T025 [W17A] [US3] Add `DELETE /me/service-accounts/{sa_id}` endpoint per FR-652: handler validates ownership via `created_by_user_id = current_user.id` per design D3; rejects with 404 if not found OR not owned. Emits `auth.api_key.revoked` audit entry. Revocation propagates within 5 seconds per SC-009 (the existing service-account auth-check reads from DB; revoked rows fail immediately).

### Consent self-service endpoints (US7)

- [X] T026 [W17A] [US7] Add `GET /me/consent` endpoint per FR-655: handler calls `me_service.list_consents(current_user_id)`; returns `UserConsentListResponse` with type, granted_at, version, current state per `PrivacyConsentRecord` model.
- [X] T027 [W17A] [US7] Add `POST /me/consent/revoke` endpoint per FR-655: handler validates the consent exists for the user; calls existing `consent_service.revoke(user_id, consent_type)` per research R7; emits `privacy.consent.revoked` audit entry per spec correction §8.
- [X] T028 [W17A] [US7] Add `GET /me/consent/history` endpoint per FR-655: handler calls T011's `consent_service.list_history_for_user(current_user_id)`; returns chronological grants + revocations.

### DSR self-service endpoints (US6)

- [X] T029 [W17A] [US6] Add `POST /me/dsr` endpoint per FR-656 + plan.md design D8 + Rule 46: handler calls existing `dsr_service.create_request(payload, requested_by=current_user.id)` with `subject_user_id=current_user.id` AUTO-PRE-FILLED (the request schema NEVER accepts `subject_user_id` per Rule 46). For erasure type, requires typed-confirmation field `confirm_text == "DELETE"` (validated server-side); returns 400 if not present per spec edge case. Emits `privacy.dsr.submitted` audit entry with `source=self_service` per spec correction §8 + §10.
- [X] T030 [W17A] [US6] Add `GET /me/dsr` endpoint per FR-656: handler calls T012's `dsr_service.list_for_subject(subject_user_id=current_user.id, limit, cursor)`; cursor-based pagination.
- [X] T031 [W17A] [US6] Add `GET /me/dsr/{dsr_id}` endpoint per FR-656: handler validates ownership (`subject_user_id == current_user.id`); rejects with 404 (NOT 403 — per Rule 46 to avoid information leakage) if not found OR not owned.

### Activity endpoint (FR-657)

- [X] T032 [W17A] Add `GET /me/activity` endpoint per FR-657 + plan.md design D9: handler calls T014's `audit_service.list_entries_by_actor_or_subject(actor_id=current_user.id, subject_id=current_user.id, ...)` with OR-semantics; cursor-based pagination; filter params `start_ts`, `end_ts`, `event_type`. Returns sanitized response (no PII exposure beyond what the audit chain already records).

### Notification preferences extended endpoints (US2)

- [X] T033 [W17A] [US2] Add `GET /me/notification-preferences` endpoint per FR-651: handler reads from extended `UserAlertSettings` per T007; returns `UserNotificationPreferencesResponse` with the 3 new JSONB columns + the 3 existing columns for backward compatibility.
- [X] T034 [W17A] [US2] Add `PUT /me/notification-preferences` endpoint per FR-651 + plan.md design D11: handler validates the request body — for events in the mandatory-list (`security.*`, `incidents.*`), REJECTS any payload that disables all channels per design D11 (server-side defense-in-depth, NOT just UI lock); on success, updates the JSONB columns + emits `notifications.preferences.updated` audit entry per spec correction §8.
- [X] T035 [W17A] [US2] Add `POST /me/notification-preferences/test/{event_type}` endpoint per FR-651 + User Story 2 acceptance scenario 4: handler triggers a synthetic `UserAlert` for the user via the existing `NotificationsService` (which routes through the user's preferences for that event type). Returns success + delivery method. NO audit entry (test-only path).

### Mark-all-read endpoint (US1)

- [X] T036 [W17A] [US1] Add `POST /me/alerts/mark-all-read` endpoint to the EXISTING `apps/control-plane/src/platform/notifications/router.py` per plan.md design D1 + FR-649: handler calls `notifications_service.mark_all_read(user_id)` which sets `read=true` on all `UserAlert` rows for the user. Returns count. NOTE: this endpoint lives in `notifications/router.py` (NOT `me/router.py`) per BC ownership of `/me/alerts*`. The router is registered at `main.py:1622` per research R5.

### Wire `me_router` + audit-event types + CI gate

- [X] T037 [W17A] Modify `apps/control-plane/src/platform/main.py`: add `from platform.me.router import router as me_router` import; register via `app.include_router(me_router, prefix="/api/v1")` AFTER the existing notifications router registration at line ~1622 per research R5.
- [ ] T038 [W17A] [US1, US3, US5, US6, US7] Wire 10 new audit-event types per spec correction §8 across the relevant services (T013, T024, T027, T029, etc.): `auth.session.revoked`, `auth.session.revoked_all_others`, `auth.api_key.created`, `auth.api_key.revoked`, `auth.mfa.enrolled` (self-service), `auth.mfa.disabled` (self-service), `auth.mfa.recovery_codes_regenerated`, `privacy.consent.revoked` (self-service), `privacy.dsr.submitted` (self-service with `source=self_service`), `notifications.preferences.updated`. Each follows the existing dual-emission pattern (`repository.create_audit_entry` + `publish_auth_event`) per research R6.
- [X] T039 [W17A] Author CI static-analysis check at `scripts/check-me-endpoint-scope.py` per Rule 46: scans all routers under `apps/control-plane/src/platform/`; identifies endpoints with `prefix="/me"` OR path containing `/me/`; rejects any handler that declares a parameter named `user_id` (in path, query, or body). Exit code 1 on violation. Wire into CI as new job in `ci.yml` per UPD-040's `check-secret-access.py` pattern. Author 4-6 pytest cases at `scripts/tests/test_check_me_endpoint_scope.py`.
- [X] T040 [W17A] Run `python scripts/check-me-endpoint-scope.py` against the in-flight Track A code; verify zero violations. The 17 new endpoints all use `current_user` from the JWT-injected dependency, never accept `user_id` from request data.

### Track A integration tests

- [ ] T041 [W17A] [US1, US2, US3, US4, US5, US6, US7] Create `apps/control-plane/tests/me/test_router.py` (NEW pytest test file): ~30 cases covering 16 endpoints — happy-path success, 401 on no auth, 400 on validation error (missing field, invalid format), correct response shape, audit-emission verification (synthetic test asserts the `audit_chain_entries` row count grows by exactly 1 per state-changing call), Rule 46 verification (synthetic test attempts to pass `user_id` parameter; verify rejection).
- [ ] T042 [W17A] [US5] Create `apps/control-plane/tests/me/test_session_revocation.py` (NEW): ~10 cases — list rendering with current-session badge, per-session revoke success, current-session revoke refusal per design D7, bulk revoke-others (current preserved), propagation verification (Redis key deleted within 5 seconds), 401 on revoked session's next request.
- [ ] T043 [W17A] [US3] Create `apps/control-plane/tests/me/test_service_account_self_service.py` (NEW): ~10 cases — create with MFA step-up, max-10-per-user limit per design D4, scope-subset rejection per spec edge case, one-time display per design D10 + Rule 31 (response contains api_key once; subsequent GETs do not), revocation immediate effect per SC-009.
- [ ] T044 [W17A] [US7] Create `apps/control-plane/tests/me/test_consent_self_service.py` (NEW): ~6 cases — list, revoke with audit emission, history rendering, revoke unknown consent (404), revoke same consent twice (idempotent or error per spec choice).
- [ ] T045 [W17A] [US6] Create `apps/control-plane/tests/me/test_dsr_self_service.py` (NEW): ~8 cases — submission auto-fills subject_user_id per Rule 46, identical row to admin-DSR per design D8 + spec correction §10, audit `source=self_service` verified, erasure typed-confirmation requirement per spec edge case, list pagination, ownership verification on `GET /me/dsr/{id}` (404 on unowned).
- [ ] T046 [W17A] [US-FR657] Create `apps/control-plane/tests/me/test_activity_query.py` (NEW): ~6 cases — actor_id-only query, subject_id-only query, OR-semantics combined, cursor pagination, time-window filter, event-type filter.
- [ ] T047 [W17A] [US2] Create `apps/control-plane/tests/me/test_notification_preferences.py` (NEW): ~10 cases — get/put round-trip, mandatory event server-side rejection per design D11, quiet hours timezone roundtrip, digest mode roundtrip, test-notification triggers synthetic alert.

**Checkpoint (end of Phase 2)**: `pytest apps/control-plane/tests/me/` passes (~80 unit tests); the new aggregator router is reachable at `/api/v1/me/*`; the static-analysis check passes; the migration is reversible; 10 new audit-event types emit correctly via the dual-emission pattern.

---

## Phase 3: Track B — Frontend Pages + `<NotificationBell>` Upgrade

**Story goal**: 9 NEW Next.js pages + 1 component upgrade per FR-649 through FR-657 + Rule 45. ~30 sub-components. i18n × 6 locales. axe-core AA per Rule 41.

### `<NotificationBell>` upgrade (US1)

- [X] T048 [W17B] [US1] Modify `apps/web/components/features/alerts/notification-bell.tsx` per plan.md research R1 + design D5 (frontend): change the `useAppQuery` call's `limit` parameter from `20` to `5` for the dropdown query (per FR-650 — dropdown shows 5 most recent). Add a "See all" link at the bottom of the dropdown navigating to `/notifications`. Verify the existing `useAlertFeed` WebSocket hook continues to deliver real-time unread-count updates via the existing `ALERTS` channel (no code change there). Net diff: ~30 lines.
- [X] T049 [W17B] [US1] Verify the existing `Header.tsx:8` import + line 57 render of `<NotificationBell/>` per research R3 — NO changes to Header.tsx required.

### Shared API + schemas + hooks

- [ ] T050 [W17B] Create `apps/web/lib/api/me.ts` (NEW): fetch wrappers for all 17 new endpoints. Each wrapper uses the existing `apiClient` pattern + Zod schema validation on response.
- [ ] T051 [W17B] Create `apps/web/lib/schemas/me.ts` (NEW): Zod schemas mirroring backend Pydantic per Track A T017. Re-export for use in TanStack Query hooks.
- [ ] T052 [W17B] Create `apps/web/lib/hooks/use-me-sessions.ts` (NEW): TanStack Query hooks `useUserSessions()`, `useRevokeSession()`, `useRevokeOtherSessions()`. Uses optimistic updates for revocation (immediate UI feedback; rollback on error).
- [ ] T053 [P] [W17B] Create `apps/web/lib/hooks/use-me-api-keys.ts` (NEW): hooks `useUserApiKeys()`, `useCreateApiKey()`, `useRevokeApiKey()`. The create hook handles MFA step-up via re-attempt with `mfa_token` field.
- [ ] T054 [P] [W17B] Create `apps/web/lib/hooks/use-me-consent.ts` (NEW): hooks `useUserConsents()`, `useRevokeConsent()`, `useConsentHistory()`.
- [ ] T055 [P] [W17B] Create `apps/web/lib/hooks/use-me-dsr.ts` (NEW): hooks `useUserDSRs()`, `useUserDSR(id)`, `useSubmitDSR()`. The submit hook handles erasure typed-confirmation.
- [ ] T056 [P] [W17B] Create `apps/web/lib/hooks/use-me-activity.ts` (NEW): hook `useUserActivity()` with `useInfiniteQuery` for cursor pagination.
- [ ] T057 [P] [W17B] Create `apps/web/lib/hooks/use-me-notification-preferences.ts` (NEW): hooks `useNotificationPreferences()`, `useUpdateNotificationPreferences()`, `useTestNotification()`.
- [ ] T058 [P] [W17B] Create `apps/web/lib/hooks/use-me-alerts-bulk.ts` (NEW): hook `useMarkAllRead()` for the bulk action on the inbox.

### `/notifications` inbox page (US1)

- [ ] T059 [W17B] [US1] Create `apps/web/app/(main)/notifications/page.tsx` (NEW per FR-649): full inbox (~250 lines). Reads from existing `GET /me/alerts` with cursor pagination + filters (date range, channel, severity, event type, read state). Bulk actions: mark all read (calls T036's new endpoint via T058 hook); archive (future enhancement — out of scope per spec).
- [ ] T060 [W17B] Create `apps/web/app/(main)/notifications/_components/NotificationFilters.tsx` (NEW ~150 lines): filter sidebar with shadcn `Select` + `DateRangePicker` + `Checkbox` group. URL-param persistence via Next.js `useSearchParams`.
- [ ] T061 [P] [W17B] Create `apps/web/app/(main)/notifications/_components/NotificationListItem.tsx` (NEW ~80 lines): reusable row with title, body excerpt, timestamp, severity icon, read-state indicator. Reusable in both inbox + bell dropdown per spec Key Entities.
- [ ] T062 [P] [W17B] Create `apps/web/app/(main)/notifications/_components/NotificationBulkActions.tsx` (NEW ~100 lines): bulk-select + mark-all-read button. Optimistic update on the bell badge + cross-tab sync via existing WebSocket per research R12 + plan.md design D? (no design — verified in T087).

### `/settings/notifications` preferences page (US2)

- [ ] T063 [W17B] [US2] Create `apps/web/app/(main)/settings/notifications/page.tsx` (NEW ~250 lines): preferences matrix UI. Reads from `GET /me/notification-preferences`; saves via `PUT /me/notification-preferences`.
- [ ] T064 [W17B] [US2] Create `apps/web/app/(main)/settings/notifications/_components/EventChannelMatrix.tsx` (NEW ~300 lines): 6-channel × N-event matrix UI (the 6 channels per spec correction §1: `in_app`, `email`, `webhook`, `slack`, `teams`, `sms`). Mandatory events (`security.*`, `incidents.*`) UI-locked with tooltip per design D11; backend enforces server-side per T034.
- [ ] T065 [P] [W17B] [US2] Create `apps/web/app/(main)/settings/notifications/_components/QuietHoursForm.tsx` (NEW ~120 lines): timezone-aware time-range picker. Stores `{start_time, end_time, timezone}` per design D2 + D12.
- [ ] T066 [P] [W17B] [US2] Create `apps/web/app/(main)/settings/notifications/_components/DigestModeSelect.tsx` (NEW ~80 lines): per-channel select (`immediate` / `hourly` / `daily`). Stores `{channel: mode}` per design D2.
- [ ] T067 [P] [W17B] [US2] Create `apps/web/app/(main)/settings/notifications/_components/TestNotificationButton.tsx` (NEW ~80 lines): per-event-type test action. Calls `POST /me/notification-preferences/test/{event_type}` via T057 hook.

### `/settings/api-keys` page (US3)

- [ ] T068 [W17B] [US3] Create `apps/web/app/(main)/settings/api-keys/page.tsx` (NEW ~250 lines): list + create modal + revoke. Reads from `GET /me/service-accounts`; max-10 limit displayed.
- [ ] T069 [W17B] [US3] Create `apps/web/app/(main)/settings/api-keys/_components/ApiKeyCreateDialog.tsx` (NEW ~200 lines): MFA step-up dialog + scope picker (subset of user's permissions per spec edge case) + expiry select (default 90 days, max 1 year). Handles 401 `mfa_required` response by triggering MFA challenge dialog.
- [ ] T070 [W17B] [US3] Create `apps/web/app/(main)/settings/api-keys/_components/ApiKeyOneTimeDisplay.tsx` (NEW ~120 lines) per Rule 31 + plan.md design D10: token value rendered ONCE in a `<CodeBlock>` with prominent copy + warning copy "This is the only time you'll see this value". Clear-on-dismiss behaviour.
- [ ] T071 [P] [W17B] [US3] Create `apps/web/app/(main)/settings/api-keys/_components/ApiKeyTable.tsx` (NEW ~150 lines): list with columns (name, scope, created_at, last_used_at, expires_at, revoke action). Disabled "Create" button at the 10-key limit per design D4.

### `/settings/security` overview + MFA + sessions + activity (US4, US5, FR-657)

- [ ] T072 [W17B] Create `apps/web/app/(main)/settings/security/page.tsx` (NEW ~150 lines): security overview page with 3 link cards (MFA, Sessions, Activity).
- [ ] T073 [W17B] [US4] Create `apps/web/app/(main)/settings/security/mfa/page.tsx` (NEW ~250 lines): enrollment flow + status panel + regenerate-backup-codes + disable-MFA. Reads from existing MFA endpoints at `/api/v1/auth/mfa/*` per spec correction §4.
- [ ] T074 [W17B] [US4] Create `apps/web/app/(main)/settings/security/mfa/_components/MfaEnrollFlow.tsx` (NEW ~250 lines): stepper component (4 steps): enable → QR + text secret + manual-entry fallback → TOTP confirmation → backup codes display. Calls existing `POST /api/v1/auth/mfa/enroll` + `POST /api/v1/auth/mfa/confirm`.
- [ ] T075 [P] [W17B] [US4] Create `apps/web/app/(main)/settings/security/mfa/_components/QRCodeDisplay.tsx` (NEW ~80 lines): renders QR code via `qrcode.react` (verify in `package.json` during T075; if not present, add). Includes text-secret fallback for manual entry per FR-653.
- [ ] T076 [P] [W17B] [US4] Create `apps/web/app/(main)/settings/security/mfa/_components/BackupCodesDisplay.tsx` (NEW ~120 lines) per Rule 31: one-time render with copy + download actions. Clear-on-dismiss behaviour.
- [ ] T077 [P] [W17B] [US4] Create `apps/web/app/(main)/settings/security/mfa/_components/DisableMfaDialog.tsx` (NEW ~150 lines): password + TOTP step-up dialog. Backend refuses with 403 if admin policy enforces MFA per spec correction §13; UI surfaces clear error.
- [ ] T078 [W17B] [US5] Create `apps/web/app/(main)/settings/security/sessions/page.tsx` (NEW ~200 lines): session list + per-session revoke + bulk revoke-others. Reads from `GET /me/sessions` via T052 hook.
- [ ] T079 [W17B] [US5] Create `apps/web/app/(main)/settings/security/sessions/_components/SessionList.tsx` (NEW ~180 lines): list with device-type icon, user-agent summary, city-level geolocation, created-at, last-active. Current-session "This session" badge per design D7. Per-session revoke disabled on current row.
- [ ] T080 [P] [W17B] [US-FR657] Create `apps/web/app/(main)/settings/security/activity/page.tsx` (NEW ~200 lines): user audit trail with cursor pagination. Reads from `GET /me/activity` via T056 hook (`useInfiniteQuery`).
- [ ] T081 [P] [W17B] [US-FR657] Create `apps/web/app/(main)/settings/security/activity/_components/ActivityFilters.tsx` (NEW ~120 lines): filter by event type + date range.

### `/settings/privacy/consent` + `/settings/privacy/dsr` (US6, US7)

- [ ] T082 [W17B] [US7] Create `apps/web/app/(main)/settings/privacy/consent/page.tsx` (NEW ~200 lines): consent list + revoke + history tab. Reads from `GET /me/consent` via T054 hook.
- [ ] T083 [W17B] [US7] Create `apps/web/app/(main)/settings/privacy/consent/_components/ConsentCard.tsx` (NEW ~120 lines): per-consent card with type, granted_at, version, current state, revoke action.
- [ ] T084 [W17B] [US7] Create `apps/web/app/(main)/settings/privacy/consent/_components/RevokeConsentDialog.tsx` (NEW ~150 lines): consequences dialog per consent type ("Revoking ai_interaction will disable agent interactions, conversations, and reasoning features. You can re-grant consent at any time").
- [ ] T085 [P] [W17B] [US7] Create `apps/web/app/(main)/settings/privacy/consent/_components/ConsentHistoryTab.tsx` (NEW ~150 lines): chronological grants + revocations from `GET /me/consent/history`.
- [ ] T086 [W17B] [US6] Create `apps/web/app/(main)/settings/privacy/dsr/page.tsx` (NEW ~200 lines): DSR list + submission. Reads from `GET /me/dsr` via T055 hook; submission via `POST /me/dsr`.
- [ ] T087 [W17B] [US6] Create `apps/web/app/(main)/settings/privacy/dsr/_components/DsrSubmissionForm.tsx` (NEW ~250 lines): multi-step form with 6 GDPR rights (access, rectification, erasure, portability, restriction, objection). Erasure step requires typed-confirmation field (`Type DELETE to confirm permanent erasure`) per spec edge case + plan.md design D8 + T029 server-side validation. Active-executions warning per spec edge case.
- [ ] T088 [P] [W17B] [US6] Create `apps/web/app/(main)/settings/privacy/dsr/_components/DsrStatusList.tsx` (NEW ~150 lines): list of pending + past DSRs with status badges + filed-at + completed-at.

### i18n + accessibility

- [ ] T089 [W17B] [US1, US2, US3, US4, US5, US6, US7] Modify `apps/web/messages/en.json` per plan.md research R10: add ~80 new i18n keys under `notifications.{inbox,preferences}`, `apiKeys.*`, `security.{mfa,sessions,activity}`, `privacy.{consent,dsr}` namespaces. Reference these in all new TSX components via `useTranslations(...)` from `next-intl`.
- [ ] T090 [P] [W17B] Modify `apps/web/messages/{de,es,fr,it,zh-CN}.json`: copy English keys with TODO-translation markers per UPD-088's parity check; vendor translates per UPD-039 / FR-620. The 7-day grace window applies. Note: per spec correction §6 the FR-620 6-locale set excludes `ja` for the docs site — but UI catalogs include `ja` (legacy from feature 083). This task updates all 6 locale files including `ja.json`.
- [ ] T091 [P] [W17B] Run `pnpm test:i18n-parity` (UPD-088's parity check) — verify all 6 locale catalogs have all new keys; flag missing.
- [ ] T092 [W17B] Run axe-core scan on all 9 new pages locally (`pnpm dev` + browser scan); verify zero AA violations per Rule 41 inheritance from UPD-083. Fix any violations introduced by the new sub-components (likely candidates: dialog focus management, table keyboard navigation, badge contrast).
- [ ] T093 [W17B] Run `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm test:i18n-parity` to verify all CI gates pass.

### Playwright E2E

- [ ] T094 [W17B] [US1, US2, US3, US4, US5, US6, US7] Create `apps/web/tests/e2e/self-service-pages.spec.ts` (NEW Playwright test file): ~25 scenarios covering: (a) `<NotificationBell>` renders with correct unread count + dropdown shows 5 most recent + "See all" link navigates to `/notifications`; (b) `/notifications` filters server-side + bulk mark-all-read updates badge; (c) `/settings/notifications` matrix saves + mandatory events UI-locked + quiet hours roundtrip; (d) `/settings/api-keys` create with MFA step-up + one-time display + revoke immediate; (e) `/settings/security/mfa` stepper + backup codes + regenerate + disable; (f) `/settings/security/sessions` list + per-session revoke + current-session refusal; (g) `/settings/security/activity` cursor pagination; (h) `/settings/privacy/consent` revoke with consequences + history; (i) `/settings/privacy/dsr` submission + erasure typed-confirmation; (j) cross-tab badge sync verification per SC-003.

**Checkpoint (end of Phase 3)**: 9 new pages render correctly against the live Track A backend; `<NotificationBell>` shows 5 most recent + See-all link; `pnpm test`, `pnpm typecheck`, axe-core scan, i18n parity check all pass; Playwright E2E ~25 scenarios pass.

---

## Phase 4: Track C — E2E Suite + Journey Extensions

**Story goal**: NEW `tests/e2e/suites/self_service/` with 8 test files; J03 + J10 journey extensions; matrix-CI inheritance from UPD-040.

### E2E suite scaffolding

- [ ] T095 [W17C] [US1, US2, US3, US4, US5, US6, US7] Create `tests/e2e/suites/self_service/__init__.py` + `conftest.py` (NEW pytest fixtures): `logged_in_user_with_alerts` (seeds 15 `UserAlert` rows for the test user before yield), `mfa_enabled_user` (creates user + completes MFA enrollment + yields auth headers), `multi_session_user` (synthetic Redis seed for 3 active sessions), `consented_user` (signup-flow result with all 3 consents granted), `clean_self_service_state` (resets between tests).
- [ ] T096 [W17C] [US1] Create `tests/e2e/suites/self_service/test_notification_inbox.py` (NEW): 5 cases per spec User Story 1 — bell badge accuracy, dropdown rendering, inbox pagination + filters, bulk mark-all-read, drill-down navigation.
- [ ] T097 [P] [W17C] [US2] Create `tests/e2e/suites/self_service/test_notification_preferences.py` (NEW): 6 cases per spec User Story 2 — matrix UI persists, mandatory events server-side rejection per design D11, quiet hours bypass for critical, digest mode roundtrip, test-notification action, all-channels-disabled-on-mandatory rejection (defense-in-depth verification).
- [ ] T098 [P] [W17C] [US3] Create `tests/e2e/suites/self_service/test_api_keys.py` (NEW): 5 cases per spec User Story 3 — MFA step-up + one-time display + max-10 + scope-subset rejection + revocation propagation ≤ 5s per SC-009.
- [ ] T099 [P] [W17C] [US4] Create `tests/e2e/suites/self_service/test_mfa_enrollment.py` (NEW): 5 cases per spec User Story 4 — stepper flow + backup codes one-time + regenerate with TOTP step-up + disable refused under admin policy + audit emission for each.
- [ ] T100 [P] [W17C] [US5] Create `tests/e2e/suites/self_service/test_session_revocation.py` (NEW): 5 cases per spec User Story 5 — list rendering + per-session revoke + current-session refusal per design D7 + bulk revoke-others + propagation ≤ 60s per SC-013.
- [ ] T101 [P] [W17C] [US7] Create `tests/e2e/suites/self_service/test_consent_management.py` (NEW): 4 cases per spec User Story 7 — list + revoke with audit emission + history rendering + policy-version-change re-consent prompt.
- [ ] T102 [P] [W17C] [US6] Create `tests/e2e/suites/self_service/test_self_service_dsr.py` (NEW): 5 cases per spec User Story 6 — submission identical row to admin-DSR per design D8 + audit `source=self_service` + erasure typed-confirmation + active-executions warning + admin-on-behalf-of-user double-audit per Rule 34 + spec correction §10.
- [ ] T103 [P] [W17C] [US-FR657] Create `tests/e2e/suites/self_service/test_audit_trail.py` (NEW): 4 cases per FR-657 — actor_id-only query + subject_id-only query + OR-semantics combined + cursor pagination.

### Journey extensions

- [ ] T104 [W17C] [US1, US2, US7] Modify `tests/e2e/journeys/test_j03_consumer_discovery_execution.py` (verified 31,924 bytes per spec phase research §15): add 4 new `journey_step()` blocks covering notification-center flow per spec correction §15: (a) consumer receives alert → (b) opens bell → (c) reads inbox → (d) updates preferences. Total addition: ~50 lines.
- [ ] T105 [W17C] [US6] Modify `tests/e2e/journeys/test_j10_multi_channel_notifications.py` (verified 7,000 bytes): add 2 new steps cross-linking admin-DSR submission (existing path) with self-service-DSR submission (new path) per plan.md design D8 + spec correction §10. Verify both produce identical `PrivacyDSRRequest` rows AND admin-on-behalf-of-user emits Rule 34 double-audit (one entry as `actor=admin`, one as `subject=user`). Total addition: ~30 lines.

### Matrix-CI integration

- [ ] T106 [W17C] [US1, US2, US3, US4, US5, US6, US7] Modify `.github/workflows/ci.yml` per plan.md Phase 4 day 6: add `tests/e2e/suites/self_service/` to UPD-040's existing matrix-CI job's test path. The suite runs in all 3 modes (`mock`, `kubernetes`, `vault`). Mock mode tests assert that user-self functionality works regardless of the underlying secret backend (these tests don't directly exercise Vault but verify backend behavior is uniform).
- [ ] T107 [W17C] [US1, US6] Verify SC-015: J03 (extended) + J10 (extended) journey tests pass on the matrix CI for all 3 modes. If any mode fails, debug + fix.
- [ ] T108 [W17C] Run `pytest tests/e2e/suites/self_service/ -v` against a kind cluster with the platform running → 8 test files pass.

**Checkpoint (end of Phase 4)**: 8 E2E test files + J03 extension + J10 extension all pass; matrix CI green for all 3 secret modes; Track C is shippable.

---

## Phase 5: Cross-Cutting Verification (Rule 31 + Rule 46 + Audit Emission)

**Story goal**: Verify Rule 31 (no plaintext secrets in logs) + Rule 46 (no `user_id` parameter on `/me/*`) + Rule 9 (every PII operation emits audit chain entry).

- [ ] T109 [W17D] Run the canonical secret-leak regex set against `kubectl logs platform-control-plane-...` for 24 hours of synthetic load (API key creation + MFA enrollment + DSR submission + consent revocation flows) per SC-014; verify zero matches per Rule 31. Document in `specs/092-user-notification-self-service/contracts/secret-leak-verification.md` (NEW file).
- [ ] T110 [W17D] Run `python scripts/check-me-endpoint-scope.py` (T039 deliverable) against the full repo post-Track-A; verify zero violations of Rule 46 (no `/me/*` endpoint accepts a `user_id` parameter).
- [ ] T111 [W17D] Verify all 17 new endpoints emit audit-chain entries per Rule 9: synthetic test hits each state-changing endpoint (create / revoke / update); asserts the `audit_chain_entries` table grows by exactly 1 row per call. Document in `specs/092-user-notification-self-service/contracts/audit-emission-verification.md` (NEW file).
- [ ] T112 [W17D] Run `python scripts/check-secret-access.py` (UPD-040's secret-pattern deny-list) against the Track A code — verify zero direct `os.getenv("*_SECRET")` calls outside the `SecretProvider` implementation files. The Track A bootstrap path uses Pydantic settings + the `MfaEnrollResponse.secret` flow already follows Rule 31 from UPD-014.

---

## Phase 6: SC Verification + Documentation Polish

**Story goal**: All 20 spec SCs pass; UPD-039 docs integration; release notes; final review.

### SC sweep

- [ ] T113 [W17E] Run the full SC verification sweep per plan.md design Phase 6 day 7: SC-001 through SC-020. For each SC, document the actual measurement (e.g., SC-001's "3 seconds bell badge update from login" — measured wall-clock with synthetic 15-alert seed). Capture verification record at `specs/092-user-notification-self-service/contracts/sc-verification.md` (NEW file).

### Operator runbooks (UPD-039 integration)

- [ ] T114 [W17E] [US2] Create `docs/operator-guide/runbooks/notification-preferences-troubleshooting.md` (NEW per plan.md design D14; deliverable here if UPD-039 has landed; otherwise UPD-039 owns and merges later). Sections: Symptom (user not receiving notifications), Diagnosis (check matrix preferences + quiet hours + mandatory event force-on), Remediation, Verification.
- [ ] T115 [P] [W17E] [US4] Create `docs/operator-guide/runbooks/mfa-self-service-issues.md`: lost backup codes recovery flow + admin-policy-enforced MFA disable refusal explanation + admin-assisted MFA reset path (existing UPD-016 / UPD-036).
- [ ] T116 [P] [W17E] [US5] Create `docs/operator-guide/runbooks/session-revocation-incident.md`: incident-response flow when a user reports a stolen session; per-session revoke + bulk revoke-others paths; propagation timing (≤ 60s).
- [ ] T117 [P] [W17E] [US6] Create `docs/operator-guide/runbooks/dsr-self-service-flow.md`: GDPR DSR self-service flow + admin-side review + erasure irreversibility + active-execution warnings.

### Admin guide updates

- [ ] T118 [P] [W17E] [US3, US7] Modify `docs/admin-guide/` (or create if not present): add a "Self-Service Surfaces" section explaining how admin features at UPD-036 admin tab cross-reference user-self equivalents. E.g., admin can override consent on behalf of user (existing path); user has reciprocal self-service path at `/settings/privacy/consent`. Document Rule 34 double-audit for admin-on-behalf-of-user actions.

### Developer guide pages

- [ ] T119 [P] [W17E] Create `docs/developer-guide/me-endpoints.md` (deliverable here if UPD-039 has landed; otherwise lives in `specs/092-user-notification-self-service/contracts/`): the `me/router.py` aggregator pattern, the 17 new endpoints, Rule 46 enforcement, the static-analysis check.
- [ ] T120 [P] [W17E] Create `docs/developer-guide/notification-preferences-internals.md`: the matrix data model, mandatory events, quiet hours timezone handling, digest mode delivery scheduling.

### Auto-doc verification (UPD-039 integration)

- [ ] T121 [W17E] If UPD-039 has landed, run `python scripts/check-doc-references.py` (UPD-039 deliverable) against the FR document — verify FR-649 through FR-657 references in this feature's docs are valid + linked to section 115. CI fails any drift.

### Release notes + final review

- [ ] T122 [W17E] Modify `docs/release-notes/v1.3.0/user-notification-self-service.md` (NEW file or extend the existing v1.3.0 release notes file): document the 9 new pages, 17 new endpoints, the 4 new database columns, the 10 new audit-event types. NO breaking changes (UPD-042 is purely additive).
- [ ] T123 [W17E] Verify all 20 spec SCs pass (re-run T113); verify J03 + J10 + 8 E2E suites + 25 Playwright scenarios all pass on the matrix CI; verify zero secret-leak hits in 24-hour log capture per T109; verify UPD-036's existing test suite passes unchanged (SC-020 — UPD-036 is the admin-equivalent surface).
- [ ] T124 [W17E] Run `pytest apps/control-plane/tests/me/`, `pytest tests/e2e/suites/self_service/`, `pytest tests/e2e/journeys/test_j03_consumer_discovery_execution.py`, `pytest tests/e2e/journeys/test_j10_multi_channel_notifications.py`, `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm test:i18n-parity` one final time → all pass.
- [ ] T125 [W17E] Run `python scripts/check-secret-access.py` (UPD-040), `python scripts/check-me-endpoint-scope.py` (T039), `python scripts/check-admin-role-gates.py` (UPD-040) → all pass with zero violations.
- [ ] T126 [W17E] Address PR review feedback; merge. Verify the `092-user-notification-self-service` branch passes all required CI gates (matrix-CI for 3 secret modes, secret-access check, role-gates check, me-endpoint-scope check, axe-core AA scan, i18n parity); merge to `main`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **W17.0 Setup (T001-T004)**: No blockers; T001 verifies UPD-040 + UPD-041 are on `main` (HARD DEPENDENCY).
- **W17A Track A Backend (T005-T047)**: Depends on W17.0 + UPD-040/41 shipped.
- **W17B Track B UI (T048-T094)**: Depends on Track A T017 (Pydantic schemas) — frontend Zod schemas mirror backend; T048-T058 can begin once schemas land; T059-T094 depend on full Track A endpoints functional.
- **W17C Track C E2E + journeys (T095-T108)**: Depends on Track A (endpoints functional) + Track B (UI for Playwright + journey-step page navigation).
- **W17D Cross-cutting verification (T109-T112)**: Depends on Track A + Track B (full flows must be runnable for log capture + audit emission verification).
- **W17E SC verification + docs (T113-T126)**: Depends on ALL OTHER PHASES — convergent.

### User Story Dependencies

- **US1 (P1 — notification inbox)**: T036 (mark-all-read endpoint) + T048 (bell upgrade) + T059-T062 (inbox page) + T096 (E2E) + T104 (J03 ext).
- **US2 (P1 — preferences matrix)**: T007 (schema extension) + T033-T035 (preferences endpoints) + T063-T067 (matrix UI) + T097 (E2E).
- **US3 (P1 — API keys)**: T008 (created_by_user_id column) + T010 (service-account self-service service methods) + T023-T025 (endpoints) + T068-T071 (UI) + T098 (E2E).
- **US4 (P1 — MFA enrollment)**: T073-T077 (MFA pages) + T099 (E2E). Backend already exists; this is UI-only.
- **US5 (P2 — sessions)**: T009 (list_sessions_by_user method) + T013 (auth_service methods) + T020-T022 (endpoints) + T078-T079 (UI) + T100 (E2E).
- **US6 (P1 — self-service DSR)**: T012 (list_for_subject method) + T029-T031 (endpoints) + T086-T088 (UI) + T102 (E2E) + T105 (J10 ext).
- **US7 (P2 — consent)**: T011 (consent service methods) + T026-T028 (endpoints) + T082-T085 (UI) + T101 (E2E).

### Within Each Track

- Track A: T005-T006 (migration) → T007-T015 (model + service extensions) → T016-T019 (me/ BC scaffolding) → T020-T036 (16 + 1 endpoints, parallel after schemas) → T037-T038 (wire + audit events) → T039-T040 (CI gate) → T041-T047 (integration tests).
- Track B: T048 (bell upgrade) → T050-T058 (API + Zod + hooks) → T059-T088 (9 pages + 30 sub-components, highly parallel by page) → T089-T091 (i18n) → T092-T093 (axe-core + CI gates) → T094 (Playwright).
- Track C: T095 (conftest) → T096-T103 (8 E2E files, parallel) → T104-T105 (journey extensions) → T106-T108 (matrix CI).

### Parallel Opportunities

- **Day 1**: T001-T004 (Setup, all parallel) + T005-T006 (Track A migration) + T048 (Track B bell upgrade — small change).
- **Day 2-3**: Track A T007-T036 sequential within sub-clusters (model → endpoint → service); Track B T050-T058 (hooks) parallel; Track C T095 (conftest setup).
- **Day 4-5**: Track A T037-T047 (wire + tests); Track B T059-T088 (9 pages + 30 sub-components — highly parallel across 2 devs); Track C T096-T103 (8 E2E files — highly parallel).
- **Day 6**: Track B T089-T094 (i18n + axe + Playwright); Track C T104-T108 (journey extensions + matrix CI).
- **Day 7-9**: Phase 5 verification + Phase 6 polish (mostly parallel — runbooks + admin/dev guides parallel).

---

## Implementation Strategy

### MVP First (User Story 1 Only — Notification Inbox)

1. Complete Phase 1 (W17.0) Setup.
2. Complete Phase 2 partial (W17A) Track A — migration + model extensions + `notifications/router.py` mark-all-read endpoint (T005-T007 + T036).
3. Complete Phase 3 partial (W17B) Track B — bell upgrade + `/notifications` page (T048-T062).
4. Run T096 (E2E for US1).
5. **STOP and VALIDATE**: a logged-in user with 15 seeded `UserAlert` rows sees the bell badge update + can navigate to `/notifications` + can mark all read per SC-001 + SC-002 + SC-003.

### Incremental Delivery

1. MVP (US1) → demo notification inbox + bell.
2. + US4 (T073-T077, T099) → demo MFA enrollment page (existing backend).
3. + US3 (T008, T010, T023-T025, T068-T071, T098) → demo self-service API keys.
4. + US2 (T007, T033-T035, T063-T067, T097) → demo preferences matrix.
5. + US6 (T012, T029-T031, T086-T088, T102, T105) → demo self-service DSR.
6. + US5 (T009, T013, T020-T022, T078-T079, T100) → demo session management.
7. + US7 (T011, T026-T028, T082-T085, T101) → demo consent management.
8. + FR-657 (T014-T015, T032, T080-T081, T103) → demo activity audit trail.
9. Full feature complete after Phase 5 + Phase 6 polish.

### Parallel Team Strategy

With 3 devs:

- **Dev A (Track A backend)**: Days 1-3 Track A entire scope (migration + endpoints + service extensions + tests); Days 4-5 Track A polish + cross-cutting verification (Phase 5); Days 6-9 Phase 6 SC verification + runbooks.
- **Dev B (Track B UI — pages 1-5)**: Day 1 Track B bell upgrade + hooks; Days 2-4 inbox + preferences + api-keys + MFA pages (T059-T077); Day 5 i18n + axe-core (T089-T093); Day 6 Playwright (T094).
- **Dev C (Track B UI — pages 6-9 + Track C)**: Days 2-4 sessions + activity + consent + DSR pages (T078-T088); Days 5-6 Track C E2E suite + journey extensions + matrix CI (T095-T108); Days 7-9 Phase 6 admin-guide + dev-guide pages.

Wall-clock: **5-6 days for MVP** (US1 + US4 — both backend-ready); **8-10 days for full feature** with 3 devs in parallel.

---

## Notes

- [P] tasks = different files, no dependencies; safe to parallelize across devs.
- [Story] label maps task to specific user story for traceability (US1-US7 + US-FR657).
- [W17X] label maps task to wave-17 sub-track (W17.0 / W17A-E).
- The plan's effort estimate (10-12 dev-days) supersedes the brownfield's 5-day understatement; tasks below total ~126 entries, consistent with that estimate.
- Track A is the keystone backend; rushing it risks rework in Track B/C. Plan ≥ 3 dev-days.
- Rule 31 (never log secrets) is enforced at THREE layers: T024 (response is one-time per design D10) + T070 (UI clear-on-dismiss) + T112 (CI deny-list extension).
- Rule 46 (no `user_id` parameter on `/me/*`) is enforced by static-analysis CI gate at T039 + T110.
- Rule 9 (PII operations emit audit) is enforced by T038 wiring 10 new event types + T111 verification.
- Rule 45 (every backend capability has UI) is the canonical anchor — verified by mapping each Track A endpoint to a Track B page (the spec's Key Entities section enumerates the mapping).
- The `<NotificationBell>` component is FULLY IMPLEMENTED at 152 lines per research R1 — Track B T048's scope is a SMALL modification (~30 lines net diff).
- The existing `/me/alerts/*` URL convention is preserved (NOT `/me/notifications/*` per spec correction §2). The new aggregator at `/me/router.py` covers 16 OTHER endpoints; the 17th (`POST /me/alerts/mark-all-read`) lives in `notifications/router.py` per BC ownership.
- The existing 6 deliverers (in_app, email, webhook, slack, teams, sms per spec correction §1 — UPD-077 landed) are the channel surface for the FR-651 matrix.
- UPD-040's matrix-CI for 3 secret modes is INHERITED for the new self-service E2E suite; mock mode tests verify uniform behavior regardless of secret backend.
- If UPD-039 has not landed when UPD-042 enters polish phase, runbook + admin-guide + dev-guide pages live in `specs/092-user-notification-self-service/contracts/` and merge into UPD-039 later per plan.md design D14.
