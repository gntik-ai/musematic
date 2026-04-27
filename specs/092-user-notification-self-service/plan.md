# Implementation Plan: UPD-042 — User-Facing Notification Center and Self-Service Security

**Branch**: `092-user-notification-self-service` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-042 is a **UI-heavy gap-fill feature** delivering 9 new Next.js pages + 1 component upgrade on top of existing-but-invisible backend capabilities. It is the v1.3.0 audit-pass cohort's last feature and the canonical Rule 45 ("Every user-facing backend capability has a user-facing UI" — `.specify/memory/constitution.md:258-262` verified per research R14) implementation. Three parallelizable tracks converge for journey-test verification:

- **Track A — Backend `/me/*` endpoints** (~3 dev-days): NEW `apps/control-plane/src/platform/me/router.py` aggregator (per plan.md research R15 — does NOT exist today; the existing `/me/alerts/*` lives distributed in `notifications/router.py:20`, MFA endpoints live at `/api/v1/auth/mfa/*`, and there is NO centralized `/me/*` aggregator). The new router consolidates: 17 NEW endpoints (sessions, service-accounts, consent, DSR, activity, notification-preferences-extended, notifications-mark-all-read, notification-test). One Alembic migration `070_user_self_service_extensions.py` (next slot per research R10 — UPD-040/041 own 069). Schema additions per spec correction §7 (`UserAlertSettings` extension OR new `user_notification_preferences` sibling table) + spec correction §3 (`created_by_user_id` column on `service_account_credentials`). NEW `list_sessions_by_user(user_id) -> list[SessionDetail]` method on `RedisSessionStore` (research R6 — does NOT exist today). NEW `list_entries_by_actor_or_subject(actor_id, subject_id, ...)` method on `AuditChainService` per FR-657. 10 new audit-event types following existing conventions per spec correction §10.

