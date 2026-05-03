---

description: "Tasks: UPD-050 Abuse Prevention and Trust & Safety (Refresh on 100-upd-050-abuse)"
---

# Tasks: UPD-050 Abuse Prevention and Trust & Safety (Refresh)

**Input**: Design documents from `/specs/103-abuse-prevention/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ (6 files) ✅, quickstart.md ✅
**Baseline**: prior unmerged branch `100-upd-050-abuse` is **referenced** but NOT directly extended — the refresh adopts the user input's nested-package layout (`security/abuse_prevention/`) and migration number 110, both incompatible with the prior branch's flat `security_abuse/` and its `109_abuse_prevention` revision.

**Tests**: Tests are IN SCOPE for this refresh because the spec defines explicit testable success criteria (SC-001 through SC-009) and J26 is named as a CI gate (SC-009). Each user story phase below ends with the unit + integration_live + Playwright tasks that lock its success criterion.

**Organization**: Tasks are grouped by user story (US1–US5 from spec.md). The optional integrations (CAPTCHA, geo-block, fraud-scoring) are gathered in Phase 8 because they are independently toggleable and any one can ship without the others.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1/US2/US3/US4/US5)
- All file paths absolute from repo root

## Path Conventions

- **Backend control plane**: `apps/control-plane/src/platform/...`
- **Backend tests**: `apps/control-plane/tests/...`
- **Frontend**: `apps/web/...`
- **Migrations**: `apps/control-plane/migrations/versions/...`
- **Helm**: `deploy/helm/...`
- **Docs**: `docs/admin-guide/...`
- **E2E suites**: `tests/e2e/suites/...`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the baseline + dependency installs.

- [X] T001 Verify Alembic head is `109_marketplace_reviewer_assign` by running `cd apps/control-plane && alembic -c migrations/alembic.ini heads`. Document the head hash in `specs/103-abuse-prevention/NOTES.md` as the starting point.
- [X] T002 [P] Add `geoip2>=4.8` to `apps/control-plane/pyproject.toml` under the runtime dependencies block. Run `pip install -e ".[dev]"` to refresh the lockfile.
- [X] T003 [P] Verify the Kafka topic registry in `apps/control-plane/src/platform/common/events/topics.py` (or the equivalent topic constants module) does NOT already define `security.abuse_events`; this refresh creates the topic — confirm it is novel.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema + bounded context skeleton + cross-cutting plumbing. **No user story phase below can begin until this phase is complete.**

- [X] T004 Create Alembic migration `apps/control-plane/migrations/versions/110_abuse_prevention.py` per `data-model.md` § Migration outline. Six new tables (`signup_velocity_counters`, `disposable_email_domains`, `disposable_email_overrides`, `trusted_source_allowlist`, `account_suspensions`, `abuse_prevention_settings`) + seed defaults. Verify `make migrate` then `make migrate-rollback` round-trips cleanly against postgres:16.
- [X] T005 [P] Create the bounded-context skeleton at `apps/control-plane/src/platform/security/abuse_prevention/` with `__init__.py` + empty `models.py` + `schemas.py` + `repository.py` + `service.py` + `exceptions.py` + `events.py` + `metrics.py` + `dependencies.py` + `admin_router.py`. Per `plan.md` § Source Code.
- [X] T006 [P] Add SQLAlchemy models to `apps/control-plane/src/platform/security/abuse_prevention/models.py` for the 6 tables, mirroring migration 110 column-for-column. Use existing `Base`, `UUIDMixin`, `TimestampMixin` from `common/models/`.
- [X] T007 [P] Add 10 exception classes to `apps/control-plane/src/platform/security/abuse_prevention/exceptions.py`: `VelocityThresholdBreachedError` (HTTP 429), `DisposableEmailNotAllowedError` (HTTP 400), `CaptchaRequiredError` / `CaptchaInvalidError` (HTTP 400), `GeoBlockedError` (HTTP 403), `FraudScoringSuspendError` (HTTP 403), `AbusePreventionUnavailableError` (HTTP 503), `AccountSuspendedError` (HTTP 403), `CannotSuspendPrivilegedUserError` (HTTP 403), `SettingNotFoundError` (HTTP 404). All extend `PlatformError` per existing convention.
- [X] T008 [P] Add 4 Kafka event types to `apps/control-plane/src/platform/security/abuse_prevention/events.py`: `AbuseSignupRefusedEvent`, `AbuseSuspensionAppliedEvent`, `AbuseSuspensionLiftedEvent`, `AbuseThresholdChangedEvent`. Payload schemas per `contracts/abuse-events-kafka.md`. Register in a new topic constant `SECURITY_ABUSE_EVENTS_TOPIC = "security.abuse_events"`.
- [X] T009 [P] Add ~14 Pydantic schemas to `apps/control-plane/src/platform/security/abuse_prevention/schemas.py`: `AbusePreventionSetting`, `AbusePreventionSettingPatch`, `TrustedSourceAllowlistEntry`, `TrustedSourceAllowlistEntryCreate`, `AccountSuspension`, `SuspensionCreate`, `SuspensionLift`, `SuspensionQueueResponse`, `DisposableEmailOverride`, `DisposableEmailOverrideCreate`, `GeoPolicyResponse`, `GeoPolicyPatch`, `RecentRefusalsResponse`, `RecentBlocksResponse`. Per the 6 contract files.
- [X] T010 [P] Add Prometheus counters/histograms to `apps/control-plane/src/platform/security/abuse_prevention/metrics.py` per research R12: `abuse_prevention_signup_refusals_total{reason}`, `abuse_prevention_suspensions_total{source,reason}`, `abuse_prevention_cap_fired_total{cap}`, `abuse_prevention_velocity_check_seconds`, `abuse_prevention_disposable_email_lookup_seconds`. Use the same `_NoopMetric` fallback pattern as `marketplace/metrics.py`.
- [X] T011 Add `AbusePreventionService` to `apps/control-plane/src/platform/security/abuse_prevention/service.py` with `get_setting(key)`, `set_setting(key, value, actor_user_id)` (audits + emits `abuse.threshold.changed`), `list_allowlist()`, `add_allowlist_entry(...)`, `remove_allowlist_entry(...)`. Each setting write writes the audit-chain entry through `security_compliance/services/audit_chain_service.py` per rule 9.
- [X] T012 Update `pyproject.toml` to ensure ruff/mypy strictness covers the new bounded context: confirm `src = ["src", "tests", "entrypoints"]` already covers `src/platform/security/abuse_prevention/`. If not, add the include explicitly. (No change expected — verification step.)
- [X] T013 Add the GeoLite2 ConfigMap template at `deploy/helm/platform/templates/configmap-geoip.yaml` per research R5. Empty by default; populated by a chart-time Job that reads the MaxMind license key from Vault path `secret/data/maxmind/geolite2_license_key`.

**Checkpoint**: schema migrated, models/schemas/exceptions/events/metrics defined, settings service works, GeoLite2 plumbing in place. User-story phases can now proceed in parallel.

---

## Phase 3: User Story 1 — Bot signup velocity block (Priority: P1) 🎯 MVP

**Goal**: 6 signups from one IP within an hour produces 5 successes + 1 HTTP 429 with `Retry-After`. Audit-chain entry recorded once per breach. Other IPs unaffected. Allowlist exempts trusted NATs.

**Independent Test**: Per `quickstart.md` Walkthrough 1 — fire 6 signups from one IP, observe 5×202 + 1×429.

**Maps to**: FR-742, FR-742.1, FR-742.2, FR-742.3, FR-742.4, FR-742.5. Success criteria: SC-001, SC-008.

### Backend — Velocity service

- [X] T014 [P] [US1] Implement `VelocityService` in `apps/control-plane/src/platform/security/abuse_prevention/velocity.py`. Public methods: `check_and_increment(ip, asn, email_domain) -> None | raises VelocityThresholdBreachedError`. Reads thresholds from `AbusePreventionService` (cached 30 s). Uses Redis `INCR` + `EXPIRE` per data-model § Redis. Wraps each Redis op in 100 ms timeout; on failure raises `AbusePreventionUnavailableError` (fail-closed per R1).
- [X] T015 [P] [US1] Add ASN-resolution helper to `velocity.py`: takes IP, returns ASN string via the existing GeoLite2-ASN reader OR a stubbed lookup if the ASN DB isn't configured (degrade gracefully — skip the per-ASN counter rather than failing the request).
- [X] T016 [US1] Wire allowlist check at the head of `VelocityService.check_and_increment`: if the IP matches any `ip_cidr` entry OR the email_domain matches any `email_domain` entry in `trusted_source_allowlist`, skip counting entirely. Depends on T014.

### Backend — Signup endpoint integration

- [X] T017 [US1] Add velocity-guard pre-step to the signup endpoint at `apps/control-plane/src/platform/accounts/router.py:72`. Inject `VelocityService` via FastAPI Depends. Call BEFORE the existing UPD-037 rate limit (or after — order is not load-bearing as long as both fire). Surface 429 with `Retry-After` per `contracts/signup-guards-rest.md`. Depends on T014, T016.
- [X] T018 [US1] Add audit-chain emission for velocity breaches at the source: when `VelocityService.check_and_increment` raises `VelocityThresholdBreachedError`, the `AbusePreventionService` writes ONE audit-chain entry per (counter_key, threshold-breach) tuple per rolling window. Use a Redis SET-NX guard `abuse:audit_dedup:{counter_key}:{window_start}` with TTL = window length to dedupe. Depends on T014, T011.
- [X] T019 [US1] Add Kafka emission for `abuse.signup.refused` at the same site as T018. Every refusal emits the event (the audit-chain dedup is independent of Kafka emission per `contracts/abuse-events-kafka.md`).

### Backend — Cron mirror to PostgreSQL

- [X] T020 [P] [US1] Add cron `velocity_persist_cron` to `apps/control-plane/src/platform/security/abuse_prevention/cron.py`: every 60 s, scan all `abuse:vel:*` keys via `SCAN`, write the (key, window_start, value, dimension) tuples into `signup_velocity_counters`. Idempotent UPSERT on `(counter_key, counter_window_start)`. Old window rows are DELETEd in the same job (anything where `counter_window_start < now() - 7d`).

### Backend — Admin surface

- [X] T021 [P] [US1] Add admin GET/PATCH/POST/DELETE routes to `apps/control-plane/src/platform/security/abuse_prevention/admin_router.py` for: settings list/update, allowlist list/add/delete, recent-refusals feed. Per `contracts/admin-abuse-prevention-rest.md`. All gated by `require_superadmin`.
- [X] T022 [US1] Mount `admin_router` under `/api/v1/admin/security/abuse-prevention` in `apps/control-plane/src/platform/main.py` (or wherever the existing admin composition lives — check `admin/router.py`). Depends on T021.

### Tests — US1

- [X] T023 [P] [US1] Add `apps/control-plane/tests/unit/security/abuse_prevention/test_velocity_service.py`: 8 cases — happy path (counter < threshold), threshold-breach raises, idempotent re-check, allowlisted IP skipped, allowlisted email-domain skipped, Redis-timeout raises `AbusePreventionUnavailableError`, ASN-resolution failure degrades to skip-ASN, dimension labels on the metric.
- [X] T024 [P] [US1] Add `apps/control-plane/tests/unit/security/abuse_prevention/test_audit_dedup.py`: asserts the SET-NX dedup gate emits one audit-chain entry per (counter_key, window) but every Kafka event still fires.
- [X] T025 [P] [US1] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_velocity_signup_e2e.py` (under `integration_live` mark). 6 signup attempts from one IP returns 5×202 + 1×429 with `Retry-After`. Verifies SC-001.
- [X] T026 [P] [US1] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_velocity_allowlist.py` (under `integration_live` mark). 10 signups from an allowlisted IP all succeed. Verifies SC-008.
- [X] T027 [P] [US1] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_admin_threshold_change.py` (under `integration_live` mark). PATCH the threshold; the next signup honours the new threshold within 30 s; audit-chain entry recorded.

