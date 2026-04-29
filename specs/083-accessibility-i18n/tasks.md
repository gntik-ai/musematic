# Tasks: Accessibility (WCAG 2.1 AA) and Internationalization

**Feature**: 083-accessibility-i18n
**Branch**: `083-accessibility-i18n`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — i18n foundation: every user-facing string through `t()` (rule 13 canonical implementation)
- **US2 (P2)** — WCAG 2.1 AA via axe-core in CI (rule 28 canonical implementation)
- **US3 (P3)** — Four-theme support: Light, Dark, System, High-Contrast (`next-themes` already wired; this adds High-Contrast)
- **US4 (P4)** — Command palette per-route + keyboard shortcuts + help overlay (`cmdk` already wired; this adds per-route registration + `?` overlay)
- **US5 (P5)** — Responsive design + PWA manifest (no service worker; offline OUT of scope at v1)

Each user story is independently testable per spec.md.

---

## Phase 1: Setup

- [X] T001 Create new bounded-context directory `apps/control-plane/src/platform/localization/` with subdirs `services/` and `tooling/`; add empty `__init__.py` to each; follow the standard BC layout from constitution § Bounded Context Structure
- [X] T002 [P] Add canonical constants to `apps/control-plane/src/platform/localization/constants.py`: `THEMES = ("light","dark","system","high_contrast")`; `LOCALES = ("en","es","fr","de","ja","zh-CN")`; `DEFAULT_LOCALE = "en"`; `DEFAULT_THEME = "system"`; `LOCALE_LRU_SIZE = 12` (6 locales × 2 versions for the rollover window — bounded process memory per the plan); `DRIFT_THRESHOLD_DAYS = 7` (matches constitution rule 38); `DATA_EXPORT_FORMATS = ("json","csv","ndjson")`; `KAFKA_TOPIC = "localization.events"` (consistent with the BC-events naming convention)
- [X] T003 [P] Add `LocalizationSettings` extension to `apps/control-plane/src/platform/common/config.py`: `localization_locale_lru_size` (int, default 12), `localization_drift_threshold_days` (int, default 7), `localization_default_locale` (str, default "en"), `localization_supported_locales` (list[str], default `["en","es","fr","de","ja","zh-CN"]`), `localization_translation_vendor` (str, default "lokalise" — vendor choice deferred to research.md but the env-var slot exists), `localization_default_data_export_format` (str, default "json"); the constitutional `FEATURE_I18N` is "always on" (constitution line 890) — no Pydantic field needed since there is no toggle
- [X] T004 [P] Initialise frontend i18n config at `apps/web/i18n.config.ts`: exports the `LOCALES` array, `DEFAULT_LOCALE`, the namespace structure (`marketplace`, `auth`, `errors`, `commands`, `preferences`, `incidents`, `regions`, `costs`, `tagging`, `policies`, `workflows`, `fleets`, `agents`, `evaluation`, `trust`, `dashboard`, `home`, `admin`, `common`, `forms`, `time`, `numbers`); these match the route-group names so namespace boundaries align with code boundaries

---

## Phase 2: Foundational (blocks every user story)