- **Track B — Frontend pages + `<NotificationBell>` upgrade** (~6 dev-days): EXTENDS the **already-fully-implemented** 152-line `NotificationBell` at `apps/web/components/features/alerts/notification-bell.tsx` (CRITICAL FINDING per spec correction §6 + research R1: the brownfield's claim that the bell is a placeholder is INCORRECT — it is fully wired with `useAlertFeed()` WebSocket hook + `/me/alerts` queries + dropdown rendering 20 most recent per research R1). UPD-042's bell scope REDUCES to: (a) increase the limit-20 → limit-5 in the dropdown per FR-650; (b) add "See all" link to `/notifications`; (c) verify cross-tab unread-count sync via the existing `useAlertFeed` WebSocket connection. 9 NEW pages: `/notifications` inbox, `/settings/notifications` matrix, `/settings/api-keys`, `/settings/security` overview, `/settings/security/mfa`, `/settings/security/sessions`, `/settings/security/activity`, `/settings/privacy/consent`, `/settings/privacy/dsr`. All pages use the existing `useAuthStore` Zustand pattern verified at `apps/web/store/auth-store.ts:40+` per research R12. i18n catalogs for 6 locales (en, es, de, fr, it, zh-CN per FR-620) with hierarchical key namespace (`notifications.*`, `apiKeys.*`, `security.mfa.*`, `security.sessions.*`, `privacy.consent.*`, `privacy.dsr.*`) per research R11. axe-core AA scan per Rule 41 inheritance.

- **Track C — E2E + journey extensions** (~2 dev-days): NEW `tests/e2e/suites/self_service/` directory with 8 test files (one per spec User Story 1-7 + audit-trail). EXTENDS J03 (Consumer journey — verified per research §15 of spec phase: `test_j03_consumer_discovery_execution.py` exists at 31,924 bytes) with notification-center steps. EXTENDS J10 (Multi-channel notifications — verified at 7,000 bytes) to cross-link admin-DSR with self-service-DSR per spec correction §10 + Rule 34 double-audit verification. Inherits UPD-040's matrix-CI for 3 secret modes (mock / kubernetes / vault).

The three tracks converge at Phase 7 for SC verification + auto-doc verification. **Effort estimate: 10-12 dev-days** (the brownfield's "5 days (5 points)" understates — the 9 new pages with shadcn primitives + i18n × 6 locales + Playwright × 18+ scenarios + axe-core AA scan + the new `me/router.py` aggregator + the 10 audit-event types + the `RedisSessionStore.list_sessions_by_user` extension + the `AuditChainService.list_entries_by_actor_or_subject` extension + the schema migration with backward-compat alias add ~5-7 days the brownfield doesn't account for; corrected per the v1.3.0 cohort pattern). Wall-clock with 3 devs in parallel: **~5-6 days**.

## Constitutional Anchors

This plan is bounded by the following Constitution articles + FRs. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-042 declared** | Constitution audit-pass roster (Wave 17) | The whole feature |
| **Rule 9 — Every PII operation emits an audit chain entry** | `.specify/memory/constitution.md` (verified existing) | Track A's 10 new audit-event types per spec correction §8 (e.g., `auth.session.revoked`, `auth.api_key.created`, `privacy.consent.revoked`, `privacy.dsr.submitted` with `source=self_service`) |
| **Rule 30 — Every admin endpoint declares a role gate** | `.specify/memory/constitution.md:198-202` | Does NOT apply to `/me/*` per spec correction — these are user-self endpoints; the plan's gate is `Depends(get_current_user)` only |
| **Rule 31 — Super-admin bootstrap never logs secrets** | `.specify/memory/constitution.md:203-207` | API-key one-time display per FR-652; MFA TOTP secret via `MfaEnrollResponse.secret` per research R2 of spec phase; backup codes one-time display |
| **Rule 34 — Impersonation double-audits** | `.specify/memory/constitution.md` (verified existing) | Track A's audit-event source classification per spec correction §10 — admin-on-behalf-of-user DSR emits actor=admin + subject=user double-entry |
| **Rule 41 — Accessibility AA** | `.specify/memory/constitution.md` | Track B's axe-core CI gate inherits UPD-083; all 9 pages MUST pass AA |
| **Rule 45 — Every user-facing backend capability has UI** | `.specify/memory/constitution.md:258-262` (verified per research R14) | THE canonical anchor — the entire feature is the Rule 45 gap-fill |
| **Rule 46 — Self-service endpoints scoped to `current_user`** | `.specify/memory/constitution.md:263-267` (verified per research R14) | Track A's 17 new `/me/*` endpoints accept NO `user_id` parameter; resolve scope from session principal via existing `get_current_user` dependency |
| **FR-649 — Notification Center Inbox** | FR doc lines 3512-3513 (verified per spec phase research §13) | Track B's `/notifications` page |
| **FR-650 — Global Notification Bell** | FR doc lines 3515-3516 | Track B's bell upgrade (NOT new component per research R1) |
| **FR-651 — Notification Preferences per User** | FR doc lines 3518-3519 | Track A schema extension + Track B's matrix UI |
| **FR-652 — Self-Service API Keys** | FR doc lines 3521-3522 | Track A's `/me/service-accounts` + Track B's `/settings/api-keys` |
| **FR-653 — MFA Self-Service Enrollment** | FR doc lines 3524-3525 | Track B's `/settings/security/mfa` (backend exists per spec phase research §2) |
| **FR-654 — User Session Management** | FR doc lines 3527-3528 | Track A's `/me/sessions` + Track B's `/settings/security/sessions` |
| **FR-655 — Consent Management Self-Service** | FR doc lines 3530-3531 | Track A's `/me/consent` + Track B's `/settings/privacy/consent` |
| **FR-656 — Self-Service DSR** | FR doc lines 3533-3534 | Track A's `/me/dsr` + Track B's `/settings/privacy/dsr` |
| **FR-657 — Self-Service Audit Chain Integration** | FR doc lines 3536-3537 | Track A's `/me/activity` + Track B's `/settings/security/activity` |

**Verdict: gate passes. No declared variances.** UPD-042 satisfies Rule 45 + Rule 46 + Rule 9 + Rule 34 + Rule 41 governing user-self surfaces.

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Python 3.12 (control plane — new `me/router.py` aggregator + Alembic migration + audit-service + session-store extensions); TypeScript 5.x (Next.js 14 — 9 new pages + `NotificationBell` upgrade + Zod schemas + i18n catalogs); YAML (no Helm changes — backend reuses existing infrastructure). NO Go changes. |
| **Primary Dependencies (existing — reused)** | `FastAPI 0.115+` (router), `pydantic-settings 2.x`, `SQLAlchemy 2.x async` (`UserAlertSettings` at `notifications/models.py:51-79` extension; `service_account_credentials` at `auth/models.py:111-129`); `redis-py 5.x async` (existing session store at `auth/session.py` per research R6); `aiokafka 0.11+` (audit-event emission via existing `publish_auth_event`); `react 18+`, `next 14`, `shadcn/ui` (existing primitives — `Tabs`, `Dialog`, `Table`, `Badge`, `Card`, `Form`, `DropdownMenu`); `Zustand 5.x` (existing `useAuthStore` per research R12); `TanStack Query v5` (existing `useAppQuery` pattern verified at `notification-bell.tsx`); `next-intl` (i18n per research R11). |
| **Primary Dependencies (NEW in 092)** | `qrcode.react` for MFA QR code rendering (verify if already in `package.json` during T020; UPD-017 may have introduced it for the MFA challenge form). NO new backend deps. |
| **Storage** | PostgreSQL — Alembic migration `070_user_self_service_extensions.py` (next slot per research R10 — UPD-040/041 own 069): (a) extends `UserAlertSettings` (per spec correction §7) with 3 NEW JSONB columns — `per_channel_preferences`, `digest_mode`, `quiet_hours` — preserving the existing 3 columns (`state_transitions`, `delivery_method`, `webhook_url`) for backward compatibility; (b) adds `created_by_user_id: UUID FK to users.id NULLABLE` on `service_account_credentials` per spec correction §3; (c) NO new tables (the matrix is column-extension per design D2 below). Redis — reuses the existing session store (`session:{user_id}:{session_id}` hash + `user_sessions:{user_id}` set per research R6) — no new keys; the new `list_sessions_by_user()` method queries the existing set. NO Vault paths owned by this feature. |
| **Testing** | `pytest 8.x` + `pytest-asyncio` (control plane unit tests for the 17 new `/me/*` endpoints — ~50+ test cases); Playwright (Next.js page E2E for 9 pages — ~25+ scenarios); axe-core CI gate per Rule 41; pytest E2E suite at `tests/e2e/suites/self_service/` — 8 test files. J03 extension (~50 lines added to existing 31,924-byte file). J10 extension (~30 lines added to existing 7,000-byte file). Matrix-CI inheritance from UPD-040: `secret_mode: [mock, kubernetes, vault]` × `self_service` suite. |
| **Target Platform** | Linux x86_64 Kubernetes 1.28+ (control plane); Next.js 14 server + browser (web app). |
| **Project Type** | Cross-stack feature: (a) Python control plane (`apps/control-plane/` — new `me/router.py` + extensions to `notifications/router.py`, `auth/session.py`, `audit/service.py`, `audit/repository.py`); (b) Next.js frontend (`apps/web/` — 9 new pages + `<NotificationBell>` upgrade + Zod schemas + i18n catalogs); (c) E2E test scaffolding (`tests/e2e/suites/self_service/`); (d) journey test extensions. NO Helm/Go changes. |
| **Performance Goals** | Notification bell badge update ≤ 3 seconds from login per SC-001; inbox first-paint ≤ 800ms p95 per SC-002; mark-all-read bulk action ≤ 2 seconds per SC-003; preferences save ≤ 500ms per SC-004; API key revocation propagation ≤ 5 seconds per SC-009; per-session revocation ≤ 60 seconds across pods per SC-013; consent revocation cache TTL ≤ 30 seconds per SC-015. |
| **Constraints** | Rule 31 — no plaintext API key value in any log; Rule 45 — every backend `/me/*` endpoint MUST have a UI page; Rule 46 — `/me/*` endpoints REJECT any `user_id` parameter (CI-enforced via static-analysis check at T032); FR-657 — audit query MUST scope by `actor_id=current_user.id OR subject_id=current_user.id`; FR-651 — mandatory events (security.*, incidents.*) cannot be disabled (UI-locked + backend validator). |
| **Scale / Scope** | Track A: 1 NEW Python module (`me/router.py`, ~600 lines including 17 endpoints) + 1 Alembic migration (~80 lines including downgrade) + ~150 lines of Pydantic schemas + 2 service-method extensions (`list_sessions_by_user`, `list_entries_by_actor_or_subject` — ~80 lines each) + 10 NEW audit-event payload classes + ~50 unit tests. Track B: 9 NEW pages (~250 lines × 9 = ~2250 lines) + ~30 NEW shared components (~80 lines × 30 = ~2400 lines) + 1 component upgrade (`NotificationBell` ~30 lines net diff) + 6 i18n catalogs × ~80 strings each = ~480 i18n entries + ~25 Playwright scenarios. Track C: 8 NEW E2E test files (~80 lines each = ~640 lines) + J03 extension (~50 lines) + J10 extension (~30 lines). **Total: ~6500 lines of new Python + TypeScript + ~480 i18n entries; ~50 NEW files + ~10 MODIFIED files.** |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing repo discipline | ✅ Pass | UPD-042 (a) EXTENDS the existing 6-endpoint `/me/alerts*` router at `notifications/router.py:20-84` with 1 new endpoint (`POST /me/alerts/mark-all-read`) — the existing 6 are preserved; (b) UPGRADES the existing 152-line `NotificationBell` (NOT introduces) per research R1; (c) REUSES the existing `MfaEnrollResponse` + `MfaConfirmResponse` from `auth/router.py:112-137` unchanged; (d) ADDS the new `me/router.py` aggregator distinct from existing distributed `/me/*` registrations; (e) PRESERVES the existing platform-admin `POST /api/v1/auth/service-accounts` per spec correction §3. |
| Rule 9 — every PII operation emits an audit chain entry | ✅ Pass | All 17 new `/me/*` endpoints that modify state emit audit entries via the existing dual-emission pattern (`repository.create_audit_entry` + `publish_auth_event` per research R6 of spec phase); 10 new event types follow `auth.*` / `privacy.*` / `notifications.*` conventions per spec correction §8. |
| Rule 30 — every admin endpoint role-gated | ✅ Pass (N/A) | UPD-042 adds NO admin endpoints; all 17 new endpoints are user-self under `/me/*` and gated by `Depends(get_current_user)` only. |
| Rule 31 — super-admin bootstrap never logs secrets | ✅ Pass | API-key one-time display via the existing UPD-014 service-account-credential creation flow (returns hash; raw key value displayed once); MFA TOTP secret via `MfaEnrollResponse.secret` (existing — already follows Rule 31 from UPD-014); backup codes via `MfaConfirmResponse.recovery_codes` (existing). UPD-040's secret-leak CI gate at `scripts/check-secret-access.py` covers any new code paths. |
| Rule 34 — impersonation double-audits | ✅ Pass | Track A's DSR submission emits with `source=self_service` for user-initiated; the existing admin-DSR path at `privacy_compliance/router.py:44-55` emits with `source=admin` + Rule 34 double-audit when actor != subject; both paths produce identical `PrivacyDSRRequest` rows per spec correction §10. |
| Rule 41 — Accessibility AA | ✅ Pass | Track B's 9 new pages pass axe-core AA scan (CI gate inherited from UPD-083); verified by SC-019. |
| Rule 45 — every user-facing backend capability has UI | ✅ Pass | THE canonical anchor — UPD-042 IS the Rule 45 gap-fill. Every backend capability listed in spec.md "Key Entities" gets a corresponding UI page. |
| Rule 46 — self-service endpoints scoped to `current_user` | ✅ Pass | All 17 new `/me/*` endpoints accept NO `user_id` parameter; static-analysis CI check (added in T032) verifies at PR time. The existing `/me/alerts/*` endpoints at `notifications/router.py:20-84` already follow this pattern (research R2 — they use `_user_id(current_user)` helper to extract from JWT claims). |

**Verdict: gate passes. No declared variances.** UPD-042 satisfies all eight constitutional rules governing user-self surfaces.

## Project Structure

### Documentation (this feature)

```text
specs/092-user-notification-self-service/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
# === Track A — Backend `/me/*` aggregator + extensions ===
apps/control-plane/src/platform/me/__init__.py                       # NEW
apps/control-plane/src/platform/me/router.py                          # NEW — aggregator with 17 new endpoints (sessions, service-accounts, consent, DSR, activity, notification-preferences-extended, mark-all-read, test-notification)
apps/control-plane/src/platform/me/schemas.py                         # NEW — Pydantic schemas for all 17 endpoints (request + response models)
apps/control-plane/src/platform/me/service.py                         # NEW — orchestrator service that delegates to existing services (DSRService, ConsentService, AuthService, NotificationsService, AuditChainService) per spec scope discipline
apps/control-plane/src/platform/main.py                               # MODIFY — register `me_router` via `app.include_router(me_router, prefix="/api/v1")` AFTER the existing notifications router registration at line 1622
apps/control-plane/src/platform/notifications/router.py               # MODIFY — adds 1 NEW endpoint `POST /me/alerts/mark-all-read` per FR-649; the existing 6 endpoints at lines 28-84 are preserved unchanged
apps/control-plane/src/platform/notifications/service.py              # MODIFY — adds `mark_all_read(user_id) -> int` method; adds `test_notification(user_id, event_type) -> None` method per FR-651 + User Story 2 acceptance scenario 4
apps/control-plane/src/platform/notifications/models.py               # MODIFY — extends `UserAlertSettings` (lines 51-79) with 3 NEW JSONB columns per spec correction §7 + design D2: `per_channel_preferences`, `digest_mode`, `quiet_hours`
apps/control-plane/src/platform/auth/models.py                        # MODIFY — adds `created_by_user_id: Mapped[UUID | None]` column to `ServiceAccountCredential` (lines 111-129) per spec correction §3
apps/control-plane/src/platform/auth/session.py                       # MODIFY — adds `list_sessions_by_user(user_id) -> list[SessionDetail]` method to `RedisSessionStore` per research R6 (does NOT exist today; queries the existing `user_sessions:{user_id}` set + fetches each session detail)
apps/control-plane/src/platform/auth/services/auth_service.py         # MODIFY — adds `list_user_sessions(user_id) -> list[SessionDetail]`, `revoke_session_by_id(user_id, session_id, current_session_id) -> None` (refuses if attempt to revoke current session per spec edge case), `revoke_other_sessions(user_id, current_session_id) -> int` methods
apps/control-plane/src/platform/auth/services/service_account_service.py  # NEW (verify existing; if exists, EXTEND) — adds user-self methods `create_for_current_user(user_id, name, scopes, expiry, mfa_token) -> ServiceAccountCredential` (with MFA step-up + max-10-per-user limit + scope-subset enforcement per spec correction §3), `list_for_current_user(user_id) -> list`, `revoke_for_current_user(user_id, sa_id) -> None`
apps/control-plane/src/platform/audit/service.py                      # MODIFY — adds `list_entries_by_actor_or_subject(actor_id, subject_id, start_ts, end_ts, limit, cursor) -> list[AuditChainEntry]` per FR-657 + research R9 (extends existing `list_audit_sources_in_window`)
apps/control-plane/src/platform/audit/repository.py                   # MODIFY — adds the underlying SQL query for the above
apps/control-plane/src/platform/privacy_compliance/services/dsr_service.py  # MODIFY (existing per research R8) — adds public method `list_for_subject(subject_user_id, limit, cursor) -> list[DSRResponse]`; the existing `create_request(payload, requested_by)` is reused unchanged for self-service
apps/control-plane/src/platform/privacy_compliance/services/consent_service.py  # MODIFY (existing per research R7) — adds public method `list_for_user(user_id) -> list[PrivacyConsentRecord]`, `list_history_for_user(user_id) -> list[ConsentHistoryEntry]`; the existing `revoke(user_id, consent_type)` is reused unchanged
apps/control-plane/migrations/versions/070_user_self_service_extensions.py  # NEW — Alembic migration adding 3 columns to `user_alert_settings` + 1 column to `service_account_credentials` per spec correction §3 + §7
apps/control-plane/tests/me/__init__.py                               # NEW
apps/control-plane/tests/me/test_router.py                            # NEW — pytest tests for 17 new endpoints (~30 cases)
apps/control-plane/tests/me/test_session_revocation.py                # NEW — race-safe revocation + current-session-refusal (~10 cases)
apps/control-plane/tests/me/test_service_account_self_service.py      # NEW — MFA step-up + max-10 + scope-subset (~10 cases)
apps/control-plane/tests/me/test_consent_self_service.py              # NEW — revoke + history (~6 cases)
apps/control-plane/tests/me/test_dsr_self_service.py                  # NEW — submission with source=self_service (~6 cases)
apps/control-plane/tests/me/test_activity_query.py                    # NEW — actor_id OR subject_id pagination (~6 cases)

# === Track B — Frontend pages + `<NotificationBell>` upgrade ===
apps/web/components/features/alerts/notification-bell.tsx             # MODIFY — change `limit=20` to `limit=5` for the dropdown per FR-650; add "See all" link to `/notifications`; verify cross-tab sync via existing `useAlertFeed` hook (research R1 — bell is fully-implemented; this is a SMALL modification)
apps/web/app/(main)/notifications/page.tsx                            # NEW — full inbox (~250 lines): paginated list + filter sidebar + bulk actions
apps/web/app/(main)/notifications/_components/NotificationFilters.tsx  # NEW (~150 lines)
apps/web/app/(main)/notifications/_components/NotificationListItem.tsx  # NEW (~80 lines) — reusable row for inbox + dropdown
apps/web/app/(main)/notifications/_components/NotificationBulkActions.tsx  # NEW (~100 lines)
apps/web/app/(main)/settings/notifications/page.tsx                   # NEW — preferences matrix (~250 lines)
apps/web/app/(main)/settings/notifications/_components/EventChannelMatrix.tsx  # NEW (~300 lines) — 6-channel × N-event matrix UI
apps/web/app/(main)/settings/notifications/_components/QuietHoursForm.tsx  # NEW (~120 lines) — timezone-aware time-range picker
apps/web/app/(main)/settings/notifications/_components/DigestModeSelect.tsx  # NEW (~80 lines) — per-channel select (immediate / hourly / daily)
apps/web/app/(main)/settings/notifications/_components/TestNotificationButton.tsx  # NEW (~80 lines) — per-event-type test action
apps/web/app/(main)/settings/api-keys/page.tsx                        # NEW — list + create modal + revoke (~250 lines)
apps/web/app/(main)/settings/api-keys/_components/ApiKeyCreateDialog.tsx  # NEW (~200 lines) — MFA step-up + scope picker + one-time display
apps/web/app/(main)/settings/api-keys/_components/ApiKeyOneTimeDisplay.tsx  # NEW (~120 lines) — token value with copy + warning per Rule 31
apps/web/app/(main)/settings/api-keys/_components/ApiKeyTable.tsx     # NEW (~150 lines) — list with name, scope, last-used, expires-at, revoke
apps/web/app/(main)/settings/security/page.tsx                        # NEW — security overview with links to MFA / sessions / activity (~150 lines)
apps/web/app/(main)/settings/security/mfa/page.tsx                    # NEW — enrollment flow (~250 lines)
apps/web/app/(main)/settings/security/mfa/_components/MfaEnrollFlow.tsx  # NEW (~250 lines) — stepper: enable → QR → confirm → backup codes
apps/web/app/(main)/settings/security/mfa/_components/QRCodeDisplay.tsx  # NEW (~80 lines) — QR + text secret + manual-entry fallback
apps/web/app/(main)/settings/security/mfa/_components/BackupCodesDisplay.tsx  # NEW (~120 lines) — one-time render with copy / download per Rule 31
apps/web/app/(main)/settings/security/mfa/_components/DisableMfaDialog.tsx  # NEW (~150 lines) — password + TOTP step-up
apps/web/app/(main)/settings/security/sessions/page.tsx               # NEW — session list + revoke (~200 lines)
apps/web/app/(main)/settings/security/sessions/_components/SessionList.tsx  # NEW (~180 lines)
apps/web/app/(main)/settings/security/activity/page.tsx               # NEW — user audit trail (~200 lines)
apps/web/app/(main)/settings/security/activity/_components/ActivityFilters.tsx  # NEW (~120 lines)
apps/web/app/(main)/settings/privacy/consent/page.tsx                 # NEW — consent list + revoke + history (~200 lines)
apps/web/app/(main)/settings/privacy/consent/_components/ConsentCard.tsx  # NEW (~120 lines)
apps/web/app/(main)/settings/privacy/consent/_components/RevokeConsentDialog.tsx  # NEW (~150 lines) — consequences dialog per consent type
apps/web/app/(main)/settings/privacy/consent/_components/ConsentHistoryTab.tsx  # NEW (~150 lines)
apps/web/app/(main)/settings/privacy/dsr/page.tsx                     # NEW — DSR list + submission (~200 lines)
apps/web/app/(main)/settings/privacy/dsr/_components/DsrSubmissionForm.tsx  # NEW (~250 lines) — multi-step with irreversibility warning for erasure
apps/web/app/(main)/settings/privacy/dsr/_components/DsrStatusList.tsx  # NEW (~150 lines)
apps/web/lib/api/me.ts                                                 # NEW — fetch wrappers for all 17 new `/me/*` endpoints
apps/web/lib/schemas/me.ts                                             # NEW — Zod schemas mirroring backend Pydantic schemas
apps/web/lib/hooks/use-me-sessions.ts                                  # NEW — TanStack Query hook
apps/web/lib/hooks/use-me-api-keys.ts                                  # NEW
apps/web/lib/hooks/use-me-consent.ts                                   # NEW
apps/web/lib/hooks/use-me-dsr.ts                                       # NEW
apps/web/lib/hooks/use-me-activity.ts                                  # NEW
apps/web/lib/hooks/use-me-notification-preferences.ts                  # NEW
apps/web/messages/en.json                                              # MODIFY — adds ~80 new i18n keys under `notifications.*`, `apiKeys.*`, `security.*`, `privacy.*` namespaces per research R11 convention
apps/web/messages/{de,es,fr,it,zh-CN,ja}.json                          # MODIFY — translated catalogs per UPD-038's parity check (vendor-handled)
apps/web/tests/e2e/self-service-pages.spec.ts                          # NEW — Playwright tests for 9 new pages (~25 scenarios)

# === Track C — E2E + journey extensions ===
tests/e2e/suites/self_service/__init__.py                              # NEW
tests/e2e/suites/self_service/conftest.py                              # NEW — shared fixtures (logged-in user with seeded UserAlerts, MFA-enabled user, multi-session user)
tests/e2e/suites/self_service/test_notification_inbox.py               # NEW — User Story 1 (~5 cases)
tests/e2e/suites/self_service/test_notification_preferences.py         # NEW — User Story 2 (~6 cases)
tests/e2e/suites/self_service/test_api_keys.py                         # NEW — User Story 3 (~5 cases)
tests/e2e/suites/self_service/test_mfa_enrollment.py                   # NEW — User Story 4 (~5 cases)
tests/e2e/suites/self_service/test_session_revocation.py               # NEW — User Story 5 (~5 cases)
tests/e2e/suites/self_service/test_consent_management.py               # NEW — User Story 7 (~4 cases)
tests/e2e/suites/self_service/test_self_service_dsr.py                 # NEW — User Story 6 (~5 cases)
tests/e2e/suites/self_service/test_audit_trail.py                      # NEW — FR-657 (~4 cases)
tests/e2e/journeys/test_j03_consumer_discovery_execution.py            # MODIFY — adds notification-center steps (~50 lines)
tests/e2e/journeys/test_j10_multi_channel_notifications.py             # MODIFY — adds self-service-DSR cross-link with admin-DSR path per spec correction §10 (~30 lines)
.github/workflows/ci.yml                                               # MODIFY — adds `tests/e2e/suites/self_service/` to UPD-040's matrix-CI test path
```

**Structure decision**: UPD-042 follows the brownfield repo discipline established by UPD-036 + UPD-037 (admin workbench + signup) + UPD-040 (Vault). The new `me/` BC at `apps/control-plane/src/platform/me/` aggregates user-self endpoints distributed today across multiple BCs (notifications, auth, privacy_compliance, audit). The 9 new pages follow the existing route-group convention `app/(main)/...`. The component co-location pattern (`_components/` subdirectory per page) keeps page-scoped components close to their consumer. NO new BCs are introduced beyond the `me/` aggregator; existing BCs are extended.

## Phase 0 — Research

> Research notes captured during plan authoring. Each item resolves a specific design question.

- **R1 — `<NotificationBell>` is FULLY IMPLEMENTED, not a placeholder [RESEARCH-COMPLETE]**: Verified at `apps/web/components/features/alerts/notification-bell.tsx` (152 LOC). The component uses `useAlertFeed()` for WebSocket connection + `/me/alerts?limit=20` query + `/me/alerts/unread-count` query + dropdown rendering 20 most recent + bell icon with unread badge. The brownfield's "[NEW]" claim per planning-input is INCORRECT. **Resolution**: UPD-042's bell scope SHRINKS to: (a) `limit=20` → `limit=5` for the dropdown per FR-650; (b) ADD "See all" link to `/notifications` (the link does not exist today); (c) verify cross-tab sync. The existing `useAlertFeed` WebSocket hook + `useAuthStore.user.id` lookup at line 59 are reused unchanged. SIGNIFICANTLY REDUCES Track B effort vs the brownfield's 0.5-day estimate.

- **R2 — Existing `/me/alerts*` endpoints already cover FR-649's read-side [RESEARCH-COMPLETE]**: Verified at `notifications/router.py:20-84` per research R2. 6 existing endpoints: `GET/PUT /me/alert-settings`, `GET /me/alerts`, `GET /me/alerts/unread-count`, `PATCH /me/alerts/{id}/read`, `GET /me/alerts/{id}`. **Resolution**: UPD-042 ADDS only 1 new endpoint to this router (`POST /me/alerts/mark-all-read` for the bulk action per FR-649); the inbox page consumes the existing endpoints. The 16 OTHER new `/me/*` endpoints (sessions, service-accounts, consent, DSR, activity, etc.) live in the NEW `me/router.py` aggregator per research R5.

- **R3 — Header.tsx already imports `<NotificationBell/>` [RESEARCH-COMPLETE]**: Verified at line 8 import + line 57 render per research R3. **Resolution**: NO changes to `Header.tsx` required by UPD-042. The bell upgrade per R1 is a self-contained component-internal change.

- **R4 — Session-store extension required [RESEARCH-COMPLETE]**: Verified at `auth/session.py` per research R4 + R6. Existing methods: `create_session`, `get_session`, `delete_session`, `delete_all_sessions`. MISSING: list-by-user. **Resolution**: Add `list_sessions_by_user(user_id) -> list[SessionDetail]` method per design D6 below. The new method queries the existing `user_sessions:{user_id}` Redis set + fetches each session's detail.

- **R5 — Centralized `me/router.py` aggregator vs distributed [RESEARCH-COMPLETE]**: Verified per research R5 + R15 — no `/api/v1/me` aggregator exists today. Distribution is: `/me/alerts*` lives in notifications BC; MFA + service-accounts live in auth BC at `/api/v1/auth/*` (NOT `/me/*`). **Resolution**: NEW `apps/control-plane/src/platform/me/` BC with router that aggregates 16 of the 17 new endpoints. The 17th (`POST /me/alerts/mark-all-read`) lives in `notifications/router.py` per BC ownership of `/me/alerts*`. This is consistent with the existing pattern AND avoids cross-BC coupling.

- **R6 — Audit chain query extension [RESEARCH-COMPLETE]**: Verified at `audit/service.py:38-94` (existing `list_audit_sources_in_window(start_ts, end_ts, sources)`) + `audit/repository.py:77+` per research R9. **Resolution**: Add `list_entries_by_actor_or_subject(actor_id, subject_id, start_ts, end_ts, limit, cursor) -> list[AuditChainEntry]` method per design D9 below. Implementation: SQL `WHERE actor_id = :actor_id OR subject_id = :subject_id` with cursor-based pagination using `(timestamp, id)` composite cursor.

- **R7 — Schema-extension choice for `UserAlertSettings` [RESEARCH-COMPLETE — column-extension chosen]**: Per spec correction §7 the choice was deferred to plan phase. **Resolution (design D2)**: ADD 3 NEW JSONB columns to `UserAlertSettings`: `per_channel_preferences: dict[str, list[str]]` (event_type → list of enabled channels), `digest_mode: dict[str, str]` (channel → "immediate" / "hourly" / "daily"), `quiet_hours: dict | None` (`{start_time: "22:00", end_time: "07:00", timezone: "Europe/Rome"}`). Reasoning: column-extension is simpler to migrate (one ALTER TABLE) + sufficient for the use case (single user × N events × 6 channels) + keeps the existing 3 columns for backward compatibility. A separate `user_notification_preferences` table is rejected because (a) the row count is bounded (~6 channels × N events per user) and fits a single row's JSONB; (b) the SQL queries would be more complex.

- **R8 — `created_by_user_id` column on service_account_credentials [RESEARCH-COMPLETE]**: Verified at `auth/models.py:111-129` per research §8 of spec phase. Existing columns include `service_account_id`, `name`, `api_key_hash`, `role`, `status`, `last_used_at`, `workspace_id` (nullable). **Resolution**: Add `created_by_user_id: Mapped[UUID | None]` column. NULL for admin-created (system-level); populated for self-service-created. The existing `POST /api/v1/auth/service-accounts` (admin-only, sets to NULL) is preserved per spec correction §3; the new `POST /me/service-accounts` sets to `current_user.id`. The user-self enumeration (`GET /me/service-accounts`) filters `WHERE created_by_user_id = :user_id`.

- **R9 — Alembic sequence [RESEARCH-COMPLETE]**: Per research R10 — UPD-040 owns 069 (oauth-bootstrap-related); UPD-041 follows but exact slot depends on UPD-040's migration count. **Resolution**: UPD-042's migration is `070_user_self_service_extensions.py`. If UPD-040 owns multiple migrations (e.g., 069-071), UPD-042 shifts to the actual next slot. T010 of tasks confirms the live sequence at the time of authoring.

- **R10 — i18n catalog convention [RESEARCH-COMPLETE]**: Per research R11 — hierarchical JSON with camelCase keys, top-level domain (e.g., `auth`, `notifications`), nested sub-context (e.g., `signup`, `verify`). **Resolution**: UPD-042's keys live under `notifications.{inbox,preferences}`, `apiKeys.*`, `security.{mfa,sessions,activity}`, `privacy.{consent,dsr}`. Estimated ~80 new keys. Vendor translation per UPD-039 / FR-620 (6 locales — en, es, de, fr, it, zh-CN); the existing UPD-088 parity check at `scripts/check-readme-parity.py` extension catches drift.

- **R11 — `useAuthStore` Zustand pattern [RESEARCH-COMPLETE]**: Verified at `apps/web/store/auth-store.ts` per research R12. **Resolution**: All 9 new pages use `const userId = useAuthStore((state) => state.user?.id ?? null)` for authorization scope. The store's `isAuthenticated` flag gates the pages from rendering for logged-out users (the existing `(main)` route-group middleware already enforces this).

- **R12 — Cross-tab `mark-as-read` sync [RESEARCH-COMPLETE — DEFERRED TO POLISH]**: Per spec SC-003 the bell badge must propagate to other tabs within 5 seconds. The existing `useAlertFeed` WebSocket connection per pod broadcasts events to all tabs of the same user via the existing `ALERTS` channel; the bell badge update is automatic. **Resolution**: NO new code; verify in T087 (Playwright cross-tab scenario).

- **R13 — Constitution Rule 45 + 46 verbatim [RESEARCH-COMPLETE]**: Verified at `.specify/memory/constitution.md:258-267` per research R14. Rule 45: "Every user-facing backend capability has a user-facing UI." Rule 46: "Self-service endpoints are scoped to `current_user`. Endpoints under `/api/v1/me/*` accept no `user_id` parameter and always operate on the authenticated principal's own data." **Resolution**: Pinned for the Constitutional Anchors table; T032 adds a CI static-analysis check verifying no `/me/*` endpoint accepts a `user_id` parameter.

- **R14 — `ALERTS` WebSocket channel auto-subscription [RESEARCH-COMPLETE]**: Per spec correction §5 — the existing `ALERTS` channel (Kafka topics `monitor.alerts` + `notifications.alerts`) is auto-subscribed by `_auto_subscribe_alerts()` at `ws_hub/router.py:407-462`. **Resolution**: The `<NotificationBell>` upgrade per R1 reuses the existing `useAlertFeed` hook which connects via the WS hub on login; no new channel registration required.

## Phase 1 — Design Decisions

> Implementation tasks (in tasks.md) MUST honour these decisions or escalate via spec amendment.

### D1 — `me/router.py` is the canonical `/me/*` aggregator (16 endpoints)

The existing `/me/alerts*` endpoints (6 total) STAY in `notifications/router.py` per BC ownership. The 16 OTHER `/me/*` endpoints (sessions, service-accounts, consent, DSR, activity, notification-preferences-extended, mark-all-read) live in the NEW `me/router.py`. The 17th endpoint (`POST /me/alerts/mark-all-read`) is added to the existing `notifications/router.py` per BC ownership.

### D2 — `UserAlertSettings` column-extension over sibling table

3 new JSONB columns on `UserAlertSettings`: `per_channel_preferences`, `digest_mode`, `quiet_hours`. Reason: simpler migration + single-row-per-user fits JSONB + backward compatibility with existing 3 columns. Sibling-table approach is rejected per research R7.

### D3 — `created_by_user_id` distinguishes self-service vs admin-created service accounts

NULL = admin-created (system-level); populated = self-service. The existing platform-admin endpoint stays; the new user-self endpoint adds the value. Enumeration via `WHERE created_by_user_id = :user_id`.

### D4 — Max 10 personal API keys per user (server-side enforced)

Per spec correction §3. Backend `service_account_service.create_for_current_user()` validates `count(WHERE created_by_user_id = :user_id, status='active') < 10` BEFORE creating; rejects with HTTP 400 + clear error. UI disables the create button at the limit.

### D5 — MFA step-up required for API key creation when MFA enabled

Per FR-652. The new endpoint accepts an optional `mfa_token: str | None` field; if `current_user.mfa_enrolled` is True AND `mfa_token` is None, the endpoint returns 401 with `mfa_required` claim. The frontend triggers an MFA challenge dialog; on completion, the request is retried with the `mfa_token`.

### D6 — `RedisSessionStore.list_sessions_by_user` extension

Per research R6. Reads the existing `user_sessions:{user_id}` Redis set (which already tracks per-user session IDs), fetches each session's detail via `get_session(user_id, session_id)`, returns sorted by `last_activity` DESC. NO new Redis keys.

### D7 — Per-session revocation refuses current session

Per spec edge case + User Story 5 acceptance scenario 4. The new `DELETE /me/sessions/{session_id}` endpoint compares `session_id` to `current_user.session_id` (extracted from JWT claims); if equal, returns HTTP 400 with "You can't revoke the session you're currently using". The frontend disables the "Revoke" button on the current-session row.

### D8 — Self-service DSR uses identical backing service as admin-DSR

Per spec correction §10 + FR-656. The new `POST /me/dsr` endpoint calls `dsr_service.create_request(payload, requested_by=current_user.id)` with `subject_user_id=current_user.id` auto-pre-filled (per Rule 46 — no `user_id` parameter accepted). The audit emits `source=self_service`. The existing admin-DSR path emits `source=admin` + Rule 34 double-audit when actor != subject.

### D9 — `AuditChainService.list_entries_by_actor_or_subject` extension

Per research R9 + FR-657. New method accepts `actor_id: UUID | None`, `subject_id: UUID | None`, `start_ts`, `end_ts`, `limit`, `cursor`. SQL: `WHERE actor_id = :actor_id OR subject_id = :subject_id` (OR semantics — show actions BY the user OR DONE TO the user). Cursor-based pagination via composite cursor `(timestamp DESC, id DESC)`.

### D10 — One-time API-key-value display via response-then-redacted pattern

Per Rule 31 + FR-652. The `POST /me/service-accounts` endpoint response includes the raw API key value ONCE in the response body (`api_key: str`). The backend NEVER persists the raw value (only `api_key_hash` per the existing `ServiceAccountCredential` model); subsequent `GET` calls return only the metadata + hash prefix (`msk_...3a4f`) for identification. The frontend's `<ApiKeyOneTimeDisplay>` component renders the value with copy + clear-on-dismiss behaviour.

### D11 — Mandatory events (security.*, incidents.*) cannot be disabled

Per FR-651 + User Story 2 acceptance scenario 2. The new `PUT /me/notification-preferences` endpoint validates each event_type's per-channel-preferences; for events in the mandatory-list (`security.*`, `incidents.*`), the validator REJECTS any attempt to disable all channels (must have ≥ 1 channel enabled). The UI locks these toggles + tooltip "This event is mandatory; it cannot be disabled".

### D12 — Quiet hours bypass for critical events

Per User Story 2 acceptance scenario 3. The notification-delivery scheduler reads the user's `quiet_hours` JSONB column; for non-critical events, queues the delivery for the next non-quiet boundary; for critical events (`incidents.*`, `security.*`), bypasses quiet hours and delivers immediately.

### D13 — Alembic migration `070` (or next available slot)

Per research R10 — UPD-040 owns 069+; UPD-041 follows; UPD-042 owns the next available. Migration adds 3 columns to `user_alert_settings` + 1 column to `service_account_credentials`. Reversible downgrade.

## Phase 2 — Track A Build Order (Backend `/me/*` aggregator + extensions)

**Days 1-3 (1 dev). Depends on UPD-040 + UPD-041 being on `main`.**

1. **Day 1 morning** — Pre-flight check: confirm UPD-040 + UPD-041 are merged on `main`; confirm `apps/control-plane/src/platform/common/secret_provider.py` exists; confirm migration sequence is at `069_oauth_provider_env_bootstrap.py` (research R10) so `070` is the next slot.
2. **Day 1 morning** — Create Alembic migration `070_user_self_service_extensions.py` per design D2 + D13: 3 new JSONB columns on `user_alert_settings` + 1 new UUID column on `service_account_credentials`. Reversible downgrade.
3. **Day 1 afternoon** — Run migration locally; verify both upgrade + downgrade work cleanly without data loss in existing rows.
4. **Day 1 afternoon** — Modify `notifications/models.py:51-79`: add 3 new JSONB columns to `UserAlertSettings`. Modify `auth/models.py:111-129`: add `created_by_user_id` column to `ServiceAccountCredential`.
5. **Day 2 morning** — Create `me/router.py` with the 16 new endpoint signatures + `me/schemas.py` with all Pydantic request/response schemas. Wire into `main.py` via `app.include_router(me_router, prefix="/api/v1")`.
6. **Day 2 morning** — Implement sessions endpoints: `GET /me/sessions` (list), `DELETE /me/sessions/{id}` (revoke per design D7), `POST /me/sessions/revoke-others` (bulk). Add `RedisSessionStore.list_sessions_by_user(user_id)` per design D6.
7. **Day 2 afternoon** — Implement service-account self-service endpoints: `GET/POST /me/service-accounts`, `DELETE /me/service-accounts/{id}`. MFA step-up per design D5; max-10-per-user per design D4; scope-subset enforcement per spec edge case.
8. **Day 2 afternoon** — Implement consent self-service endpoints: `GET /me/consent`, `POST /me/consent/revoke`, `GET /me/consent/history`. Reuse existing `consent_service` from research R7.
9. **Day 3 morning** — Implement DSR self-service endpoints: `POST /me/dsr`, `GET /me/dsr`, `GET /me/dsr/{id}`. Use the existing `dsr_service.create_request(payload, requested_by=current_user.id)` per design D8 + research R8.
10. **Day 3 morning** — Implement activity endpoint: `GET /me/activity`. Add `AuditChainService.list_entries_by_actor_or_subject` per design D9 + research R9 with cursor pagination.
11. **Day 3 afternoon** — Implement notification-preferences-extended endpoints: `GET /me/notification-preferences` (returns the new JSONB columns + the 3 existing columns), `PUT /me/notification-preferences` (validates mandatory events per design D11; updates JSONB + existing columns). Implement `POST /me/notification-preferences/test/{event_type}` per FR-651.
12. **Day 3 afternoon** — Add `POST /me/alerts/mark-all-read` to the existing `notifications/router.py` per D1.
13. **Day 3 afternoon** — Wire 10 new audit-event types per spec correction §8 (e.g., `auth.session.revoked`, `auth.api_key.created`, `privacy.consent.revoked`, `privacy.dsr.submitted`).
14. **Day 3 afternoon** — Author CI static-analysis check at `scripts/check-me-endpoint-scope.py` per Rule 46: scans all `/me/*` endpoints; rejects any that declare a `user_id` parameter. Wire into CI.

Day-3 acceptance: `pytest apps/control-plane/tests/me/` passes (~50 unit tests covering the 17 endpoints); the new aggregator router is reachable at `/api/v1/me/*`; the static-analysis check passes; the migration is reversible.

## Phase 3 — Track B Build Order (Frontend pages + `<NotificationBell>` upgrade)

**Days 1-6 (1-2 devs in parallel; can start day 1 with placeholder Zod schemas before Track A schemas land).**

15. **Day 1 morning** — Upgrade `<NotificationBell>` per R1: change `limit=20` to `limit=5` for the dropdown query; add "See all" link to `/notifications`. Verify cross-tab sync still works (existing `useAlertFeed` hook). Total: ~30 lines of net diff.
16. **Day 1 afternoon** — Create `apps/web/lib/api/me.ts` with fetch wrappers for all 17 new endpoints + `apps/web/lib/schemas/me.ts` with Zod schemas mirroring backend Pydantic. Use placeholder schemas if Track A hasn't shipped Pydantic yet.
17. **Day 1 afternoon** — Create `apps/web/lib/hooks/use-me-{sessions,api-keys,consent,dsr,activity,notification-preferences}.ts` (6 NEW TanStack Query hooks).
18. **Day 2 morning** — Author `/notifications/page.tsx` (full inbox) + 3 sub-components (`NotificationFilters`, `NotificationListItem`, `NotificationBulkActions`). Read from existing `GET /me/alerts` + new `POST /me/alerts/mark-all-read`.
19. **Day 2 afternoon** — Author `/settings/notifications/page.tsx` + 4 sub-components (`EventChannelMatrix`, `QuietHoursForm`, `DigestModeSelect`, `TestNotificationButton`). Mandatory events UI-locked per design D11.
20. **Day 3 morning** — Author `/settings/api-keys/page.tsx` + 3 sub-components (`ApiKeyCreateDialog` with MFA step-up + scope picker, `ApiKeyOneTimeDisplay` per design D10, `ApiKeyTable`).
21. **Day 3 afternoon** — Author `/settings/security/page.tsx` (overview with 3 link cards: MFA, Sessions, Activity).
22. **Day 4 morning** — Author `/settings/security/mfa/page.tsx` + 4 sub-components (`MfaEnrollFlow` stepper, `QRCodeDisplay`, `BackupCodesDisplay` per Rule 31, `DisableMfaDialog`). Reuse existing `qrcode.react` if present in `package.json`; else add.
23. **Day 4 afternoon** — Author `/settings/security/sessions/page.tsx` + `SessionList` sub-component. Current-session "This session" badge per design D7.
24. **Day 5 morning** — Author `/settings/security/activity/page.tsx` + `ActivityFilters` sub-component. Cursor-based pagination via TanStack Query `useInfiniteQuery`.
25. **Day 5 afternoon** — Author `/settings/privacy/consent/page.tsx` + 3 sub-components (`ConsentCard`, `RevokeConsentDialog` with consequences copy, `ConsentHistoryTab`).
26. **Day 5 afternoon** — Author `/settings/privacy/dsr/page.tsx` + 2 sub-components (`DsrSubmissionForm` with irreversibility warning for erasure, `DsrStatusList`).
27. **Day 6 morning** — i18n integration: extract ~80 new strings to `apps/web/messages/en.json` under `notifications.*`, `apiKeys.*`, `security.*`, `privacy.*` namespaces per R10. Commit with TODO markers for the 5 other locales (vendor-translated per UPD-039 / FR-620).
28. **Day 6 morning** — Run `pnpm test:i18n-parity` (or UPD-088's parity check command) — verify catalogs in 6 locales have all new keys; flag missing.
29. **Day 6 afternoon** — Run axe-core scan on all 9 new pages locally (`pnpm dev` + browser scan); verify zero AA violations per Rule 41 inheritance from UPD-083. Fix any violations introduced.
30. **Day 6 afternoon** — Run `pnpm test`, `pnpm typecheck`, `pnpm lint` to verify all CI gates pass.

Day-6 acceptance: 9 new pages render correctly against the live Track A backend; `pnpm test`, `pnpm typecheck`, axe-core scan all pass; i18n parity check clean.

## Phase 4 — Track C Build Order (E2E + journey extensions)

**Days 4-6 (1 dev — depends on Track A endpoints functional + Track B pages reachable).**

31. **Day 4 morning** — Create `tests/e2e/suites/self_service/__init__.py` + `conftest.py` with shared fixtures (logged-in user with seeded `UserAlert` rows, MFA-enabled user, multi-session user via synthetic Redis seed).
32. **Day 4 morning** — Create `test_notification_inbox.py` (~5 cases covering User Story 1: bell badge, dropdown, inbox pagination, filters, mark-all-read).
33. **Day 4 afternoon** — Create `test_notification_preferences.py` (~6 cases covering User Story 2: matrix UI, mandatory events, quiet hours, digest mode, test-notification action).
34. **Day 5 morning** — Create `test_api_keys.py` (~5 cases covering User Story 3: MFA step-up, one-time display, max-10 limit, scope-subset rejection, revocation propagation ≤ 5s).
35. **Day 5 morning** — Create `test_mfa_enrollment.py` (~5 cases covering User Story 4: stepper flow, QR + manual entry, backup codes one-time display, regenerate with TOTP step-up, disable refused under admin policy).
36. **Day 5 afternoon** — Create `test_session_revocation.py` (~5 cases covering User Story 5: list rendering, per-session revoke, current-session-refusal per D7, bulk revoke-others, propagation ≤ 60s).
37. **Day 5 afternoon** — Create `test_consent_management.py` + `test_self_service_dsr.py` + `test_audit_trail.py` (User Stories 6 + 7 + FR-657 — ~13 cases total).
38. **Day 6 morning** — Extend `tests/e2e/journeys/test_j03_consumer_discovery_execution.py`: add 4 new `journey_step()` blocks covering notification-center flow (consumer receives alert → opens bell → reads inbox → updates preferences).
39. **Day 6 morning** — Extend `tests/e2e/journeys/test_j10_multi_channel_notifications.py`: add 2 new steps cross-linking admin-DSR submission (existing path) with self-service-DSR submission (new path); verify both produce identical `PrivacyDSRRequest` rows + Rule 34 double-audit for admin-on-behalf-of-user.
40. **Day 6 afternoon** — Modify `.github/workflows/ci.yml`: add `tests/e2e/suites/self_service/` to UPD-040's matrix-CI test path (3 secret modes: `mock`, `kubernetes`, `vault`). Verify all 8 test files pass in all 3 modes.

Day-6 acceptance: 8 E2E test files + J03 extension + J10 extension all pass; matrix CI green for all 3 secret modes.

## Phase 5 — Cross-cutting concerns

**Day 7 (1 dev).**

41. **Day 7 morning** — Run the canonical secret-leak regex set against `kubectl logs platform-control-plane-...` for 24 hours of synthetic load (API key creation + MFA enrollment + DSR submission + consent revocation flows) per SC-014; verify zero matches per Rule 31.
42. **Day 7 morning** — Run `python scripts/check-me-endpoint-scope.py` (T032 deliverable) — verify zero `/me/*` endpoints accept `user_id` parameter per Rule 46.
43. **Day 7 afternoon** — Verify all 17 new endpoints emit audit-chain entries per Rule 9 (synthetic test: hit each endpoint, verify the `audit_chain_entries` table grows by exactly 1 row).

## Phase 6 — SC verification + documentation polish

**Days 7-9 (1 dev).**

44. **Day 7-8** — Run the full SC verification sweep per the spec's 20 SCs. Capture verification record at `specs/092-user-notification-self-service/contracts/sc-verification.md` (NEW file).
45. **Day 8 morning** — If UPD-039 has landed, modify `docs/operator-guide/runbooks/`: add 4 new runbooks (notification-preferences-troubleshooting, mfa-self-service-issues, session-revocation-incident, dsr-self-service-flow). If UPD-039 has not landed, runbooks live in `specs/092-user-notification-self-service/contracts/` and merge into UPD-039 later per design D14 below.
46. **Day 8 afternoon** — If UPD-039 has landed, modify `docs/admin-guide/`: add a "Self-Service Surfaces" section explaining how admin features at UPD-036 admin tab cross-reference the user-self equivalents (e.g., admin can override consent on behalf of user; user has reciprocal self-service path).
47. **Day 9** — Modify `docs/release-notes/v1.3.0/` — add UPD-042 release-notes entry covering 9 new pages + 17 new endpoints + breaking-change note (NONE — UPD-042 is purely additive).
48. **Day 9** — Final review pass; address PR feedback; merge.

### D14 — UPD-039 documentation integration is BEST-EFFORT

Mirrors UPD-040 / UPD-041 design D10. If UPD-039 has landed, runbooks + admin-guide updates live under `docs/`; if delayed, they live in `specs/092-user-notification-self-service/contracts/` and merge into UPD-039 later.

## Effort & Wave

**Total estimated effort: 10-12 dev-days** (5-6 wall-clock days with 3 devs in parallel: 1 on Track A, 1 on Track B, 1 on Track C; convergent on Days 7-9).

The brownfield's "5 days (5 points)" understates by ~50% (consistent with v1.3.0 cohort pattern):
- The 9 new pages × ~250 lines each = ~2250 lines (vs the brownfield's implicit 1-page-per-day × 9 days ≈ 9 days for UI alone).
- The new `me/router.py` aggregator + 17 endpoints + 5 service-method extensions = ~3 dev-days (vs the brownfield's "1 day").
- The 6 i18n catalogs × 80 new strings = ~480 entries — the parity check + vendor coordination adds ~0.5 day.
- The Playwright × 25 scenarios + axe-core sweep = ~1 day.
- The 8 E2E test files + journey extensions = ~2 days.

**Wave: Wave 17** — last in the v1.3.0 audit-pass cohort. Position in execution order:
- Wave 11 — UPD-036 Administrator Workbench
- Wave 12 — UPD-037 Public Signup Flow
- Wave 13 — UPD-038 Multilingual README
- Wave 14 — UPD-039 Documentation Site
- Wave 15 — UPD-040 HashiCorp Vault Integration
- Wave 16 — UPD-041 OAuth Env-Var Bootstrap + Admin UI
- **Wave 17 — UPD-042 User-Facing Notification Center + Self-Service Security** (this feature)

**Cross-feature dependency map**:
- UPD-042 INTEGRATES with UPD-036 (admin equivalents shipped first; the user-self surfaces are reciprocal).
- UPD-042 INTEGRATES with UPD-037 (consent capture at signup; UPD-042 ships ongoing-management).
- UPD-042 INTEGRATES with UPD-040 + UPD-041 (matrix-CI + audit-event source-classification + secret-leak CI inherited).
- UPD-042 INTEGRATES with UPD-039 (docs auto-flow + runbook library).
- UPD-042 EXTENDS UPD-077 (multi-channel notifications — preferences matrix covers all 6 channels per spec correction §1).
- UPD-042 EXTENDS UPD-024 (audit chain — adds user-scoped query method).

## Risk Assessment

**Low-medium risk overall.** UPD-042 is mostly UI on proven backends. Risks:

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **R1: WebSocket subscription leaks (multiple tabs bloat connection count)** | Medium | Low (browser-side memory) | The existing `useAlertFeed` hook (research R1) coordinates via the WS hub's per-pod connection-pooling; each tab opens its own connection but the hub deduplicates by `(user_id, channel)`. SC-003 verifies cross-tab badge sync. |
| **R2: API key value leak via logs** | Low | High (credential exposure) | One-time display per design D10; UPD-040's `scripts/check-secret-access.py` extended in T032 to scan for any `api_key=...` patterns in logger calls; CI fails any new code path that logs the value. |
| **R3: Session revocation race (revoke own session while another tab mid-request)** | Medium | Low (UX — graceful degradation) | Backend tolerates short-lived revoked tokens during 60-second propagation window per SC-013; UI shows "Session expired; please log in again" gracefully on 401 receipt. |
| **R4: Self-service DSR abuse (user spams erasure requests)** | Low | Medium (operational load) | Server-side rate limit per user (1 erasure per 24h — added in T020); typed-confirmation per spec edge case; admin notification on submission per UPD-024. |
| **R5: Schema migration breaks existing users (`UserAlertSettings` extension)** | Low | High (data loss / startup failure) | Per design D2 — column-extension with NOT NULL DEFAULT preserves existing rows; reversible downgrade verified in T002. |
| **R6: Mandatory-event UI lock bypass (user crafts a direct API call to disable security.* events)** | Low | High (security — user disables critical alerts) | Server-side validator per design D11 rejects any payload that disables a mandatory event; UI lock is defense-in-depth, not the security boundary. |
| **R7: Quiet hours timezone mishandling (user in Europe sees notifications at wrong hour)** | Medium | Low (UX) | Per design D12 — backend stores `quiet_hours.timezone` (e.g., `"Europe/Rome"`); the scheduler resolves user's local time at delivery time; SC-006 verifies E2E. |
| **R8: i18n catalog drift across 6 locales** | Medium | Low (untranslated strings) | UPD-088's parity check (already shipped) catches drift; 7-day grace window applies; vendor-translated catalogs per FR-620. |
| **R9: Cross-feature documentation lag (UPD-039 not landed)** | Medium | Low (deferred docs) | Per D14 — runbooks live in feature spec dir if UPD-039 not shipped; merge later. |

## Plan-correction notes (vs. brownfield input)

1. **Effort estimate corrected from 5 days to 10-12 dev-days.** Brownfield understates by ~50% (consistent with features 085-091 pattern).
2. **Wave 17 reaffirmed.** Brownfield correctly identifies; this plan reaffirms.
3. **`<NotificationBell>` is FULLY IMPLEMENTED**, not a placeholder per spec correction §6 + research R1. Track B scope SHRINKS for this component.
4. **`/me/notifications/*` URL is WRONG** — existing endpoints are `/me/alerts/*` per spec correction §2 + research R2. Plan uses canonical paths.
5. **MFA endpoints prefix is `/api/v1/auth/mfa/*`**, NOT `/mfa/*` per spec correction §4.
6. **WebSocket uses existing `ALERTS` channel**, not `user.notification.new` per spec correction §5 + research R14.
7. **No dedicated `/api/v1/me` aggregator exists today** per research R5 + R15. Plan creates NEW `me/router.py`.
8. **`UserAlertSettings` schema extension is REQUIRED** per spec correction §7 + design D2 — the existing 3 columns are insufficient.
9. **`RedisSessionStore.list_sessions_by_user` is NEW** per research R6 — does not exist today.
10. **`AuditChainService.list_entries_by_actor_or_subject` is NEW** per research R9 + FR-657.
11. **Service accounts: NEW `created_by_user_id` column** per research R8 + design D3 distinguishes self-service from admin-created.
12. **Max 10 personal API keys per user** per design D4 + spec correction §3.
13. **Mandatory events server-side validator** per design D11 — UI lock is defense-in-depth.
14. **DSR self-service uses identical backing service as admin** per design D8 + research R8 — consistent rows + audit pattern.
15. **Audit query is OR-semantics (actor OR subject)** per design D9 — shows actions BY the user OR DONE TO the user.
16. **Migration 070 (or next available)** per research R10 — sequence depends on UPD-040/041 final count.

## Complexity Tracking

| Area | Complexity | Why |
|---|---|---|
| `me/router.py` aggregator | Medium | 16 endpoints + 17 schemas + delegation to 5 existing services. Mostly orchestration + auth scope. |
| Sessions enumeration extension | Low | Single new method on `RedisSessionStore`; reuses existing `user_sessions:{user_id}` set. |
| Audit query extension | Medium | Cursor-based pagination + composite index needed for performance; extends existing repository. |
| Schema migration (3 + 1 columns) | Low | Pure additive; reversible. |
| 9 NEW Next.js pages | High | ~2250 lines of TSX + ~30 sub-components + i18n × 6 locales + Playwright × 25 scenarios. |
| `<NotificationBell>` upgrade | Trivial | ~30 lines of net diff. |
| 8 E2E test files | Medium | One per User Story; conftest fixtures reused. |
| Journey extensions (J03 + J10) | Low | Sequential `journey_step` blocks added to existing 31,924 + 7,000-byte files. |
| i18n + axe-core sweep | Medium | 480 entries × 6 locales + AA scan on 9 pages. |

**Net complexity: medium.** The frontend volume (Track B) is the highest-effort piece; once the components are right, the rest is mechanical.