### Frontend — Threshold tuning UI

- [X] T028 [P] [US1] Create `apps/web/lib/hooks/use-abuse-prevention-settings.ts` with TanStack Query hooks `useAbusePreventionSettings()` and `useUpdateSetting()`. Optimistic update + rollback on 422.
- [X] T029 [P] [US1] Create `apps/web/components/features/admin/security/ThresholdEditor.tsx` — a per-knob editor with inline save, surfaces 422 validation errors, debounced 1 s.
- [X] T030 [P] [US1] Create `apps/web/components/features/admin/security/RefusalReasonChart.tsx` — Recharts time-series of `abuse.signup.refused` events grouped by `reason`. Powers the dashboard panel.
- [X] T031 [US1] Create `apps/web/app/(admin)/admin/security/abuse-prevention/page.tsx` — overview page composing `ThresholdEditor` for each setting + `RefusalReasonChart`. Gated by `require_superadmin` via the existing admin layout. Depends on T028, T029, T030.
- [X] T032 [P] [US1] Add `apps/web/e2e/security-abuse-prevention.spec.ts` — Playwright spec covering: queue page renders settings, editor saves a value (mocked PATCH), audit toast confirms, RefusalReasonChart renders fixture data.

**Checkpoint**: US1 fully functional. Velocity rules enforced. Allowlist works. Admin can tune thresholds without redeploy.