- [X] T005 Create Alembic migration `apps/control-plane/migrations/versions/066_localization.py` (rebase to current head at merge time): creates **`user_preferences`** (`id` UUID PK, `user_id` UUID UNIQUE FK to `users.id` ON DELETE CASCADE, `default_workspace_id` UUID FK to `workspaces.id` ON DELETE SET NULL nullable, `theme` VARCHAR(16) CHECK against `THEMES` default `'system'`, `language` VARCHAR(16) CHECK against `LOCALES` default `'en'`, `timezone` VARCHAR(64) default `'UTC'` (validated against IANA tz at the application layer via `zoneinfo.available_timezones()`), `notification_preferences` JSONB default `'{}'` (channels + quiet-hours per FR-493.4), `data_export_format` VARCHAR(32) CHECK against `DATA_EXPORT_FORMATS` default `'json'`, `created_at` TIMESTAMPTZ, `updated_at` TIMESTAMPTZ; UNIQUE on `user_id`); creates **`locale_files`** (`id` UUID PK, `locale_code` VARCHAR(16) NOT NULL CHECK against `LOCALES`, `version` INT NOT NULL default 1, `translations` JSONB NOT NULL (the per-namespace translation map), `published_at` TIMESTAMPTZ nullable, `published_by` UUID FK to `users.id`, `vendor_source_ref` VARCHAR(256) nullable (the translation vendor's identifier for traceability per the audit trail), `created_at` TIMESTAMPTZ; UNIQUE on `(locale_code, version)`; partial UNIQUE index on `(locale_code) WHERE published_at IS NOT NULL` would be too restrictive (multiple versions can be "published" historically — only the *latest published* version is the active one; resolved by query at read time, not by index). Index `(locale_code, version DESC)` for the "latest version per locale" query; **data migration in the same revision** seeds the English `locale_files` row at version 1 with an empty `{}` translations map so the LRU has a row to load on first request — non-English locales are seeded by the vendor-sync CI step on first deploy
- [X] T006 [P] Add SQLAlchemy models to `apps/control-plane/src/platform/localization/models.py`: `UserPreferences`, `LocaleFile` (FK columns to `users.id` and `workspaces.id` as typed FKs since these ARE specific tables; this is NOT polymorphic like feature 082's tagging substrate)
- [X] T007 [P] Add Pydantic schemas to `apps/control-plane/src/platform/localization/schemas.py`: `UserPreferencesResponse`, `UserPreferencesUpdateRequest` (PATCH-shape — every field optional; `theme: Literal["light","dark","system","high_contrast"] | None`, `language: str | None`, `timezone: str | None`, `default_workspace_id: UUID | None`, `notification_preferences: dict | None`, `data_export_format: Literal["json","csv","ndjson"] | None`), `LocaleFileResponse`, `LocaleFileListItem` (lightweight for listing — no `translations` payload), `LocaleFilePublishRequest` (admin only — body carries the translations JSONB and the optional `vendor_source_ref`), `LocaleResolveRequest` (the locale-negotiation helper input — `url_hint`, `accept_language`, `user_preference`), `LocaleResolveResponse` (the resolved locale + the source that won the negotiation), `DriftCheckResponse` (per-namespace `{namespace, last_published_en, last_published_es, …, days_drift, over_threshold}` rows for the CI script's output)
- [X] T008 [P] Add domain exceptions to `apps/control-plane/src/platform/localization/exceptions.py`: `UnsupportedLocaleError` → 422 (locale_code not in `LOCALES`); `InvalidThemeError` → 422; `InvalidTimezoneError` → 422 (validated against IANA tz database via `zoneinfo.available_timezones()` at upsert time); `LocaleFileNotFoundError` → 404; `LocaleFileVersionConflictError` → 409 (concurrent publish for the same locale); `WorkspaceNotMemberError` → 422 (user attempts to set a `default_workspace_id` they're not a member of); `DataExportFormatInvalidError` → 422
- [X] T009 [P] Add events to `apps/control-plane/src/platform/localization/events.py`: payload classes `UserPreferencesUpdatedPayload` (carries `user_id`, `changed_fields: dict[str, Any]` — old + new for the audit trail; never includes the user's full preferences blob, just the delta), `LocaleFilePublishedPayload` (carries `locale_code`, `version`, `published_by`, `vendor_source_ref`, `namespace_count`, `key_count`); `LocalizationEventType` StrEnum; `register_localization_event_types()` mirroring feature 082's pattern; topic `localization.events`
- [X] T010 Create `apps/control-plane/src/platform/localization/repository.py`: `get_user_preferences(user_id)` (returns row or None); `upsert_user_preferences(user_id, **fields)` (PATCH semantics — only provided fields update; UPSERT on `user_id` UNIQUE constraint; returns the merged row); `get_latest_locale_file(locale_code)` (single SELECT ordered by version DESC LIMIT 1); `list_locale_files(locale_code=None)` (admin listing; lightweight without translations payload); `insert_locale_file_version(locale_code, version, translations, published_by, vendor_source_ref)` (INSERT with `version = (SELECT MAX(version)+1 ... FOR UPDATE)` inside a serializable transaction to avoid race conditions per LocaleFileVersionConflictError); `get_namespace_publish_timestamps_per_locale()` — for the drift-check, returns a per-(locale_code, namespace) map of the latest publish timestamp; this is the SQL the drift script consumes
- [X] T011 Create `LocalizationService` facade at `apps/control-plane/src/platform/localization/service.py`: composes the three sub-services (preferences, locale-file, locale-resolver); exposes `get_user_language(user_id) -> str` as the hot-path API the notifications BC calls (FR-CC-4); exposes `handle_workspace_archived(workspace_id)` for FR-CC-3 (preferences with that `default_workspace_id` are NULLed via the FK ON DELETE SET NULL — but the service-side handler also emits an audit-chain entry per affected user)
- [X] T012 [P] Wire dependency-injection providers in `apps/control-plane/src/platform/localization/dependencies.py`: `get_preferences_service`, `get_locale_file_service`, `get_locale_resolver`, `get_localization_service`; reuse `get_audit_chain_service` (UPD-024); reuse `get_workspaces_service` (for the default-workspace membership check)
- [X] T013 Mount `localization/router.py` skeleton at the constitutional REST prefixes (constitution § REST Prefix lines 811–812): `/api/v1/me/preferences` (GET, PATCH — workspace-member-RBAC; rule 46 — accepts no `user_id` parameter, always operates on the authenticated principal); `/api/v1/locales/{locale_code}` (GET); `/api/v1/locales` (GET — list available); admin authoring at `/api/v1/admin/locales` (POST publish; `require_superadmin` per rule 30); wire onto the FastAPI app at the existing router-mount block in `apps/control-plane/src/platform/main.py:1540–1579`; register the event types via `register_localization_event_types()` at app startup; no middleware added; no APScheduler jobs
- [X] T014 [P] **Frontend foundational i18n machinery**: install `next-intl@3.x`, `@axe-core/playwright@4.x`, `@formatjs/intl-localematcher@0.5.x` in `apps/web/package.json`; install custom ESLint plugin scaffold (the rule itself lands in T058); create `apps/web/messages/` directory with six empty catalogues (`en.json` with `{}`, `es.json` with `{}`, `fr.json` with `{}`, `de.json` with `{}`, `ja.json` with `{}`, `zh-CN.json` with `{}`); create `apps/web/lib/i18n/getRequestLocale.ts` (server-side locale resolution helper that delegates to backend `LocaleResolver` for canonical negotiation per FR-489.2); modify `apps/web/middleware.ts` to honour `?lang=` URL hint and write the negotiated locale into a request-scoped cookie that the server-render uses for first-paint locale (avoids FOIT); modify `apps/web/app/layout.tsx` to wrap `children` with `<NextIntlClientProvider>` *inside* the existing `<NextThemesProvider>` at `:17` (the existing theme provider is preserved untouched). Existing UI continues to render English-only because the ESLint rule (T058) is not yet enforced

---

## Phase 3: User Story 1 — Internationalisation Foundation (P1) 🎯 MVP

**Story goal**: Every user-facing string in the web UI flows through `t()` resolved against per-locale catalogues; six locales ship at launch; locale negotiation honours URL > preference > browser > default; locale-specific formatting renders correctly; missing keys fall back to English silently (never the raw key literal); CI enforces translation drift > 7 days fails the build.

**Independent test**: Switch the active locale via the user-preference setting, the URL hint, and the browser; confirm UI strings change accordingly across at least three distinct surfaces (login, marketplace listing, agent detail). Detect a deliberate translation gap by removing one Spanish string and confirming the CI parity check fails. Verify date/number/currency rendering across the six locales.

### Tests

- [X] T015 [P] [US1] Unit tests `apps/control-plane/tests/unit/localization/test_locale_resolver.py`: precedence URL > preference > browser > default verified across all combinations; partial-fallback for missing keys returns the English source (NEVER the raw `t('key.path')` literal per FR-489.7); empty browser `Accept-Language` falls back through; an unsupported locale in the URL hint is rejected (logged + falls back to next priority) — never silently accepted
- [X] T016 [P] [US1] Unit tests `apps/control-plane/tests/unit/localization/test_drift_check.py`: per-namespace timestamp comparison; English leading any non-English by > 7 days for any namespace returns `over_threshold=true` for that (locale, namespace) pair; the 7-day boundary is exclusive (exactly 7.0 days does not fail); a brand-new namespace with no non-English translations yet (e.g., a freshly-added namespace within the grace window) is flagged "in_grace" not "over_threshold"
- [X] T017 [P] [US1] Unit tests `apps/control-plane/tests/unit/localization/test_locale_file_service.py`: publish writes a new version row; the version increments monotonically per locale; a concurrent publish for the same locale raises `LocaleFileVersionConflictError` 409 (the serializable transaction is the guard); `get_latest_locale_file(locale)` returns the highest-versioned published row; the per-process LRU caches by `(locale_code, version)` so a version bump invalidates naturally; LRU size capped at `LOCALE_LRU_SIZE`
- [X] T018 [P] [US1] Frontend unit tests `apps/web/tests/unit/i18n/`: `getRequestLocale` precedence; `next-intl`'s `useTranslations` hook resolves keys correctly; missing-key fallback to English; locale-specific formatting (dates, numbers, currencies) via `Intl.DateTimeFormat`, `Intl.NumberFormat`

### Implementation

- [X] T019 [US1] Implement `apps/control-plane/src/platform/localization/services/locale_resolver.py` `LocaleResolver` class: `async def resolve(*, url_hint: str | None, user_preference: str | None, accept_language: str | None) -> tuple[str, Literal["url","preference","browser","default"]]` returning the negotiated locale + the source that won. Uses Python's `langcodes` (or `babel.localedata`) for the `Accept-Language` parsing and best-match selection against `LOCALES`. Returns the source so audit / debug surfaces can show "your URL hint won this negotiation"
- [X] T020 [US1] Implement `apps/control-plane/src/platform/localization/services/preferences_service.py` `PreferencesService` class:
  - `async def get_for_user(user_id) -> UserPreferencesResponse` — returns persisted row or a virtual default row (so callers always get a usable response; `is_persisted: bool` flag distinguishes)
  - `async def upsert(user_id, requester, **fields) -> UserPreferencesResponse` — RBAC: `user_id == requester.id` (rule 46); validates `language` in `LOCALES`, `theme` in `THEMES`, `timezone` against `zoneinfo.available_timezones()`, `data_export_format` in `DATA_EXPORT_FORMATS`; if `default_workspace_id` provided, calls `WorkspaceService.is_member(user_id, workspace_id)` to verify membership (raises `WorkspaceNotMemberError` 422 if not); UPSERT on `user_id` UNIQUE; emits an audit-chain entry with the `changed_fields` delta (NOT the full preferences blob — just the delta is the audit-relevant signal)
  - `async def get_user_language(user_id) -> str` — the hot path the notifications BC calls; falls back to `DEFAULT_LOCALE` on resolution failure (per the plan's fail-open-for-language rationale)
- [X] T021 [US1] Implement `apps/control-plane/src/platform/localization/services/locale_file_service.py` `LocaleFileService` class with the per-process LRU: `async def get_latest(locale_code) -> LocaleFileResponse` (LRU-cached by `(locale_code, version)`); `async def publish(locale_code, translations, requester, vendor_source_ref)` — superadmin only; serializable transaction; bumps version; emits audit-chain entry with `LocaleFilePublishedPayload`; invalidates the LRU entries for that locale (oldest version first); `async def list_available()` for the locale-switcher UI
- [X] T022 [US1] Implement REST endpoints in `localization/router.py`:
  - `GET /api/v1/me/preferences` — returns `UserPreferencesResponse` for the authenticated user
  - `PATCH /api/v1/me/preferences` — body `UserPreferencesUpdateRequest`; rule 46 — no `user_id` accepted; always operates on the authenticated principal
  - `GET /api/v1/locales/{locale_code}` — returns the latest published version of that locale's catalogue (the *full* `translations` JSONB; this is the surface the frontend pulls on locale-switch); served from the LRU
  - `GET /api/v1/locales` — list available locales with metadata (version, published_at) — used by the locale-switcher UI
  - `POST /api/v1/admin/locales` — `require_superadmin`; body `LocaleFilePublishRequest`; emits audit-chain entry
  - All mutating endpoints emit audit-chain entries
- [X] T023 [US1] Implement the **drift-check Python script** at `apps/control-plane/src/platform/localization/tooling/drift_check.py`: CLI entrypoint via `python -m platform.localization.tooling.drift_check --pr-base $BASE_SHA`; queries `repository.get_namespace_publish_timestamps_per_locale()`; for each namespace touched in the diff between `$BASE_SHA` and HEAD (parsed via `git diff --name-only` against `apps/web/messages/`), checks per-locale drift; exits 0 if no over-threshold, exits 1 with a structured-log error listing the over-threshold (locale, namespace, days) tuples; the CI step in `.github/workflows/ci.yml` invokes this and fails the build per FR-489.8 + constitution rule 38 + SC-004
- [X] T024 [US1] Add the **drift-check job** to `.github/workflows/ci.yml` (a new top-level job — separate from `test-frontend` because it reads from PG and the frontend test job doesn't have DB access): runs after the `migrate` step; invokes `python -m platform.localization.tooling.drift_check --pr-base ${{ github.event.pull_request.base.sha }}`; fails the build on non-zero exit; outputs the structured-log to the job summary so the PR author sees the offending namespaces
- [X] T025 [US1] Add **vendor-sync CI step** at `.github/workflows/ci.yml` (runs only on merges to `main`): pulls the latest translations from the chosen vendor's API (Lokalise / Crowdin / Phrase — choice in research.md; each has a similar pull pattern); writes them to `apps/web/messages/{locale}.json`; if any catalogue changed, opens a follow-up PR via `gh pr create` (or stages a commit on a `chore/translations-sync-YYYYMMDD` branch); auth via the vendor's API token resolved through the platform's existing secret mechanism (rule 39); never logs the token (rule 23, 40)
- [X] T026 [US1] Add **integration test** `apps/control-plane/tests/integration/localization/test_preferences_api.py`: GET returns virtual-default for a user with no persisted row; PATCH writes the persisted row + audit-chain entry; PATCH with invalid locale → 422; PATCH with `default_workspace_id` for a workspace the user isn't a member of → 422 with the documentation pointer; concurrent PATCH from the same user races safely (last-write-wins per the UPSERT semantics)
- [X] T027 [US1] Add **integration test** `apps/control-plane/tests/integration/localization/test_locale_publish_admin.py`: superadmin publishes a new version → success + audit-chain entry; non-superadmin attempt → 403; concurrent publish for the same locale → 409 `LocaleFileVersionConflictError`
- [X] T028 [US1] Add **integration test** `apps/control-plane/tests/integration/localization/test_locale_resolver_e2e.py`: end-to-end precedence URL > preference > browser > default verified through the full stack with a real test user
- [X] T029 [US1] Add **integration test** `apps/control-plane/tests/integration/localization/test_drift_check_ci_failure.py`: seed a deliberate gap (English ahead by > 7 days for `marketplace.*` namespace); run the drift script; assert exit 1 + the error output names the (locale, namespace, days) triple

### Frontend wiring

- [X] T030 [US1] Wire **`<NextIntlClientProvider>` in the layout** at `apps/web/app/layout.tsx`: server-component reads the active locale from the request (via `getRequestLocale`); fetches the latest catalogue for that locale via `GET /api/v1/locales/{locale_code}` (server-side fetch, runs once per request — cached by Next.js's request memoization); passes the messages to the provider; the existing `<NextThemesProvider>` at `:17` is preserved untouched
- [X] T031 [US1] Implement the **locale switcher** at `apps/web/components/layout/locale-switcher/LocaleSwitcher.tsx`: dropdown listing the six locales with their native names (e.g., `Español`, `Français`, `日本語`); on selection, PATCH `/api/v1/me/preferences` with `language=<code>` AND set the URL `?lang=` for the current request to take effect immediately (no page reload required because the messages are re-fetched via TanStack Query on locale change); the switcher integrates into the existing application shell's user menu
- [ ] T032 [US1] **String extraction across the 26 main routes — Wave 11C in the plan's split**. This is the bulk of the user-visible work. Approach: each route group becomes a sub-task that lands as its own PR; the ESLint rule (T058) starts with all 26 routes allowlisted; per-PR the sub-route is removed from the allowlist as its strings are extracted to the namespace catalogue:
  - **T032a** [P] [US1] Extract `app/(auth)/login/`, `(auth)/signup/`, `(auth)/reset-password/` → `messages/{locale}.json:auth.*`
  - **T032b** [P] [US1] Extract `app/(main)/home/`, `app/(main)/dashboard/` → `messages/{locale}.json:home.*`, `dashboard.*`
  - **T032c** [P] [US1] Extract `app/(main)/marketplace/`, `app/(main)/discovery/` → `marketplace.*`
  - **T032d** [P] [US1] Extract `app/(main)/agents/`, `app/(main)/agent-management/` → `agents.*`
  - **T032e** [P] [US1] Extract `app/(main)/fleet/`, `app/(main)/workflows/`, `app/(main)/workflow-editor-monitor/` → `fleets.*`, `workflows.*`
  - **T032f** [P] [US1] Extract `app/(main)/policies/`, `app/(main)/trust/`, `app/(main)/trust-workbench/` → `policies.*`, `trust.*`
  - **T032g** [P] [US1] Extract `app/(main)/evaluation-testing/`, `app/(main)/analytics/`, `app/(main)/costs/` → `evaluation.*`, `dashboard.*`, `costs.*`
  - **T032h** [P] [US1] Extract `app/(main)/operator/` (incidents, regions, maintenance, capacity, executions) → `incidents.*`, `regions.*` (see also feature 080 / 081 surfaces)
  - **T032i** [P] [US1] Extract `app/(main)/admin/`, `app/(main)/settings/`, `app/(main)/profile/` → `admin.*`, `preferences.*`
  - **T032j** [P] [US1] Extract `app/(main)/conversations/`, `app/(main)/dev/` → `common.*`, `forms.*`
  - **T032k** [P] [US1] Extract shared components under `apps/web/components/` (excluding the new tagging / locale-switcher / theme-toggle / command-palette which are authored localised from the start) → `common.*`, `forms.*`, `errors.*`
  - Each sub-task: removes its routes/components from the ESLint allowlist as part of its PR; once all 11 sub-tasks land, the allowlist is empty and rule 13 is fully enforced
- [ ] T033 [P] [US1] Add **i18n E2E test** `apps/web/tests/e2e/i18n.spec.ts`: switch locale to each of the six locales; navigate to login, marketplace, agent detail; assert no English fragments leak in non-English locales; verify date / number / currency rendering per locale (US1-AS5); verify a missing-key fallback to English never exposes the raw `t('key.path')` literal (US1-AS6)
- [X] T034 [US1] Add **integration test** `apps/control-plane/tests/integration/localization/test_notifications_language_hook.py` (FR-CC-4): a notification dispatched to a user with `language=es` renders its platform-string portion in Spanish; user-generated content portions remain as-authored; failure to resolve the language falls back to English and the dispatch still succeeds

**Checkpoint**: US1 deliverable. The i18n substrate is in place; six locales ship at launch; CI enforces drift > 7 days; missing keys fall back gracefully; constitution rule 13 has its CI enforcement once T058 lands. Wave 11A + 11B + 11C (and the part of 11D that delivers initial locales) are this phase.

---

## Phase 4: User Story 2 — WCAG 2.1 AA Compliance Verified by axe-core in CI (P2)

**Story goal**: axe-core runs in headless browser automation across the audited surfaces × four themes × six locales; zero AA violations on the post-feature build; keyboard navigation works; screen-reader announcements are sensible; colour contrast meets AA; text resizes to 200% without overflow; focus indicators visible; constitution rule 28 has its CI enforcement.

**Independent test**: Run `pnpm test:a11y` locally; confirm zero violations across the audited surface set. Manually verify keyboard navigation through the marketplace's filter sidebar and the operator dashboard. Manually verify with VoiceOver that a status badge announces both colour and text.

### Tests

- [ ] T035 [P] [US2] Create the **canonical audited surfaces list** at `apps/web/tests/a11y/audited-surfaces.ts`: the 26+ surfaces axe-core covers (login, signup, dashboard, home, marketplace, agent-detail, agent-management, workflow editor, workflow monitor, fleet view, fleet topology, operator dashboard, incidents, regions, maintenance, capacity, admin settings, policies, trust certifications, evaluation runs, conversations, costs, the new preferences page, the new admin locales page); for each, a route + a "ready to assert" predicate (e.g., wait for a specific element to be visible) so axe-core runs against a stable DOM
- [ ] T036 [P] [US2] Create `apps/web/tests/a11y/playwright.a11y.config.ts`: Playwright config for the a11y suite; parameterises across 4 themes × 6 locales = 24 runs per surface; sharded across CI workers for the ≤ 5-minute SLA per the plan's perf goal; uses `@axe-core/playwright`'s `AxeBuilder` with the WCAG 2.1 AA rule-set
- [ ] T037 [P] [US2] Author per-surface Playwright a11y tests at `apps/web/tests/a11y/*.spec.ts` — one file per surface group:
  - `auth.spec.ts` — login, signup, reset-password
  - `marketplace.spec.ts`
  - `agent-detail.spec.ts`
  - `workflow-editor.spec.ts`
  - `fleet-view.spec.ts`
  - `operator-dashboard.spec.ts` (incidents + regions + maintenance + capacity panels)
  - `admin-settings.spec.ts`
  - `policies.spec.ts`
  - `trust.spec.ts`
  - `evaluation.spec.ts`
  - `costs.spec.ts`
  - `preferences.spec.ts` (the new route from T056)
  - `admin-locales.spec.ts` (the new route from T057)

### Implementation

- [ ] T038 [US2] **Wire `pnpm test:a11y` script** into `apps/web/package.json`: invokes `playwright test --config tests/a11y/playwright.a11y.config.ts`; default rule-set is WCAG 2.1 AA; reporter outputs JSON for CI artifact upload
- [ ] T039 [US2] **Extend the existing `test-frontend` CI job** at `.github/workflows/ci.yml:417–451`: after the existing `pnpm test --coverage` step, add `pnpm test:a11y` (allow-fail initially during the cross-cutting refactor — switched to fail-fast once T032a–T032k all land per the plan's incremental-rollout strategy); upload the JSON artifact for review; constitutional rule 28's enforcement is delivered by this step
- [ ] T040 [P] [US2] **Audit and fix existing AA violations** discovered by the first axe-core run. This is iterative — likely produces dozens of small fixes across the existing surfaces (missing ARIA labels, insufficient contrast on status badges, missing focus indicators on custom buttons, form fields without `aria-describedby` linkage to validation messages, colour-only severity indicators, etc.). Each fix lands as a small PR; the violation count must reach zero before T039's CI step is switched to fail-fast. **Concrete sub-tasks** (these are the categories the field-guide audit will surface; the count per category is unknown until the first run):
  - **T040a** [US2] Fix ARIA-label gaps on every interactive element across the audited surfaces (FR-488.2)
  - **T040b** [US2] Fix colour-contrast violations across status badges, alert pills, severity indicators (FR-488.3)
  - **T040c** [US2] Fix missing focus indicators on custom buttons / icon buttons (FR-488.5)
  - **T040d** [US2] Fix colour-only severity indicators by adding text or icon cues (FR-488.6)
  - **T040e** [US2] Fix form-validation `aria-describedby` linkage so screen readers announce validation messages (FR-488.7)
  - **T040f** [US2] Fix Tab-order issues on composite widgets (e.g., the marketplace filter sidebar; the workflow editor's node panel)
  - **T040g** [US2] Fix text-resize-to-200% overflow on layouts that use fixed widths instead of fluid ones (FR-488.4)
- [ ] T041 [P] [US2] Create the **constitutionally-named "J15 Accessibility User journey"** at `tests/e2e/journeys/test_j15_accessibility_journey.py` per constitution rule 28: signup → set preferred locale (e.g., Spanish) → change theme to High-Contrast → navigate via keyboard only through marketplace → invoke an agent → verify the screen-reader announces a state-change → observe an alert delivered in Spanish; the journey is the canonical proof that all five user stories integrate end-to-end
- [ ] T042 [P] [US2] Manual a11y verification (NOT automated — but documented): one round of VoiceOver (macOS) and NVDA (Windows) testing across the audited surfaces; document any findings axe-core didn't catch (axe catches the structural violations; manual catches the announcement-quality issues — e.g., "this status badge announces but the text is awkward")

**Checkpoint**: US2 deliverable. axe-core runs in CI; zero AA violations across audited surfaces × 4 themes × 6 locales; J15 journey passes; constitution rule 28 has its enforcement.

---

## Phase 5: User Story 3 — Theme Support: Light, Dark, System, High-Contrast (P3)

**Story goal**: Four themes — Light (default), Dark, System (follows OS), High-Contrast (exceeds AA) — selectable per user, persisted server-side, no FOIT on initial load, every UI surface honours the active theme uniformly. `next-themes` is already wired (this feature adds the High-Contrast variant); the `class` strategy at `apps/web/app/layout.tsx:17` already drives Tailwind's dark mode.

**Independent test**: Switch from Light to Dark in the preferences page; confirm every major surface renders the dark variant without FOIT; switch to System and toggle the OS to dark; observe the platform follow; switch to High-Contrast and confirm zero AA violations across surfaces (axe-core does this automatically per US2's parameterisation); log out and back in and confirm the chosen theme persists.

### Tests

- [ ] T043 [P] [US3] Frontend unit tests `apps/web/tests/unit/theme/theme-toggle.test.tsx`: theme toggle UI lists all four themes; selecting a theme persists via PATCH `/api/v1/me/preferences` with optimistic update; on PATCH failure the optimistic update rolls back; the displayed active-theme indicator matches the persisted preference on remount
- [ ] T044 [P] [US3] Visual regression test `apps/web/tests/visual/theme-no-foit.spec.ts` (SC-007): with persisted preference `dark`, load the marketplace; capture the first paint; assert the captured frame already shows the dark variant (no light-theme flash). Repeat for `high_contrast`, `system` (with OS in dark mode), and `system` (with OS in light mode). The cookie-based theme priming at T046 is the implementation that makes this pass

### Implementation

- [X] T045 [US3] **Extend Tailwind config** at `apps/web/tailwind.config.ts`: add `high-contrast` to the theme variants list (the `darkMode: ["class", '[data-theme="dark"]']` strategy is extended to also recognise `[data-theme="high-contrast"]`); define the high-contrast colour ramp meeting AA-or-better contrast (the design tokens are committed alongside the existing Light + Dark tokens in `apps/web/app/globals.css` — a separate `.high-contrast` class applies the variant tokens)
- [X] T046 [US3] **Cookie-based theme priming** at `apps/web/middleware.ts`: read the persisted theme cookie (set by the preferences PATCH); on the server-rendered HTML, emit the matching theme class on `<html>` so first-paint matches the chosen theme (no FOIT). Use the existing `next-themes` integration's `attribute="class"` configuration; the cookie is set by the PATCH endpoint AND by the user's first OS-preference detection
- [ ] T047 [US3] **Extend the existing `<ThemeToggle>`** at `apps/web/components/layout/theme-toggle/ThemeToggle.tsx`: add the High-Contrast option alongside Light/Dark/System; on selection, PATCH `/api/v1/me/preferences` with `theme=<value>`; the `next-themes` provider receives the new value via its `setTheme()` API; persisted to cookie + DB
- [ ] T048 [US3] **High-Contrast colour ramp design** at `apps/web/app/globals.css`: define the four-theme tokens — Light, Dark, High-Contrast use Tailwind's CSS-variable approach; System resolves to Light or Dark per the OS preference. Status badges, alert pills, severity indicators, focus indicators, chart palettes (Recharts colours) all have High-Contrast variants. **Design check**: every interactive UI surface from the audited list has a high-contrast variant verified visually before T049 enables axe-core for it
- [ ] T049 [US3] **Parameterise axe-core across the four themes** in `apps/web/tests/a11y/playwright.a11y.config.ts` (already designed in T036 — this task verifies the High-Contrast variant passes AA on every audited surface; SC-006); any High-Contrast violations discovered are fixed under T040's umbrella
- [ ] T050 [US3] Add integration test `apps/control-plane/tests/integration/localization/test_theme_preference_persistence.py`: PATCH `theme=high_contrast`; verify cookie set; verify DB row updated; log out + log in; verify cookie re-applied on first request after login

**Checkpoint**: US3 deliverable. Four themes ship; persistence is server + cookie; no FOIT; High-Contrast exceeds AA; every surface honours the active theme.

---

## Phase 6: User Story 4 — Command Palette and Keyboard Shortcuts (P4)

**Story goal**: Cmd+K opens a global palette with route-context-specific commands; common shortcuts work (toggle theme, search marketplace, etc.); `?` opens a help overlay listing every registered shortcut localised to the active language. `cmdk` is already wired at `apps/web/components/layout/command-palette/CommandPaletteProvider.tsx:18` (this feature adds per-route registration + the help overlay).

**Independent test**: Press Cmd+K from any page; confirm the palette opens with route-relevant commands; type a partial command name and confirm fuzzy-match works; press Enter and confirm the action executes; press `?` and confirm the help overlay appears with all shortcuts grouped by category; navigate end-to-end without the mouse.

### Tests

- [ ] T051 [P] [US4] Frontend unit tests `apps/web/tests/unit/commands/command-registry.test.tsx`: per-route command registration via React context; commands grouped by category in the palette UI; fuzzy-match selects the right candidate; pressing Escape closes without action; no input-focus hijacking when an input element has focus
- [ ] T052 [P] [US4] Frontend unit tests `apps/web/tests/unit/commands/help-overlay.test.tsx`: `?` opens the overlay only when no input has focus; the overlay lists every registered shortcut grouped by category; shortcut labels are localised to the active locale (e.g., "Toggle theme" in English, "Cambiar tema" in Spanish); pressing Escape closes
- [ ] T053 [P] [US4] Frontend unit tests `apps/web/tests/unit/commands/customisation.test.tsx`: customising a binding refuses system-reserved combinations (`Cmd+T`, `Cmd+W`, `Cmd+Q`, `Cmd+R`, `Ctrl+T`, etc.) with a clear error per FR-491.5; valid bindings persist via PATCH `/api/v1/me/preferences`

### Implementation

- [ ] T054 [US4] **Extend the existing `CommandPaletteProvider`** at `apps/web/components/layout/command-palette/CommandPaletteProvider.tsx:18` (preserve the existing Cmd+K binding): add a React context (`<CommandRegistryContext>`) that routes call to register their context-specific commands. Each route's `page.tsx` calls `useRegisterCommands([...])` on mount with the commands relevant to that route (e.g., the marketplace's commands include "Search marketplace…", "Filter by tag…"; the operator dashboard's commands include "Open incidents tab", "Schedule maintenance window")
- [ ] T055 [US4] **Implement `<HelpOverlay>`** at `apps/web/components/layout/command-palette/HelpOverlay.tsx`: keyboard listener on `?` (with input-focus guard per the Constraints rationale); modal overlay listing every registered shortcut grouped by category; every label localised via `t()`; renders the keyboard combo using platform-aware glyphs (`⌘K` on macOS, `Ctrl+K` on others); pressing Escape closes the overlay
- [ ] T056 [US4] **Register platform-wide commands and per-route commands** across the 26 main routes (parallelizable across multiple devs by route group, similar to T032's approach):
  - **Platform-wide** (registered in the application shell): "Toggle theme", "Switch language", "Search marketplace", "Open preferences", "Sign out", "Open command palette help"
  - **Per-route** (each route's `page.tsx` registers): the route's primary actions
  - This task lands incrementally per route as part of each route's broader US1 string-extraction PR
- [ ] T057 [US4] Frontend E2E test `apps/web/tests/e2e/command-palette.spec.ts`: log in → press Cmd+K → palette opens → type "switch language" → fuzzy-match returns the right command → press Enter → language switcher dialog opens → select Spanish → verify the platform UI is Spanish; press `?` → help overlay appears with shortcut labels in Spanish

**Checkpoint**: US4 deliverable. Per-route command registration works; `?` help overlay is localised; customisation refuses reserved combinations.

---

## Phase 7: User Story 5 — Responsive Design and Progressive Web App (P5)

**Story goal**: 375px / 768px / 1280px+ breakpoints all work across read-mostly surfaces; creator/operator-edit surfaces show a graceful "best on desktop" hint on mobile (still allowing read-only); PWA manifest published with installability; service worker is OUT of scope at v1.

**Independent test**: Open the platform at 375px; verify marketplace, execution viewer, approval response, alert review, agent detail are usable; visit the workflow editor on 375px and confirm the "best on desktop" hint appears with a clear path to read-only viewing; install the PWA from a mobile browser; relaunch from home screen and verify chrome-less launch.

### Tests

- [X] T058 [P] [US5] Implement the **custom ESLint rule** at `apps/web/eslint/no-hardcoded-jsx-strings.js`: flags hardcoded user-facing strings in JSX; allowlist starts with all 26 routes + components allowlisted (so the rule lands in this PR without breaking the existing build); each route's PR (T032a–T032k) removes its files from the allowlist as part of its work; once the allowlist is empty, rule 13 is fully enforced. The rule has `severity=error` so the CI lint step (existing in `.github/workflows/ci.yml`) fails on new violations once a file is removed from the allowlist. Note: this lands HERE in T058 because by Wave 11C the ESLint plumbing should be in place even though the allowlist initially covers everything; the rule itself is a US1 enabler but its placement here is pragmatic
- [ ] T059 [P] [US5] Frontend visual regression tests `apps/web/tests/visual/responsive.spec.ts`: capture each read-mostly surface at 375px / 768px / 1280px; assert no horizontal scroll; no overlapping interactive elements; readable text; (SC-010)
- [ ] T060 [P] [US5] Frontend test `apps/web/tests/visual/desktop-only-hint.spec.ts`: navigate to creator/operator-edit surfaces (workflow editor, fleet topology editor, admin settings) on 375px; assert the "best experienced on desktop" hint is visible with a clear path to read-only viewing (SC-011); read-only viewing remains usable
- [ ] T061 [P] [US5] PWA installability test `apps/web/tests/visual/pwa-installability.spec.ts`: load the platform at HTTPS endpoint; assert the manifest is reachable; assert the browser's `BeforeInstallPromptEvent` fires (or equivalent assertion via Playwright's PWA helpers); assert the manifest passes the validator's checks per SC-012

### Implementation

- [ ] T062 [US5] **Audit and fix responsive issues** across the 26 main routes (parallelizable across multiple devs by route group). This is the cross-cutting work for FR-492.1 — each route's responsive layout is tested at 375px / 768px / 1280px and adjusted (typically: replacing fixed widths with `w-full` + `max-w`; replacing horizontal layouts with `flex-col md:flex-row`; collapsing sidebars to bottom sheets on mobile; etc.). Read-mostly surfaces from FR-492.2 are the priority; creator/operator-edit surfaces get the "best on desktop" hint instead per FR-492.3
- [ ] T063 [US5] **Implement the "best experienced on desktop" hint** as a shared component at `apps/web/components/layout/desktop-best-hint/DesktopBestHint.tsx`: shown when `window.innerWidth < 768` AND the route is in the creator/operator-edit set (registered per-route via a `requiresDesktop=true` flag in the route's metadata); offers a clear path to read-only viewing of the same data
- [X] T064 [US5] **Implement the PWA manifest** as Next.js 14 App Router-native `apps/web/app/manifest.ts`: TypeScript-typed; exports the manifest JSON at build time; brand constants (`name: "musematic"`, `short_name: "musematic"`, `theme_color`, `background_color`) reference the same source-of-truth as the rest of the UI (avoiding duplicate brand strings); `display: "standalone"`; `icons: [192x192, 512x512, 512x512-maskable]` — the icon files live at `apps/web/public/icons/`
- [X] T065 [US5] **Add PWA icon variants** at `apps/web/public/icons/`: 192×192, 512×512, 512×512-maskable PNGs derived from the platform's existing logo asset
- [ ] T066 [US5] **PWA + auth integration**: the PWA's launch flow honours the existing JWT-refresh path (per feature 015) and the existing `?redirectTo=` deep-link pattern (per feature 017). On launch from home-screen with a stale session, the user is redirected to `/login?redirectTo=/home` (or wherever the manifest's `start_url` points); after re-auth, they land at the original target. Verified by T061 + a manual install-and-relaunch test on a real device
- [ ] T067 [US5] Frontend E2E test `apps/web/tests/e2e/responsive-mobile.spec.ts`: 375px viewport; navigate marketplace → tap an agent card → see agent-detail; navigate to operator dashboard → see incidents tab → tap an incident → see incident detail with all the FR-492.2 read-mostly surfaces working

**Checkpoint**: US5 deliverable. Responsive across breakpoints; "best on desktop" hint on edit surfaces; PWA installable; service worker remains OUT of scope at v1.

---

## Phase 8: User Preferences Page + Admin Locale-File Page

**Story goal**: Greenfield routes for `/settings/preferences` and `/admin/locales` host the user-facing UI for FR-493 and the admin UI for locale-file publishing. Satisfies rule 45 + rule 46.

- [X] T068 [P] Create `apps/web/lib/api/preferences.ts`: typed wrappers over `/api/v1/me/preferences`; TanStack Query hook factories `useUserPreferences`, `useUpdatePreferences` (with optimistic update + rollback)
- [X] T069 [P] Create `apps/web/lib/api/locales.ts`: typed wrappers over `/api/v1/locales/*` and `/api/v1/admin/locales`; hook factories `useLocaleFile`, `useAvailableLocales`, `usePublishLocaleFile`
- [ ] T070 [P] Create `apps/web/components/features/preferences/`:
  - `PreferencesForm.tsx` — RHF + Zod; sections for theme picker (4 options), language picker (6 locales), timezone picker (autocomplete against IANA tz list — uses `Intl.supportedValuesOf("timeZone")` for the client-side list), default-workspace picker (autocomplete from the user's workspaces), notification preferences (channels + quiet-hours, integrating with feature 077's notification-channel registry), data-export-format picker
  - `ThemePicker.tsx` — visual previews of the four themes
  - `LanguagePicker.tsx` — native names per locale
  - `TimezonePicker.tsx` — autocomplete against IANA tz with current-time preview
  - `NotificationPreferencesSection.tsx` — channels (email, in-app, mobile push if PWA-installed) + per-channel quiet-hours
- [ ] T071 [US-FE] Create `apps/web/app/(main)/settings/preferences/page.tsx`: hosts `<PreferencesForm>`; on submit PATCHes `/api/v1/me/preferences`; success toast; failure toast surfaces the validation error (e.g., "you are not a member of that workspace")
- [ ] T072 [US-FE] Update `apps/web/app/(main)/settings/page.tsx`: the existing 1-line stub becomes a settings index linking to `/settings/preferences`, the existing sub-routes (`/settings/governance`, `/settings/visibility`, `/settings/alerts`), and any future settings sub-pages
- [ ] T073 [P] Create `apps/web/components/features/admin-locales/`:
  - `LocaleFilePublishForm.tsx` — superadmin-only; upload a `translations` JSON via file input or paste-area; preview the namespace+key counts; submit POSTs to `/api/v1/admin/locales`
  - `LocaleVersionHistory.tsx` — table of versions per locale with `published_at`, `published_by`, `vendor_source_ref`
  - `DriftStatusBadge.tsx` — green/yellow/red indicator per locale based on the drift-check output
- [ ] T074 [US-FE] Create `apps/web/app/(main)/admin/locales/page.tsx`: superadmin-gated route; lists the six locales with `<DriftStatusBadge>`; admin can publish a new version per locale via `<LocaleFilePublishForm>`; per-locale version history via `<LocaleVersionHistory>`
- [ ] T075 [P] [US-FE] Vitest + RTL component tests:
  - `PreferencesForm`: Zod validation (invalid locale, invalid timezone, invalid theme); optimistic update; rollback on 422 from non-membership default workspace; debounced auto-save OR explicit "Save" button (decision in research.md — recommend explicit Save for predictability)
  - `LocaleFilePublishForm`: superadmin-only (link from non-superadmin returns 403); preview the upload before submit; concurrent-publish 409 surfaces with a clear "another publish is in progress" message
  - `DriftStatusBadge`: green when all namespaces in-window; yellow when within grace; red when over-threshold
- [ ] T076 [US-FE] Frontend E2E test `apps/web/tests/e2e/preferences.spec.ts`: log in → navigate to `/settings/preferences` → change theme to Dark → change language to Spanish → change timezone → save → log out → log in → verify all preferences persisted

**Checkpoint**: Rule 45 + rule 46 + FR-493 satisfied. The user-preferences page and admin locale-file page are live.

---

## Phase 9: Polish & Cross-Cutting

- [ ] T077 [P] Create Grafana dashboard ConfigMap `deploy/helm/observability/templates/dashboards/localization.yaml` (rules 24, 27): follow the `cost-governance.yaml` / `incident-response.yaml` pattern; panels for translation-key-not-found rate per locale (signals stale catalogues), per-locale request rate (validates locale negotiation), preference-mutation rate, locale-file publish events. Labels limited to `service`, `bounded_context=localization`, `level`, `locale` (bounded set of 6)
- [ ] T078 [P] Add OpenAPI tags `localization-preferences`, `localization-locales`, `localization-admin-locales` and ensure all `/api/v1/me/preferences`, `/api/v1/locales/*`, `/api/v1/admin/locales` routers carry them
- [ ] T079 [P] Wire E2E suite directory `tests/e2e/suites/localization/` (constitution rule 25): `test_locale_switching.py` (US1 — six-locale verification across three surfaces), `test_high_contrast_a11y.py` (US3 — High-Contrast meets AA on every surface), `test_pwa_installability.py` (US5 — PWA manifest validation); the J15 journey at T041 is the canonical journey-crossing per rule 28
- [ ] T080 [P] Run `ruff check apps/control-plane/src/platform/localization` and `mypy --strict apps/control-plane/src/platform/localization`; resolve all findings; assert no `os.getenv` for `*_SECRET` / `*_API_KEY` / `*_TOKEN` outside SecretProvider files (rule 39 — only the translation vendor's API token; verify it's resolved through SecretProvider)
- [ ] T081 [P] Run `pytest apps/control-plane/tests/unit/localization apps/control-plane/tests/integration/localization -q`; verify ≥ 95% line coverage on `apps/control-plane/src/platform/localization/` (constitution § Quality Gates)
- [ ] T082 [P] Run frontend test suites: `pnpm test --coverage` (vitest); `pnpm test:a11y` (axe-core across 4 themes × 6 locales); verify zero AA violations; verify ≥ 95% line coverage on the new components
- [ ] T083 [P] **Translation-vendor onboarding** (Wave 11D — partially blocks on vendor turnaround): pick the vendor (Lokalise / Crowdin / Phrase per research.md); provision the project; export the English source from `apps/web/messages/en.json`; commission translations for the five non-English locales; receive translations and merge via the vendor-sync CI step from T025; first-launch coverage target ≥ 95% per SC-003
- [ ] T084 [P] Smoke-run the `quickstart.md` walkthrough (extract a string in a route → translate via vendor → see it render → toggle to High-Contrast → run axe-core locally) against a local control plane; capture deviations and update `quickstart.md` accordingly
- [ ] T085 [P] **Manual a11y verification** with VoiceOver (macOS) and NVDA (Windows) across the audited surfaces; document any findings axe-core didn't catch (already an item at T042 — re-run pre-merge to validate the High-Contrast variant + the localised announcements pass real assistive-tech checks)
- [ ] T086 Update `CLAUDE.md` Recent Changes via `bash .specify/scripts/bash/update-agent-context.sh` so future agent context reflects this BC + the cross-cutting work; the entry must call out:
  - (a) **The frontend is `apps/web/`**, NOT `apps/ui/` (the brownfield input got this wrong; the correction is recorded so future planners don't chase a non-existent path)
  - (b) **`next-themes` and `cmdk` were already wired** at `apps/web/app/layout.tsx:17` and `components/layout/command-palette/CommandPaletteProvider.tsx:18` respectively; this feature ADDED High-Contrast to next-themes and per-route registration to cmdk — future planners should not re-install or re-wire these
  - (c) **The user-preference storage is owned by `localization/` BC**, NOT `auth/` or `accounts/` (which had no preference fields before this feature) — future BCs querying user language / theme / timezone go through `LocalizationService.get_for_user(user_id)`, never the table directly
  - (d) **The maintenance gate's fail-OPEN-on-Redis-miss decision** from feature 081 is unrelated to this feature's notification-language fail-OPEN-on-resolution-failure decision; both are documented inversions of rule 41 with rationale (auth paths fail closed; cooperative paths preserve delivery / preserve language fallback)
  - (e) **Rule 13's CI enforcement** is delivered here via the custom ESLint rule at `apps/web/eslint/no-hardcoded-jsx-strings.js` with an initial allowlist that shrinks per PR; **rule 28's CI enforcement** is delivered via `pnpm test:a11y` in the existing `test-frontend` job; **rule 38's CI enforcement** is delivered via the `translation-drift` CI job

---

## Dependencies

```
Phase 1 (Setup) ──▶ Phase 2 (Foundational — Backend BC + Frontend i18n machinery) ──▶ Checkpoint: Substrate exists

Phase 2 ──▶ Phase 3 US1 (P1) ──▶ Checkpoint MVP (i18n shipping; rule 13 CI enforcement)
              │
              ▼
              ┌──────────────────────────────┐
              │ Phase 4 US2 (P2)             │ — depends on US1 (axe-core parameterises across locales,
              │   (axe-core in CI)           │   so locale catalogues must exist first)
              │                              │
              │ Phase 5 US3 (P3)             │ — independent of US1/US2 (theme work is orthogonal to i18n;
              │   (Light/Dark/System/HC)     │   next-themes already wired)
              │                              │
              │ Phase 6 US4 (P4)             │ — depends on US1 (command labels + help overlay are localised)
              │   (palette + shortcuts       │
              │    + help overlay)           │
              │                              │
              │ Phase 7 US5 (P5)             │ — independent (PWA manifest + responsive audit are orthogonal)
              │   (responsive + PWA)         │
              └──────────────────────────────┘
                            │
                            ▼
                Phase 8 (Preferences page + Admin locale page) — depends on Phase 2 (REST contracts)
                                                                + US1 (UI strings localised)
                                                                + US3 (theme picker UI)
                            │
                            ▼
                      Phase 9 (Polish)
```

**MVP scope**: Phase 1 + Phase 2 + Phase 3 = ~30 tasks. Delivers the i18n substrate end-to-end across all 26 main routes with cross-cutting string extraction, six-locale delivery, drift CI, and rule-13 enforcement. Constitution rules 13 + 38's enforcement is satisfied here. WCAG 2.1 AA (US2), themes (US3), command palette (US4), responsive (US5), and the preferences page are subsequent phases.

**Parallel opportunities**:
- Phase 1: T002 ∥ T003 ∥ T004 (independent files).
- Phase 2: T006 ∥ T007 ∥ T008 ∥ T009 ∥ T012 (independent files); T005 sequential (single migration); T010 / T011 / T013 / T014 sequential after their inputs.
- Phase 3: T015 ∥ T016 ∥ T017 ∥ T018 (test-only); T019 / T020 / T021 sequential (services); T022 / T023 / T024 / T025 mostly parallel after T021; **T032a–T032k** are 11 parallel sub-tasks across multiple devs by route group — the bulk of the work parallelizes cleanly; T033 / T034 sequential at the end of the phase.
- Phase 4: T035 ∥ T036 ∥ T037 (test-only); T038 / T039 sequential; T040 (the violation-fix umbrella) is its own iterative sub-tasks T040a–T040g parallelizable across multiple devs; T041 / T042 sequential.
- Phase 5: T043 ∥ T044 (test-only); T045 / T046 sequential; T047 / T048 / T049 / T050 mostly parallel.
- Phase 6: T051 ∥ T052 ∥ T053 (test-only); T054 sequential; T055 sequential; T056 (per-route registration across 26 routes — parallelizable across multiple devs); T057 sequential.
- Phase 7: T058 sequential (it lands the ESLint rule); T059 ∥ T060 ∥ T061 (test-only); T062 (responsive audit across 26 routes — parallelizable); T063 / T064 / T065 / T066 sequential after T062; T067 sequential at the end.
- Phase 8: T068 ∥ T069 ∥ T070 ∥ T073 (lib + components, fully parallel); T071 / T072 / T074 sequential after T068+T070; T075 sequential after T070+T073; T076 sequential at the end.
- Phase 9: T077 ∥ T078 ∥ T079 ∥ T080 ∥ T081 ∥ T082 ∥ T083 ∥ T084 ∥ T085 (independent surfaces); T086 last.

---

## Implementation strategy

This feature is **the largest cross-cutting refactor in the platform's recent history**. Recommend the Wave 11A–11F split documented in the plan rather than a single push:

1. **Wave 11A (Backend BC + REST)** — Phases 1, 2 (backend portion). One backend dev, ~2 days. Delivers the substrate; existing UI continues working unchanged.
2. **Wave 11B (Frontend i18n machinery)** — Phase 2 (frontend portion: T014). One frontend dev, ~2 days. Installs `next-intl`, wires the provider, creates empty catalogues, lands the ESLint rule with full allowlist (no extractions yet).
3. **Wave 11C (String extraction)** — Phase 3 (T032a–T032k). Multiple devs in parallel by route group, ~1–2 weeks. The ESLint allowlist shrinks per PR until empty.
4. **Wave 11D (Translation vendor + initial locales + drift CI)** — Phases 3 (T023–T025) + 9 (T083). Partially blocks on vendor turnaround, ~1 week.
5. **Wave 11E (Accessibility — Phase 4)**. One frontend dev, ~1 week. axe-core wiring + High-Contrast theme + AA violation fixes (T040a–T040g umbrella). Highest-risk phase because the violation count is unknown until the first run.
6. **Wave 11F (Theme + Palette + Responsive + PWA + Preferences page — Phases 5, 6, 7, 8)**. Multiple devs in parallel, ~1 week. The four user stories' surfaces land here; the preferences page is the canonical end-to-end test.
7. **Wave 11G (Polish — Phase 9)**. Final ~2 days. Dashboard, OpenAPI tags, journey extensions, lint/types/coverage gates, manual a11y verification, agent-context update.

**Total realistic budget: 6–8 weeks of coordinated work across 3–4 devs.** The 3-day budget the brownfield input proposed covers Wave 11A + part of 11B only — useful, but the user-visible work is still future. If the goal is "ship i18n + a11y to users in one push," budget at least 6 weeks.

**Constitution coverage matrix**:

| Rule / AD | Where applied | Tasks |
|---|---|---|
| 1, 4, 5 (brownfield) | All — extends `common/config`, `notifications/service.py`, CI `ci.yml`, `apps/web/app/layout.tsx`; new BC `localization` | T003, T011, T013, T014, T024, T030, T039 |
| 2 (Alembic only) | Phase 2 | T005 |
| 6 (additive enums) | Phase 1 | T002 (string constants, no enum mutation) |
| 7 (backwards compat) | Phase 2 | T014 (existing UI continues English-only until T032 lands per route); T011 (`get_user_language` falls back to DEFAULT_LOCALE) |
| 8 (feature flags) | N/A — `FEATURE_I18N` is "always on"; no toggle | — |
| 9 (PII / sensitive op audit) | Phase 3 | T020, T021 (preference mutations + locale-file publish audited via `AuditChainService.append`) |
| 13 (every user-facing string through i18n) | Phase 3, 7 | T032a–T032k (the cross-cutting string extraction — 11 parallel sub-tasks); T058 (the custom ESLint rule that enforces it) |
| 18, AD-21 (residency at query time) | N/A — locale files are platform-global; user preferences replicate via the `users` table's existing residency path | — |
| 20, 22 (structured JSON logs, low-cardinality labels) | All Python files | T077 (Loki label policing on the dashboard panels) |
| 21 (correlation IDs context-managed) | All endpoints | Audit-chain entries inherit CorrelationContext from request middleware |
| 23, 31, 40 (no secrets in logs) | Phase 3 | T025 (vendor-sync CI step — vendor API token via SecretProvider; never logged) |
| 24, 27 (BC dashboard via Helm) | Phase 9 | T077 |
| 25, 28 (E2E suite + journey crossing — J15 per rule 28 specifically) | Phase 4 | T041 (the constitutionally-named "J15 Accessibility User journey") |
| 26 (journey against real backend) | Phase 4 | T041 (kind cluster + Helm chart per rule 26) |
| 28 (axe-core in CI fails on AA violations) | Phase 4 | T039 (CI step extending the existing test-frontend job) |
| 29, 30 (admin endpoint segregation, admin role gates) | Phase 2, 3, 8 | T013, T022 (`/api/v1/admin/locales` segregated; `require_superadmin`) |
| 32 (audit chain on config changes) | Phase 3, 8 | T020, T021 (preferences + locale-file publish) |
| 36 (UX-impacting FR documented) | Phase 9 | T084 (quickstart) + T086 (CLAUDE.md) — docs site update tracked in PR description |
| 38 (multi-language parity enforced) | Phase 3 | T023, T024 (the drift-check script + CI step) |
| 39 (every secret resolves via SecretProvider) | Phase 3 | T025 (vendor API token via SecretProvider) |
| 41 (Vault failure does not bypass auth) | ⚠️ Documented inversion — see plan's Constraints rationale | T020 (`get_user_language` falls back to DEFAULT_LOCALE on resolution failure — preserves *delivery*, just not language; this is NOT a rule 41 violation because the gate is cooperative, not auth-related) |
| 45 (backend has UI) | Phase 8 | T071, T074 |
| 46 (`/api/v1/me/*` scoped to current_user) | Phase 2, 3 | T013, T022 (PATCH endpoint accepts no `user_id`) |
| 50 (mock LLM for previews) | N/A — no LLM use | — |
| Principle I (modular monolith) | All | All backend work in Python control plane |
| Principle III (dedicated stores) | Phase 2 | T005 (PG); per-process LRU for locale files (NOT Redis — locale catalogues fit in memory; round-trip overhead avoided) |
| Principle IV (no cross-BC table access) | Phase 3 | T020 (`PreferencesService` calls `WorkspaceService.is_member` for default-workspace membership check via service interface, never the table) |
| Constitutional REST prefixes already declared | Phase 2, 3 | T013, T022 (`/api/v1/me/preferences` + `/api/v1/locales/*` per constitution lines 811–812) |
| Constitutional feature flag already declared | Phase 1 | `FEATURE_I18N` is "always on" per constitution line 890; no toggle needed |

---

## Notes

- The `[Story]` tag maps each task to its user story (US1, US2, US3, US4, US5, or US-FE for frontend tasks that span stories) so independent delivery is preserved.
- Constitution rules 13, 28, and 38 are **explicitly code-review-blocker / CI-enforced rules** that PRESUME this feature exists. T039 (axe-core CI), T024 (drift CI), and T058 (ESLint rule) are the canonical CI-enforcement deliverables that satisfy each rule.
- The **brownfield input nominated `apps/ui/`** as the modification target. **That path does NOT exist**; the actual frontend is `apps/web/`. T086 captures the correction in CLAUDE.md so future planners don't chase the non-existent path.
- **`next-themes@0.4.4` and `cmdk@1.0.0` were already wired** when this feature began. T047 extends the existing theme toggle with High-Contrast; T054 extends the existing command palette provider with per-route registration. Future planners reading this spec must not propose re-installing or re-wiring these — the substrate is already there.
- **The `localization/` BC owns user preferences** (theme, language, timezone, default-workspace, notification preferences, data-export format). Neither `auth/` nor `accounts/` carried these fields before this feature. Future BCs querying these go through `LocalizationService.get_for_user(user_id)` via the public service interface (Principle IV), never the table directly.
- **The notification-language fail-OPEN-on-resolution-failure decision** is a documented inversion of rule 41's fail-closed posture (similar in spirit to feature 081's maintenance-gate fail-OPEN-on-Redis-miss). Auth paths fail closed; cooperative-protection paths preserve delivery / language fallback. T086 records this so future planners don't try to "fix" it as a rule 41 violation.
- **Service worker / offline mode is OUT of scope at v1**. The PWA manifest exists (T064) and the platform is installable (T061), but there is no service worker caching the application shell or data. Future work.
- **Right-to-left languages (Arabic, Hebrew) are OUT of scope at v1** but the substrate is RTL-ready by design (T032's CSS uses logical properties: `padding-inline-start`, `margin-inline-end`, `text-align: start`). Future RTL addition is a content delivery, not a refactor.
- Migration `066_localization.py` MUST rebase to the current alembic head at merge time (latest at branch cut: `065_tags_labels_saved_views` from feature 082).
- **Effort estimate disconnect heavily flagged**: input was 6 SP / 3 days; actual scope (2 PG tables + new BC; 26 routes × ~hundreds of strings × 6 locales = ~18,000 translation entries; axe-core wiring + AA violation fixes; 4 themes incl. greenfield High-Contrast; per-route command registration across 26 routes; responsive audit across 26 routes; PWA manifest; 2 new pages; full unit/integration/a11y/visual/E2E coverage). Realistic 6–8 weeks of coordinated frontend work across 3–4 devs. Wave 11A–11G split documented above lets the work land incrementally without big-bang risk.