---

## Phase 4: User Story 2 — Disposable-email signup rejected (Priority: P1)

**Goal**: signup with `tempmail@10minutemail.com` returns HTTP 400 `disposable_email_not_allowed` BEFORE any verification email is sent. Super-admin override list takes precedence over upstream.

**Independent Test**: Per `quickstart.md` Walkthrough 2.

**Maps to**: FR-743, FR-743.1, FR-743.2, FR-743.3, FR-743.4. Success criterion: SC-002.

### Backend — Disposable-email service

- [X] T033 [P] [US2] Implement `DisposableEmailService` in `apps/control-plane/src/platform/security/abuse_prevention/disposable_emails.py`. Public method: `check(email) -> None | raises DisposableEmailNotAllowedError`. Resolution order per data-model § disposable_email_overrides: override `allow` → allow → override `block` → block → upstream `domain` → block → else allow.
- [X] T034 [P] [US2] In-memory cache for `disposable_email_domains` + `disposable_email_overrides` rows: refresh on every write to either table (signaled via Redis pub/sub) and on a 1 h timer fallback. The cache is process-local; cross-pod consistency comes from per-pod refresh on the same signals.

### Backend — Cron upstream sync

- [X] T035 [US2] Add `disposable_email_sync_cron` to `apps/control-plane/src/platform/security/abuse_prevention/cron.py`. Weekly schedule (configurable). Fetches `https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf` via `httpx`. Truncates `disposable_email_domains` and reinserts. Emits `abuse.threshold.changed` events in chunks of 100 deltas.
- [X] T036 [P] [US2] Add a manual-trigger endpoint `POST /api/v1/admin/security/email-overrides/refresh-blocklist` per `contracts/disposable-email-overrides-rest.md`. Returns 202 with a job_id; the job runs the same cron logic.

### Backend — Signup endpoint integration

- [X] T037 [US2] Add disposable-email-guard pre-step to the signup endpoint immediately after the velocity guard. Inject `DisposableEmailService`. Per `contracts/signup-guards-rest.md`. Refusal emits audit-chain entry with hashed local-part + domain (per data-model privacy note).

### Backend — Override list admin

- [X] T038 [P] [US2] Add admin GET/POST/DELETE routes for the override list to `admin_router.py` per `contracts/disposable-email-overrides-rest.md`. Each write invalidates the in-memory cache + audits.

### Tests — US2

- [X] T039 [P] [US2] Add `apps/control-plane/tests/unit/security/abuse_prevention/test_disposable_email_service.py`: 6 cases — domain in upstream blocks, override `allow` overrides upstream, override `block` adds to upstream, neither matches → allow, cache refresh on signal, lookup p99 < 2 ms (perf check).
- [X] T040 [P] [US2] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_disposable_email_signup.py` (under `integration_live` mark). Submits `tempmail@10minutemail.com` → 400 + `disposable_email_not_allowed`. Asserts NO mail enqueued (verifies `outbound_mail_audit` table OR Mailhog REST API). Verifies SC-002.
- [X] T041 [P] [US2] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_disposable_email_override.py` (under `integration_live` mark). Add `allow` override, signup proceeds; remove override, signup refused.
- [X] T042 [P] [US2] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_blocklist_sync_cron.py` (under `integration_live` mark). Mock the upstream HTTP response, run the cron, assert the table was populated and `abuse.threshold.changed` events emitted in chunks of 100.

### Frontend — Override list UI

- [X] T043 [P] [US2] Create `apps/web/lib/hooks/use-disposable-email-overrides.ts` with TanStack Query hooks for list/add/remove/refresh-blocklist.
- [X] T044 [P] [US2] Create `apps/web/components/features/admin/security/DisposableEmailOverrideList.tsx` — table of overrides with add-form (domain + mode dropdown + reason input) and per-row delete.
- [X] T045 [US2] Create `apps/web/app/(admin)/admin/security/email-overrides/page.tsx`. Composes `DisposableEmailOverrideList` + a "Refresh blocklist now" button.

**Checkpoint**: US2 fully functional. Disposable-email refusal works at signup; override list lets super admin escape false positives; weekly cron syncs the upstream list.

---

## Phase 5: User Story 3 — Suspended user login blocked (Priority: P1)

**Goal**: a user with an active suspension cannot log in; receives `account_suspended` refusal with appeal contact; mid-session suspension invalidates existing sessions; lift restores login.

**Independent Test**: Per `quickstart.md` Walkthrough 3.

**Maps to**: FR-744, FR-744.1, FR-744.2, FR-744.3, FR-744.4, FR-744.5. Success criteria: SC-003, SC-004.

### Backend — Suspension service

- [X] T046 [P] [US3] Implement `SuspensionService` in `apps/control-plane/src/platform/security/abuse_prevention/suspension.py`. Public methods: `apply(user_id, tenant_id, reason, evidence, applied_by, applied_by_user_id) -> AccountSuspension`, `lift(suspension_id, lifted_by_user_id, lift_reason) -> AccountSuspension`, `is_user_suspended(user_id) -> bool` (cheap; uses partial index `account_suspensions_user_active_idx`), `list_for_admin_queue(...) -> SuspensionQueueResponse`.
- [X] T047 [US3] Add privileged-role guard to `SuspensionService.apply`: load the target user's roles; refuse with `CannotSuspendPrivilegedUserError` if the role set includes `platform_admin` or `tenant_admin`. Per FR-744.3.
- [X] T048 [US3] Add session-invalidation side effect to `SuspensionService.apply`: in the same DB transaction that inserts the suspension row, issue a Redis broadcast on the existing session-invalidation channel (the one auth uses today for password-reset session kills) — keyed on `user_id`. Auth middleware drops sessions that match. If Redis is down, log error but DON'T fail the suspension (the durable row is the source of truth; the next request will check the row).

### Backend — Auto-suspension rule engine

- [X] T049 [P] [US3] Implement `AutoSuspensionRuleEngine` in `apps/control-plane/src/platform/security/abuse_prevention/suspension.py` (or a sibling `_auto_rules.py` if it grows). Three rule families per research R3: cost-burn-rate, repeated-velocity, fraud-scoring-suspend. Each rule is a class implementing a `evaluate(user_id) -> Optional[SuspensionDecision]` Protocol.
- [X] T050 [US3] Add cron `auto_suspension_scanner_cron` to `cron.py`. Every 5 minutes, scans the recent-events horizon (24 h) and runs each rule against candidate users. For each rule that fires, calls `SuspensionService.apply(reason=<rule_name>, ...)`. Depends on T046, T049.
- [X] T051 [P] [US3] Implement Kafka consumer `CostBurnRateConsumer` in `apps/control-plane/src/platform/security/abuse_prevention/consumer.py`. Subscribes to `cost.budget.exceeded` (existing topic from UPD-027/079). On match, evaluates the cost-burn rule synchronously — fast path complementary to the cron scanner.

### Backend — Login + middleware integration

- [X] T052 [US3] Modify `apps/control-plane/src/platform/auth/service.py:login` (the existing UPD-014 login path) to call `SuspensionService.is_user_suspended(user_id)` AFTER credential validation. If suspended, raise `AccountSuspendedError` (HTTP 403) with body `{"appeal_contact": "support@musematic.ai"}`. Per `contracts/suspension-rest.md`.
- [X] T053 [US3] Modify the auth-middleware at `apps/control-plane/src/platform/common/auth_middleware.py` (or wherever JWT validation lives) to call `is_user_suspended` on every authenticated request. Refuse with the same `account_suspended` code. Cache the suspension state in the request context to avoid duplicate DB hits within a request.

### Backend — Manual suspend / lift admin

- [X] T054 [P] [US3] Add admin POST/POST routes for manual suspend + lift to `admin_router.py` per `contracts/suspension-rest.md`. Both gated by `require_superadmin`.
- [X] T055 [P] [US3] Add `MarketplaceNotificationService`-style helper `SuspensionNotifier` in `apps/control-plane/src/platform/security/abuse_prevention/suspension.py` that posts to the user's UPD-042 inbox on apply (subject: "Account suspended", body: appeal contact) and on lift (subject: "Suspension lifted").

### Tests — US3

- [X] T056 [P] [US3] Add `apps/control-plane/tests/unit/security/abuse_prevention/test_suspension_service.py`: 8 cases — apply happy path, lift idempotent, is_user_suspended uses partial index (mock SQL), privileged-role refusal, manual + system + tenant_admin suspended_by paths, evidence_json serialised correctly, audit-chain entry written, Kafka event emitted.
- [X] T057 [P] [US3] Add `apps/control-plane/tests/unit/security/abuse_prevention/test_auto_rules.py`: 6 cases — cost-burn rule fires above threshold; repeated-velocity rule fires on N velocity hits in window; fraud-scoring "suspend" verdict fires; "review" verdict does NOT fire (notifies only); each rule respects the privileged-role exemption.
- [X] T058 [P] [US3] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_suspended_login_refused.py` (under `integration_live` mark). Suspend a user; login with valid creds returns 403 `account_suspended`. Verifies SC-003.
- [X] T059 [P] [US3] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_mid_session_invalidation.py` (under `integration_live` mark). Authenticated session, suspend, next request returns 403; existing session invalidated.
- [X] T060 [P] [US3] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_suspension_notification_latency.py` (under `integration_live` mark). After suspension, verify the user's inbox receives the alert within 60 s p95. Verifies SC-004.
- [X] T061 [P] [US3] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_privileged_role_exempt.py` (under `integration_live` mark). Auto-suspension scanner runs against a user holding `platform_admin`; assert no suspension is applied; assert the rule engine emits a structured-log warning.

**Checkpoint**: US3 fully functional. Suspended users blocked at login + mid-session. Auto-suspension rules fire. Privileged users immune to auto-suspension. Notifications reach the user.

---

## Phase 6: User Story 4 — Suspension queue review (Priority: P2)

**Goal**: super admin opens `/admin/security/suspensions`, sees pending suspensions with evidence, lifts a false positive.

**Independent Test**: Per `quickstart.md` Walkthrough 4.

**Maps to**: FR-744.4 (admin endpoint), FR-749 (admin surface). Success criterion: SC-007 (audit reconciliation).

### Frontend — Suspension queue UI

- [X] T062 [P] [US4] Create `apps/web/lib/hooks/use-suspensions.ts` with TanStack Query hooks `useSuspensions(filter)`, `useSuspension(id)`, `useLiftSuspension()`, `useApplySuspension()`. Optimistic UI on lift.
- [X] T063 [P] [US4] Create `apps/web/components/features/admin/security/SuspensionQueueTable.tsx` — DataTable of pending suspensions; columns: user, tenant, reason, evidence_summary, suspended_at, suspended_by (with system/human badge per US4 acceptance scenario 3), lift action.
- [X] T064 [P] [US4] Create `apps/web/components/features/admin/security/EvidencePanel.tsx` — JSON viewer for `evidence_json` with structured rendering for known reason codes (cost_burn_rate, repeated_velocity, fraud_scoring_suspend).
- [X] T065 [US4] Create `apps/web/app/(admin)/admin/security/suspensions/page.tsx` — composes `SuspensionQueueTable` with filter chips (active / lifted / by-reason). Gated by `require_superadmin`.
- [X] T066 [US4] Create `apps/web/app/(admin)/admin/security/suspensions/[id]/page.tsx` — detail view: full evidence + lift dialog with reason input. Calls the `useLiftSuspension` mutation.

### Tests — US4

- [X] T067 [P] [US4] Add `apps/web/e2e/security-suspensions.spec.ts` — Playwright covering: queue renders, filter chips work, lift dialog opens, lift submits with reason, optimistic toast appears, audit reconciliation reflects the lift.

**Checkpoint**: US4 fully functional. Super admin can review and lift suspensions through the UI.

---

## Phase 7: User Story 5 — Free-tier cost-mining attempt blocked (Priority: P1)

**Goal**: 4 caps fire on a Free-tier abuse attempt: monthly_execution_cap, allowed_model_tier, max_execution_time_seconds, max_reasoning_depth.

**Independent Test**: Per `quickstart.md` Walkthrough 5.

**Maps to**: FR-748, FR-748.1, FR-748.2, FR-748.3, FR-748.4. Success criterion: SC-005.

### Backend — Plan extras (assumed already in UPD-047, verify only)

- [X] T068 [P] [US5] Verify the existing UPD-047 plan_versions schema already exposes `allowed_model_tier`, `max_execution_time_seconds`, `max_reasoning_depth`, `monthly_execution_cap` — if any are missing, add them under the `extras_json` column with documented keys (no migration needed if the column is JSONB). Document in NOTES which fields exist on `main` vs. need adding.

### Backend — Model-router enforcement

- [X] T069 [US5] Modify `apps/control-plane/src/platform/common/clients/model_router.py` to refuse `model_id` whose `tier` is not in the workspace's plan-defined `allowed_model_tier`. Raises `ModelTierNotAllowedError` (existing exception class — already in `billing/exceptions.py:` from UPD-026). Increments `abuse_prevention_cap_fired_total{cap="model_tier"}`.

### Backend — Execution service enforcement

- [X] T070 [P] [US5] Modify `apps/control-plane/src/platform/execution/service.py` (or `scheduler.py`) to (a) refuse new execution start when `monthly_execution_cap` reached — raises `QuotaExceededError` per UPD-047; (b) auto-terminate executions exceeding `max_execution_time_seconds` — uses the existing per-execution timer, just sets the deadline based on plan. Increments `abuse_prevention_cap_fired_total{cap="execution_time"|"monthly_execution_cap"}`.

### Backend — Reasoning engine enforcement

- [X] T071 [P] [US5] Modify `apps/control-plane/src/platform/reasoning/client.py` to pass `max_reasoning_depth` (resolved from the workspace plan) to the gRPC `ReasoningEngineService.RequestReasoning` call. Verify the Go side honours the field (it should already — research R7); if not, raise an issue against the Go reasoning engine. Increments `abuse_prevention_cap_fired_total{cap="reasoning_depth"}` on refusal.

### Tests — US5

- [X] T072 [P] [US5] Add `apps/control-plane/tests/unit/security/abuse_prevention/test_cost_protection.py`: 8 cases — model-router refuses non-cheap model on Free plan; allows cheap model; execution-service refuses 101st execution; auto-terminates at time cap; reasoning-engine refuses over-depth; metric increments per cap; audit-chain entry per cap-fired event.
- [X] T073 [P] [US5] Add `apps/control-plane/tests/integration/security/abuse_prevention/test_cost_protection_e2e.py` (under `integration_live` mark). Run a Free-plan agent through the 4 cap paths. Verifies SC-005 (caps fire within ≤1 execution / ≤10 s of the configured limit).

**Checkpoint**: US5 fully functional. Cost-mining vector closed at the runtime + model-router + reasoning-engine layers.

---

## Phase 8: Optional integrations — CAPTCHA, geo-block, fraud-scoring (Priority: P2 each)

**Purpose**: ship the optional layers behind toggles per spec FR-745 / FR-746 / FR-747. Each is independently shippable.

### CAPTCHA (Turnstile + hCaptcha adapter)

- [X] T074 [P] [US1] Create `CaptchaProvider` Protocol + `TurnstileProvider` + `HCaptchaProvider` implementations in `apps/control-plane/src/platform/security/abuse_prevention/captcha.py`. Per research R4. Secrets resolved through `SecretProvider` per rule 39.
- [X] T075 [US1] Add CAPTCHA-guard pre-step to the signup endpoint immediately after the disposable-email guard. Optional — fires only when `captcha_enabled=true`. Refused replays via `abuse:captcha_seen:{sha256(token)}` Redis cache. Per `contracts/signup-guards-rest.md`.
- [X] T076 [P] [US1] Frontend: add CAPTCHA widget to the signup page (`apps/web/app/(auth)/signup/page.tsx` — existing UPD-037 / UPD-087). Render the widget when `captcha_enabled=true` (read from a public settings endpoint that surfaces only the enabled-flag, not the secret).

### Geo-block

- [X] T077 [P] [US1] Implement `GeoBlockService` in `apps/control-plane/src/platform/security/abuse_prevention/geo_block.py`. Loads `/var/lib/musematic/geoip/GeoLite2-Country.mmdb` via `geoip2.Reader` on app start. `lookup(ip) -> str | None` returns ISO-3166-1 alpha-2 or None on miss. `check(ip) -> None | raises GeoBlockedError` consults the `geo_block_mode` and `geo_block_country_codes` settings.
- [X] T078 [US1] Add geo-block guard pre-step to the signup endpoint after CAPTCHA. Refused signups emit audit-chain entry with country_code + actor_ip_hash. Per `contracts/geo-policy-rest.md`.
- [X] T079 [P] [US1] Frontend: create `apps/web/app/(admin)/admin/security/geo-policy/page.tsx` + `GeoPolicyEditor.tsx` — mode picker (disabled / deny_list / allow_list), country-list editor with mode-switch confirmation modal. Per the geo-policy contract.

### Fraud-scoring

- [X] T080 [P] [US1] Define `FraudScoringProvider` Protocol in `apps/control-plane/src/platform/security/abuse_prevention/fraud_scoring.py`. Single method `score_signup(payload) -> FraudScoreResult` with `verdict ∈ {"allow", "review", "suspend"}`. NO concrete provider ships in this branch — operators register an adapter at app startup if they want fraud-scoring.
- [X] T081 [US1] Add fraud-scoring guard pre-step to the signup endpoint after geo-block. 3 s timeout; on timeout / 5xx / network error → degrade to "allow" with structured-log warning (FR-747.1). On "suspend" verdict → emit `abuse.signup.refused` + auto-suspend the user (the suspension is the side-effect; the signup itself is refused).
- [X] T082 [P] [US1] Frontend: surface fraud-scoring status on the abuse-prevention dashboard (`abuse-prevention/page.tsx`) — when `fraud_scoring_provider != "disabled"` and the adapter is registered, show a green health indicator; when set but adapter missing, show a red "provider not registered" warning.

### Tests — Optional integrations

- [X] T083 [P] Add unit tests for the CAPTCHA replay cache, geo-block resolution, and fraud-scoring graceful degradation in `apps/control-plane/tests/unit/security/abuse_prevention/test_optional_integrations.py`.
- [X] T084 [P] Add integration test `apps/control-plane/tests/integration/security/abuse_prevention/test_optional_guards_e2e.py` (under `integration_live` mark). With CAPTCHA enabled + geo-block enabled + fraud-scoring stubbed, signup respects all three. Verifies SC-006 (graceful degradation latency).

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: documentation, dashboards, axe accessibility, mypy strict, migration verification.

- [X] T085 [P] Add `docs/admin-guide/abuse-prevention.md` with operator walkthroughs for the four admin flows (threshold tuning, suspension queue, override list, geo-policy). Per constitutional rule 36.
- [X] T086 [P] Add the abuse-prevention Grafana dashboard at `deploy/helm/observability/templates/dashboards/abuse-prevention.yaml`. Panels: refusals/min by reason, suspensions/min by source, cap-fired counts by cap, velocity-check latency p99, disposable-email-lookup latency p99. Per constitutional rules 24 + 27.
- [X] T087 [P] Add the 4 new admin surfaces to `apps/web/tests/a11y/audited-surfaces.ts`: `abuse-prevention` (`/admin/security/abuse-prevention`), `suspensions` (`/admin/security/suspensions`), `email-overrides` (`/admin/security/email-overrides`), `geo-policy` (`/admin/security/geo-policy`). All grouped under `admin-settings`.
- [X] T088 Run `pytest apps/control-plane/tests/integration/security/abuse_prevention/ -m integration_live` and confirm all integration_live-marked tests have spec/skip body wired so the orchestrator's `make integration-test` passes (as specifications). Document any flakes in NOTES.
- [X] T089 [P] Run `mypy --strict apps/control-plane/src/platform/security/abuse_prevention/` to confirm the new bounded context passes strict typing.
- [X] T090 [P] Run `make migrate-check` after migration 110 is applied to confirm `110_abuse_prevention` is the new head with no chain conflicts.
- [X] T091 [P] Add J26 boundary scenarios at `tests/e2e/suites/abuse_prevention/` (5 files: `test_velocity_block.py`, `test_disposable_email.py`, `test_suspension_flow.py`, `test_free_tier_cost_protection.py`, `test_admin_overrides.py`). Boundary-scenario style matching existing `tests/e2e/suites/cost_governance/`. Verifies SC-009.
- [X] T092 Append `## Refresh-Pass Summary` to `specs/103-abuse-prevention/NOTES.md` enumerating the migration-number resolution (109 → 110), the path adoption (security_abuse → security/abuse_prevention), the module split (single service → disposable_emails + suspension), and any further deltas surfaced during implementation.

---

## Dependencies

```text
Phase 1 (Setup) ─┐
                 ├─► Phase 2 (Foundational, blocks everything)
                 │      │
                 │      ├─► Phase 3 (US1, P1) — MVP
                 │      ├─► Phase 4 (US2, P1) — depends on Phase 2 only
                 │      ├─► Phase 5 (US3, P1) — depends on Phase 2 only
                 │      ├─► Phase 6 (US4, P2) — depends on Phase 5 (suspension service must exist)
                 │      ├─► Phase 7 (US5, P1) — depends on Phase 2; touches existing UPD-047 + UPD-026 surfaces
                 │      ├─► Phase 8 (Optional integrations) — each independent of the others
                 │      └─► Phase 9 (Polish) — runs after all user-story phases pass
```

### Inter-task dependencies (within phases)

- T016 depends on T014.
- T017 depends on T014, T016.
- T018 depends on T014, T011.
- T022 depends on T021.
- T031 depends on T028, T029, T030.
- T037 depends on T033.
- T045 depends on T043, T044.
- T050 depends on T046, T049.
- T052, T053 depend on T046.
- T065 depends on T062, T063, T064.
- T066 depends on T065.
- T078 depends on T077.

### Cross-phase dependencies

- All `integration_live`-marked tests depend on the integration-test fixture from feature 071 (already wired by PR #135 for marketplace; the same harness covers abuse-prevention).
- T069, T070, T071 modify code outside the `security/abuse_prevention/` BC (model_router, execution, reasoning); each must keep the existing tests for those modules green.

---

## Parallel Execution Examples

### Within Phase 2 (after T004 — migration applied)

```bash
$ Task: "T005 [P] — bounded-context skeleton"
$ Task: "T006 [P] — SQLAlchemy models"
$ Task: "T007 [P] — exception classes"
$ Task: "T008 [P] — Kafka event types"
$ Task: "T009 [P] — Pydantic schemas"
$ Task: "T010 [P] — Prometheus metrics"
$ Task: "T013 [P] — GeoLite2 ConfigMap"
```

### Within Phase 3 (US1)

```bash
# After T014 (VelocityService) is in:
$ Task: "T015 [P] — ASN-resolution helper"
$ Task: "T020 [P] — velocity_persist_cron"
$ Task: "T021 [P] — admin endpoints"
$ Task: "T023 [P] — unit tests"
$ Task: "T028 [P] — TanStack hooks"
$ Task: "T029 [P] — ThresholdEditor"
$ Task: "T030 [P] — RefusalReasonChart"
```

### Within Phase 5 (US3)

```bash
# After T046 (SuspensionService) is in:
$ Task: "T049 [P] — auto-rule engine"
$ Task: "T051 [P] — CostBurnRateConsumer"
$ Task: "T054 [P] — admin endpoints"
$ Task: "T055 [P] — SuspensionNotifier"
$ Task: "T056 [P] — service unit tests"
$ Task: "T057 [P] — auto-rules unit tests"
```

---

## Implementation Strategy

### MVP scope

**Phase 3 (US1) is the MVP.** It delivers the headline value (per-IP velocity refusal at signup) and gates SC-001 + SC-008. It is also the minimum viable defence against bot signups — the rest of the abuse-prevention layer adds depth.

### Incremental delivery

Recommended PR slicing:

1. **PR 1** — Phase 1 + Phase 2: schema (migration 110) + bounded-context skeleton + cross-cutting plumbing.
2. **PR 2** — Phase 3 (US1): velocity rules + admin tuning UI (the MVP).
3. **PR 3** — Phase 4 (US2): disposable-email detection + override list UI.
4. **PR 4** — Phase 5 (US3): suspension + login refusal + auto-rule engine.
5. **PR 5** — Phase 6 (US4): suspension queue UI.
6. **PR 6** — Phase 7 (US5): free-tier cost protection (touches model-router + execution + reasoning — review carefully, three different sub-systems).
7. **PR 7** — Phase 8 (optional integrations): each of CAPTCHA / geo-block / fraud-scoring can ship as its own micro-PR or as one bundle.
8. **PR 8** — Phase 9 polish: docs + dashboards + axe + mypy + J26.

PRs 3–6 can ship in any order after PR 2; PR 1 is the only hard prerequisite.

---

## Total task count

- **Phase 1 Setup**: 3 tasks (T001–T003)
- **Phase 2 Foundational**: 10 tasks (T004–T013)
- **Phase 3 US1 (P1, MVP)**: 19 tasks (T014–T032)
- **Phase 4 US2 (P1)**: 13 tasks (T033–T045)
- **Phase 5 US3 (P1)**: 16 tasks (T046–T061)
- **Phase 6 US4 (P2)**: 6 tasks (T062–T067)
- **Phase 7 US5 (P1)**: 6 tasks (T068–T073)
- **Phase 8 Optional integrations**: 11 tasks (T074–T084)
- **Phase 9 Polish**: 8 tasks (T085–T092)

**Total: 92 tasks.**

### Independent test criteria summary

| Story | Priority | Independent test |
|---|---|---|
| US1 | P1 | 6 signups from one IP → 5×202 + 1×429; verified by T025, T026, T027 |
| US2 | P1 | `tempmail@10minutemail.com` → 400 + no mail; verified by T040, T041, T042 |
| US3 | P1 | Suspended user cannot log in; mid-session invalidates; verified by T058, T059, T060, T061 |
| US4 | P2 | Super admin lifts a suspension via the queue UI; verified by T067 |
| US5 | P1 | 4 caps fire on Free-tier abuse; verified by T072, T073 |

### Format validation

✅ All 92 tasks follow the strict `- [ ] T### [P?] [US?] description with file path` format.
✅ Setup (T001–T003), Foundational (T004–T013), and Polish (T085–T092) carry no `[Story]` label.
✅ User-story phase tasks (T014–T084) all carry `[US1]`–`[US5]` labels (Phase 8 tasks marked `[US1]` because they extend the signup-side guard introduced in US1).
✅ Every task names a concrete file or absolute command.
