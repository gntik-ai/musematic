# Implementation Plan: Accessibility (WCAG 2.1 AA) and Internationalization

**Branch**: `083-accessibility-i18n` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

Stand up the `localization/` bounded context that the constitution already names as the owner of UPD-030 (Constitution § "New Bounded Contexts" line 494) — backing the already-reserved REST prefixes `/api/v1/me/preferences` and `/api/v1/locales/*` (lines 811–812) and the always-on feature flag `FEATURE_I18N` (line 890) — AND deliver the cross-cutting frontend work that constitution rules 13 ("every user-facing string through `t()`"), 28 ("axe-core in CI fails on AA violations"), and 38 ("translation drift > 7 days fails CI") already presume exists. The field-guide research found this is **less greenfield than the brownfield input implied on the frontend, but more greenfield on the backend**: `next-themes@0.4.4` is already wired in `apps/web/app/layout.tsx:17` (so theme switching exists; this feature *adds* the High-Contrast variant), `cmdk@1.0.0` is already integrated with a working Cmd+K binding at `apps/web/components/layout/command-palette/CommandPaletteProvider.tsx:18` (so the substrate is there; this feature *adds* per-route command registration + the help overlay), and a stub settings page exists at `apps/web/app/(main)/settings/page.tsx` (so the route is reserved; this feature *fills* it). On the backend side, the `localization/` BC does NOT exist, neither `user_preferences` nor `locale_files` tables exist (zero migration matches), and neither `auth/` nor `accounts/` currently stores any user-scoped preferences (no `language`, `theme`, `timezone`, or `preferences` columns) — so this feature is the canonical source of all user-preference storage. **i18n library choice**: `next-intl` over `react-i18next` (Next.js App Router-native, server-component-friendly, smaller bundle); decision recorded in `research.md`. **Per-locale message catalogues** live at `apps/web/messages/{locale}.json` keyed by namespace (`marketplace.*`, `auth.*`, `errors.*`, `commands.*`); the canonical English source is committed under git, non-English files are produced by the chosen translation vendor (planning concern — Lokalise / Crowdin / Phrase) and synced via a CI step. **axe-core integration** extends the existing frontend CI job (`.github/workflows/ci.yml:417–451 test-frontend`) by adding a Playwright-driven a11y test suite that runs after the existing vitest pass. **Translation drift detection** is a small Python script invoked by a new CI step that compares per-namespace `published_at` timestamps in `locale_files` and emits a build failure when English leads any non-English by > 7 days for any namespace touched by the PR. **The `apps/ui/` path nominated by the brownfield input does NOT exist** — the frontend is `apps/web/`; the correction is recorded loudly in the spec's scoping note + here. **Notifications BC integration** (FR-CC-4): `notifications/service.py:64+ AlertService` does NOT today accept a `language` parameter; this feature adds an additive `language` resolution at the dispatch site (resolved from the recipient's `user_preferences.language` via the new `localization/` BC's service interface) so platform-string portions of notifications are rendered in the recipient's language without introducing a parallel notification path.

## Technical Context

**Language/Version**: Python 3.12+ (control plane) + TypeScript 5.x (frontend). No Go changes.
**Primary Dependencies**:
- *Backend* (already present): FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+ (audit-event emission). No APScheduler jobs needed.
- *Frontend* — already present per `apps/web/package.json`: Next.js 14 App Router, React 18+, `next-themes@0.4.4` (theme switching — wired at `app/layout.tsx:17`), `cmdk@1.0.0` (command palette — wired at `components/layout/command-palette/CommandPaletteProvider.tsx:18`), `shadcn/ui`, Tailwind CSS 3.4+, TanStack Query v5, React Hook Form 7.x + Zod 3.x.
- *Frontend* — **NEW** dependencies introduced by this feature: `next-intl@3.x` (i18n library — chosen over `react-i18next` for App-Router-native server-component support; decision recorded in `research.md`), `@axe-core/playwright@4.x` (a11y CI runner extending the existing Playwright suite), `@formatjs/intl-localematcher@0.5.x` (locale negotiation between user/browser/URL/default per spec FR-489.2), `i18next-eslint-plugin` OR a small custom ESLint rule (the rule-13 lint check that flags hardcoded JSX strings).
**Storage**: PostgreSQL — 2 new tables (`user_preferences`, `locale_files`) via Alembic migration `066_localization.py`. No new Redis keys (locale files are loaded into a per-process LRU at request time; the cache key is `(locale_code, version)`). No MinIO/S3 paths.
**Testing**: pytest + pytest-asyncio 8.x for backend; Vitest + RTL + Playwright + MSW for frontend (all already present per feature 015). New: `@axe-core/playwright` for the a11y assertion harness, parameterised across the four themes × six locales.
**Target Platform**: Linux server (control plane). No new runtime profile — `localization/` runs on the existing `api` profile. No background jobs.
**Project Type**: Web service + cross-cutting frontend refactor. New BC under `apps/control-plane/src/platform/localization/` + cross-cutting changes across all 26 main routes under `apps/web/app/(main)/` (string extraction; theme-aware testing; per-route command registration; responsive audit) + 1 new route (`/settings/preferences`) + 1 new API call site in `notifications/service.py` (per-recipient language resolution).
**Performance Goals**: i18n resolution overhead ≤ 1 ms per render (`next-intl`'s server-side resolution adds negligible latency once the locale catalogue is in the per-process cache). axe-core CI run completes in ≤ 5 minutes across the audited surfaces × 4 themes × 6 locales (the cartesian is 24 × surface-count, but per-(theme, locale) pairs share rendered DOM most checks; the runner parallelises). Theme switching MUST be instant (no FOIT) — verified by visual regression test. Command palette MUST open in ≤ 100 ms p95 (already true today; verified by automated latency assertion). PWA manifest validation MUST pass the browser's installability checks (verified by Playwright's PWA installability assertion).
**Constraints**: **No FOIT on theme load** — the persisted theme preference must apply at first paint; this is enforced by reading the theme cookie at server-render time and emitting the matching theme class on the `<html>` element (Tailwind `dark`/`high-contrast` class strategy). **`?` help overlay must NOT hijack input** — the keyboard listener checks `document.activeElement` and ignores the keystroke when an input/textarea/contenteditable has focus. **Translation drift detection runs per-namespace, not whole-catalogue**: a partial drift (e.g., `marketplace.*` is up-to-date, `auth.*` is 8 days behind) MUST precisely identify the affected namespace so the PR author knows which sections to fix. **Per-locale message catalogues are loaded into a per-process LRU**: the LRU is bounded by `localization_locale_lru_size` (default 12 = 6 locales × 2 versions for the version-rollover window) so a hot-loaded new translation arrives without restart but stale versions don't accumulate. **The notification language resolution honours rule 41 fail-closed for auth-related notifications**: if the recipient's preference cannot be resolved (e.g., DB unavailable), notifications fall back to the platform default (English) — this is NOT a rule-41 violation because the fallback preserves *delivery*, just not language; an auth notification in English is still actionable. **Right-to-left** is OUT of scope at v1, but every CSS file written in this feature MUST use logical properties (`padding-inline-start`, `margin-inline-end`, `text-align: start`) so the future RTL addition is mechanical.
**Scale/Scope**: 26 main routes under `app/(main)/` × ~hundreds of user-facing strings each = order-of-magnitude **2,000–5,000 translation keys** total at v1 (estimate; the field-guide grep found ~73 obvious JSX literals just under `app/`, and the full audit will surface many more in component files, error messages, ARIA labels, and form validation). 6 locales × ~3,000 keys (mid-estimate) = ~18,000 translation entries to ship at launch. 4 themes × the surface-set audited by axe-core. PWA manifest is a single static file; service worker is OUT of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Source | Status | Notes |
|---|---|---|---|
| Brownfield rule 1 — never rewrite | Constitution § Brownfield | ✅ Pass | New BC `localization/`. Modifies `apps/web/` cross-cuttingly via additive string-extraction (existing JSX wraps an extracted key; the function call shape is additive); modifies `notifications/service.py` additively (adds optional `language` parameter that defaults to platform default); modifies CI `.github/workflows/ci.yml` additively. No file rewritten. |
| Brownfield rule 2 — Alembic only | Constitution § Brownfield | ✅ Pass | Single migration `066_localization.py` adds 2 tables. No raw DDL. |
| Brownfield rule 3 — preserve tests | Constitution § Brownfield | ✅ Pass | Existing tests stay green. The new ESLint rule (rule-13 enforcement) is wired with an initial allowlist of pre-existing files so the cross-cutting refactor lands in waves without breaking the lint baseline mid-feature. |
| Brownfield rule 4 — use existing patterns | Constitution § Brownfield | ✅ Pass | New BC follows the standard layout (`models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`). Frontend i18n integration follows `next-intl`'s App-Router-native pattern (`messages/{locale}.json` + provider in root layout). axe-core integration extends the existing Playwright config (no new test runner). |
| Brownfield rule 5 — cite exact files | Constitution § Brownfield | ✅ Pass | Project Structure below names every file; integration seams cite file:line for all call sites. |
| Brownfield rule 6 — additive enums | Constitution § Brownfield | ✅ Pass | New string-CHECK constants (`THEMES = ("light","dark","system","high_contrast")`, `LOCALES = ("en","es","fr","de","ja","zh-CN")`) live in `localization/constants.py`. No mutation of existing enums. |
| Brownfield rule 7 — backwards-compatible APIs | Constitution § Brownfield | ✅ Pass | A user with no persisted preferences sees the platform default (English, Light theme, browser timezone) — exactly the current behaviour. Notifications continue to deliver in English when the recipient has no language preference. The `notifications/service.py` `language` parameter is optional with the default-language fallback. |
| Brownfield rule 8 — feature flags | Constitution § Brownfield | ✅ Pass | `FEATURE_I18N` is constitutionally "always on" (line 890); no toggle. |
| Rule 9 — every PII operation audited | Constitution § Domain | ✅ Pass | Every user-preference mutation emits an audit-chain entry via `AuditChainService.append` (`audit/service.py:49`); locale-file publish events also audited. User preferences are PII-adjacent (a user's language reveals locale; their timezone reveals approximate location) — the audit boundary applies. |
| Rule 13 — every user-facing string goes through i18n | Constitution § Domain | ✅ Pass | This feature IS the canonical implementation that rule 13 presumes exists. The ESLint rule that enforces "no hardcoded JSX user-facing strings" is delivered here (Phase 8 — T058 in tasks); the cross-cutting string extraction across all 26 main routes is the bulk of the frontend work. |
| Rule 18, AD-21 (residency at query time) | Constitution § Domain | ✅ Pass | Locale files are platform-global (not per-region); user preferences replicate via the existing `users` table replication path (feature 081). No new residency surface. |
| Rule 20, 22 (structured JSON logs, low-cardinality labels) | Constitution § Domain | ✅ Pass | All new modules use `structlog`. Translation-key-not-found warnings log namespace + key in JSON payload; never as Loki labels (would explode cardinality). |
| Rule 21 (correlation IDs context-managed) | Constitution § Domain | ✅ Pass | Preference mutations carry the existing `CorrelationContext` via FastAPI's request-scoped middleware. |
| Rule 23, 31, 40 (no secrets in logs) | Constitution § Domain | ✅ N/A | This feature handles no secrets. |
| Rule 24 (every BC dashboard) | Constitution § Domain | ✅ Pass | New `deploy/helm/observability/templates/dashboards/localization.yaml` ConfigMap following the `cost-governance.yaml` pattern. Panels: translation-key-not-found rate per locale (a high rate signals stale catalogues), per-locale request rate (validates the locale negotiation is working), preference-mutation rate, locale-file publish events. |
| Rule 25, 26, 28 (E2E suite + journey crossing + extend not parallel) | Constitution § Domain | ✅ Pass | New `tests/e2e/suites/localization/` suite. **The constitutionally-named "Accessibility User journey (J15)"** (constitution rule 28) is delivered by this feature — a new operator + creator journey (sign up → set preferred locale → change theme → navigate via keyboard → screen-reader announce a state-change → invoke a workflow) per rule 25 + rule 28 (extend the existing journey tree, do not parallel). |
| Rule 28 (accessibility tested via axe-core, fails build on AA violation) | Constitution § Domain | ✅ Pass | The CI integration is delivered in this feature: `.github/workflows/ci.yml:417–451 test-frontend` job extended with a `pnpm test:a11y` step that runs Playwright + `@axe-core/playwright` across the audited surfaces × 4 themes; any AA violation fails the build with the violating selector + rule-id. |
| Rule 29, 30 (admin endpoint segregation, admin role gates) | Constitution § Domain | ✅ Pass | Locale-file publish (admin) lives under `/api/v1/admin/locales/*` with `require_superadmin` (rule 30). User-preference CRUD lives under `/api/v1/me/preferences` (constitutionally-reserved at line 811) — workspace-member-RBAC, no admin gate (rule 46 — `/api/v1/me/*` accepts no `user_id` parameter; always operates on the authenticated principal). |
| Rule 32 (audit chain on config changes) | Constitution § Domain | ✅ Pass | Preference mutations + locale-file publish events emit audit-chain entries. |
| Rule 36 (UX-impacting FR documented) | Constitution § Domain | ✅ Pass | The new `/settings/preferences` page, the help overlay (`?`), and the per-locale rendering conventions are documented in the docs site as part of this PR. |
| Rule 38 (multi-language parity enforced) | Constitution § Domain | ✅ Pass | This feature delivers the drift-check tooling that rule 38 presumes exists. The check runs in CI per-namespace (not whole-catalogue) so partial drift is precisely identified. |
| Rule 41 (Vault failure does not bypass auth) | Constitution § Domain | ✅ N/A — but related | This feature does not handle auth credentials; the related "fail-closed for delivery, fail-open for language fallback" decision (notifications fall back to English on preference-resolution failure) is documented in Constraints above. |
| Rule 45 (backend has UI) | Constitution § Domain | ✅ Pass | New `/settings/preferences` page (extends the existing `app/(main)/settings/` stub) hosts the user-preference UI. |
| Rule 46 (`/api/v1/me/*` scoped to current_user) | Constitution § Domain | ✅ Pass | `/api/v1/me/preferences` accepts no `user_id` parameter and always operates on the authenticated principal. Cross-user preference access is impossible. |
| Rule 50 (mock LLM for previews) | Constitution § Domain | ✅ N/A | This feature does not invoke an LLM. |
| Principle I (modular monolith) | Constitution § Core | ✅ Pass | All backend work in the Python control plane. |
| Principle III (dedicated stores) | Constitution § Core | ✅ Pass | PostgreSQL for relational truth (2 tables). No vector / OLAP / graph use. Per-process LRU for locale-file content (not Redis — locale files are < 1 MB total per locale, fit comfortably in process memory; Redis round-trip is unnecessary overhead). |
| Principle IV (no cross-BC table access) | Constitution § Core | ✅ Pass | `localization/` calls into `auth/` (verify user exists) and `workspaces/` (verify default-workspace membership) only via their public service interfaces. The reverse direction: `notifications/service.py` calls into `LocalizationService.get_user_language(user_id)` — public service interface, not direct table access. |
| Principle V (append-only journal) | Constitution § Core | ✅ N/A | No journal interaction. |
| Principle XVI (generic S3) | Constitution § Core | ✅ N/A | Locale files are committed under git (`apps/web/messages/`) AND mirrored in the `locale_files` PostgreSQL table for runtime; no S3. |
| Constitutional REST prefixes already declared | Constitution § REST Prefix lines 811–812 | ✅ Pass | `/api/v1/me/preferences` and `/api/v1/locales/*` already in the prefix registry. Admin authoring uses the segregated `/api/v1/admin/*` prefix per rule 29. |
| Constitutional feature flag already declared | Constitution § Feature Flag Inventory line 890 | ✅ Pass | `FEATURE_I18N=true` is "always on"; this plan operates under that assumption. |

## Project Structure

### Documentation (this feature)

```text
specs/083-accessibility-i18n/
├── plan.md                  # This file
├── spec.md                  # Feature spec
├── planning-input.md        # Verbatim brownfield input (preserved as planning artifact)
├── research.md              # Phase 0 — i18n library decision (next-intl over react-i18next),
│                            #   translation vendor choice (Lokalise vs Crowdin vs Phrase),
│                            #   message-catalogue namespace structure, locale negotiation
│                            #   precedence, drift-check algorithm
├── data-model.md            # Phase 1 — 2 PG tables + per-process LRU for locale files;
│                            #   the user_preferences shape; the locale_files versioning model
├── quickstart.md            # Phase 1 — local end-to-end walk: extract a string in a route →
│                            #   translate it via the vendor → see it render in the active
│                            #   locale → toggle to high-contrast → run axe-core locally
├── contracts/               # Phase 1
│   ├── localization-service.md             # User preferences + locale resolution
│   ├── locale-file-service.md              # Publish, list, get, version semantics
│   ├── drift-check.md                      # The CI script; per-namespace timestamp comparison
│   ├── i18n-eslint-rule.md                 # The custom ESLint rule for rule 13
│   ├── axe-core-runner.md                  # Playwright integration; theme/locale parameterisation
│   ├── preferences-rest-api.md             # /api/v1/me/preferences
│   ├── locales-rest-api.md                 # /api/v1/locales/* + /api/v1/admin/locales/*
│   └── notifications-language-hook.md      # The notifications/service.py integration
├── checklists/
│   └── requirements.md
└── tasks.md                 # Created by /speckit.tasks (NOT created here)
```

### Source Code (repository root)

```text
apps/control-plane/
├── migrations/versions/
│   └── 066_localization.py                              # NEW — 2 tables (rebase to current head at merge)
└── src/platform/
    ├── localization/                                    # NEW BOUNDED CONTEXT (Constitution § New BCs line 494)
    │   ├── __init__.py
    │   ├── constants.py                                 # NEW — THEMES = ("light","dark","system",
    │   │                                                #   "high_contrast"); LOCALES = ("en","es","fr",
    │   │                                                #   "de","ja","zh-CN"); DEFAULT_LOCALE = "en";
    │   │                                                #   DEFAULT_THEME = "system"; LOCALE_LRU_SIZE = 12
    │   ├── models.py                                    # NEW — UserPreferences, LocaleFile SQLAlchemy
    │   │                                                #   models (FK to users; FK to workspaces for
    │   │                                                #   default_workspace_id)
    │   ├── schemas.py                                   # NEW — UserPreferencesResponse,
    │   │                                                #   UserPreferencesUpdateRequest (PATCH-shape;
    │   │                                                #   each field optional), LocaleFileResponse,
    │   │                                                #   LocaleFilePublishRequest (admin),
    │   │                                                #   LocaleResolveRequest (the locale-negotiation
    │   │                                                #   helper input), DriftCheckResponse
    │   ├── service.py                                   # NEW — LocalizationService facade
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── preferences_service.py                   # NEW — get_for_user, upsert (PATCH semantics —
    │   │   │                                            #   only provided fields update; others retain
    │   │   │                                            #   prior values), get_user_language (the hot
    │   │   │                                            #   path for notifications integration)
    │   │   ├── locale_file_service.py                   # NEW — publish (admin only; bumps version,
    │   │   │                                            #   sets published_at), get(locale_code), list,
    │   │   │                                            #   get_namespaces (used by drift-check), the
    │   │   │                                            #   per-process LRU is held here
    │   │   └── locale_resolver.py                       # NEW — resolve_active_locale(*, url_hint,
    │   │                                                #   user_preference, accept_language) returning
    │   │                                                #   the negotiated locale per FR-489.2; uses
    │   │                                                #   @formatjs/intl-localematcher equivalent
    │   │                                                #   (langcodes / babel.localedata) for the match
    │   ├── repository.py                                # NEW — PG queries; UPSERT on user_preferences;
    │   │                                                #   versioned INSERT on locale_files
    │   ├── router.py                                    # NEW — /api/v1/me/preferences (GET, PATCH);
    │   │                                                #   /api/v1/locales/{locale_code} (GET);
    │   │                                                #   /api/v1/locales (GET — list available);
    │   │                                                #   /api/v1/admin/locales (POST — publish a
    │   │                                                #   new version; require_superadmin)
    │   ├── events.py                                    # NEW — UserPreferencesUpdatedPayload,
    │   │                                                #   LocaleFilePublishedPayload; topic
    │   │                                                #   `localization.events`
    │   ├── exceptions.py                                # NEW — UnsupportedLocaleError → 422,
    │   │                                                #   InvalidThemeError → 422,
    │   │                                                #   InvalidTimezoneError → 422 (validate against
    │   │                                                #   IANA tz database via zoneinfo.available_timezones())
    │   └── dependencies.py                              # NEW — FastAPI deps; reuses get_audit_chain_service
    │
    ├── notifications/
    │   └── service.py                                   # MODIFIED — at AlertService methods (≈ :167
    │                                                    #   process_attention_request and :203
    │                                                    #   process_state_change), at the dispatch site,
    │                                                    #   call await localization_service.
    │                                                    #   get_user_language(recipient_user_id) and pass
    │                                                    #   to the notification template renderer; on
    │                                                    #   resolution failure, fall back to
    │                                                    #   DEFAULT_LOCALE (FR-CC-4 — "fail-open for
    │                                                    #   language fallback" per Constraints rationale)
    │
    └── main.py                                          # MODIFIED — register localization_router at
                                                         #   the existing router-mount block (:1540–1579):
                                                         #     app.include_router(localization_router)
                                                         #   no middleware added; no APScheduler jobs

apps/web/
├── package.json                                         # MODIFIED — add next-intl@3.x,
│                                                         #   @axe-core/playwright@4.x,
│                                                         #   @formatjs/intl-localematcher@0.5.x,
│                                                         #   eslint-plugin-formatjs (or custom rule)
├── i18n.config.ts                                       # NEW — locale list, default locale,
│                                                         #   namespace structure
├── middleware.ts                                        # MODIFIED — extend the existing middleware
│                                                         #   to honour `?lang=` URL hint and to write
│                                                         #   the negotiated locale into a request-
│                                                         #   scoped cookie that the server-render
│                                                         #   uses for first-paint locale (avoids FOIT
│                                                         #   for locale-aware content)
├── messages/                                            # NEW — per-locale message catalogues
│   ├── en.json                                          #   English source of truth (committed)
│   ├── es.json                                          #   Spanish (translated by vendor; synced via CI)
│   ├── fr.json
│   ├── de.json
│   ├── ja.json
│   └── zh-CN.json
├── public/
│   ├── manifest.json                                    # NEW — PWA manifest with icon, short_name,
│   │                                                     #   theme_color, display=standalone
│   └── icons/                                           # NEW — PWA icon variants (192x192, 512x512,
│                                                          #   maskable)
├── app/
│   ├── layout.tsx                                       # MODIFIED — wrap children with
│   │                                                     #   <NextIntlClientProvider>; the existing
│   │                                                     #   <NextThemesProvider> at :17 is preserved;
│   │                                                     #   the `themes` array is extended to include
│   │                                                     #   "high-contrast"; the `class` strategy
│   │                                                     #   already in place handles the new variant
│   │                                                     #   via Tailwind config; render the PWA
│   │                                                     #   manifest link
│   ├── manifest.ts                                      # OR (alternative to public/manifest.json) —
│   │                                                     #   App Router-native manifest source per
│   │                                                     #   Next.js 14 conventions; decision in
│   │                                                     #   research.md
│   └── (main)/
│       ├── settings/                                    # MODIFIED — existing stub at page.tsx becomes
│       │   ├── page.tsx                                 #   the settings index (links to sub-pages)
│       │   ├── preferences/                             # NEW route — the user-preference UI
│       │   │   └── page.tsx                             #   form with theme picker, language picker,
│       │   │                                            #   timezone picker, default-workspace picker,
│       │   │                                            #   notification preferences sub-section,
│       │   │                                            #   data-export-format picker
│       │   └── (existing sub-routes preserved)          #   governance/, visibility/, alerts/
│       ├── (admin)/locales/                             # NEW route — admin locale-file publishing
│       │   └── page.tsx                                 #   superadmin-gated; upload/publish a new
│       │                                                #   version per locale; view drift status
│       └── (existing 26 routes)                         # ALL MODIFIED — string extraction
│
├── tailwind.config.ts                                   # MODIFIED — add `high-contrast` to the
│                                                         #   theme variants; define the high-contrast
│                                                         #   colour ramp meeting AAA where feasible
│
├── components/
│   ├── layout/
│   │   ├── command-palette/
│   │   │   ├── CommandPaletteProvider.tsx               # MODIFIED — at :18 the existing Cmd+K binding
│   │   │   │                                            #   is preserved; extend to support per-route
│   │   │   │                                            #   command registration via React context
│   │   │   ├── CommandPalette.tsx                       # MODIFIED — extract strings; render
│   │   │   │                                            #   commands grouped by category
│   │   │   ├── CommandRegistry.tsx                      # NEW — context provider that routes call to
│   │   │   │                                            #   register their context-specific commands
│   │   │   └── HelpOverlay.tsx                          # NEW — `?` overlay listing all registered
│   │   │                                                #   shortcuts grouped by category; keyboard
│   │   │                                                #   listener guards against input-focus
│   │   │                                                #   hijacking (Constraints rationale)
│   │   ├── theme-toggle/
│   │   │   └── ThemeToggle.tsx                          # MODIFIED — extend the existing toggle to
│   │   │                                                #   include the High-Contrast option
│   │   └── locale-switcher/
│   │       └── LocaleSwitcher.tsx                       # NEW — language picker; persists via
│   │                                                    #   /api/v1/me/preferences PATCH
│   └── (existing components)                            # ALL MODIFIED — string extraction
│
├── lib/
│   ├── api/preferences.ts                               # NEW — typed wrappers over /api/v1/me/preferences
│   ├── api/locales.ts                                   # NEW — typed wrappers over /api/v1/locales/*
│   ├── i18n/getRequestLocale.ts                         # NEW — server-side locale resolution helper
│   │                                                     #   (used in layout.tsx + server components);
│   │                                                     #   delegates to backend's locale_resolver
│   │                                                     #   service interface for canonical negotiation
│   ├── a11y/announceForScreenReader.ts                  # NEW — small helper for live-region
│   │                                                     #   announcements (state changes that aren't
│   │                                                     #   already announced by ARIA-live regions
│   │                                                     #   in shadcn primitives)
│   └── (existing lib modules unchanged)
│
├── tests/
│   ├── a11y/                                            # NEW — Playwright a11y suite
│   │   ├── playwright.a11y.config.ts                    # NEW — runs against the audited surface set
│   │   │                                                 #   parameterised across 4 themes × 6 locales;
│   │   │                                                 #   sharded across CI workers
│   │   ├── audited-surfaces.ts                          # NEW — the canonical list of surfaces axe-core
│   │   │                                                 #   covers (login, dashboard, marketplace,
│   │   │                                                 #   agent-detail, workflow editor, fleet view,
│   │   │                                                 #   operator dashboard, admin settings,
│   │   │                                                 #   policies, certifications, evaluation runs,
│   │   │                                                 #   the new preferences page)
│   │   └── *.spec.ts                                    # NEW — per-surface a11y tests using
│   │                                                     #   @axe-core/playwright
│   ├── visual/                                          # NEW — visual regression tests for theme
│   │   └── theme-no-foit.spec.ts                        #   switching (SC-007 — no FOIT on initial load)
│   └── e2e/i18n.spec.ts                                 # NEW — locale-switching E2E across three
│                                                          #   distinct surfaces in all six locales
├── eslint/
│   └── no-hardcoded-jsx-strings.js                      # NEW — custom ESLint rule (or formatjs plugin
│                                                          #   config) enforcing rule 13; allowlist of
│                                                          #   pre-existing files seeded so the rollout
│                                                          #   is incremental
└── (existing tests unchanged)

apps/control-plane/
└── src/platform/localization/
    └── tooling/
        └── drift_check.py                               # NEW — small Python script the CI step
                                                          #   invokes; queries locale_files; returns
                                                          #   non-zero exit on > 7-day drift per
                                                          #   namespace touched by the PR

deploy/helm/observability/templates/dashboards/
└── localization.yaml                                    # NEW — Grafana dashboard ConfigMap (rule 24)

.github/workflows/
└── ci.yml                                               # MODIFIED — at :417–451 test-frontend, add
                                                          #   `pnpm test:a11y` step (after vitest);
                                                          #   add a new `translation-drift` job that
                                                          #   runs `python -m platform.localization.
                                                          #   tooling.drift_check --pr-base=$BASE_SHA`
                                                          #   and fails the build on > 7-day drift
                                                          #   per namespace touched by the PR

apps/control-plane/tests/unit/localization/
├── test_preferences_service.py                          # NEW
├── test_locale_file_service.py                          # NEW
├── test_locale_resolver.py                              # NEW — precedence: URL > preference > browser
│                                                          #   > default; partial-fallback for missing
│                                                          #   keys
├── test_drift_check.py                                  # NEW — per-namespace; > 7 days fails
└── test_event_registration.py                           # NEW

apps/control-plane/tests/integration/localization/
├── test_preferences_api.py                              # NEW — GET/PATCH /api/v1/me/preferences;
│                                                          #   audit-chain emission per mutation
├── test_locale_publish_admin.py                         # NEW — admin-only; version bump; audit
├── test_notifications_language_hook.py                  # NEW — recipient's language drives platform-
│                                                          #   string portion of notification (FR-CC-4)
├── test_locale_resolver_e2e.py                          # NEW — URL hint > preference > browser >
│                                                          #   default precedence verified end-to-end
└── test_workspace_archival_preserves_preferences.py     # NEW — FR-CC-3
```

**Structure Decision**: One new bounded context (`localization/`) under `apps/control-plane/src/platform/`, owning user-preference storage (greenfield — neither `auth/` nor `accounts/` carry these fields today) and locale-file storage. Cross-cutting frontend work touches all 26 main routes under `apps/web/app/(main)/` plus the application shell at `apps/web/app/layout.tsx:17` (where the existing `<NextThemesProvider>` is preserved and `<NextIntlClientProvider>` added) and the existing command-palette components at `apps/web/components/layout/command-palette/CommandPaletteProvider.tsx:18` (preserved Cmd+K binding; extended with per-route registration). One small extension to `notifications/service.py` adds language-aware content selection (FR-CC-4). The `apps/ui/` path nominated by the brownfield input does NOT exist; the actual frontend is `apps/web/`. The four themes ship as Tailwind CSS classes via the existing `next-themes` `class` strategy; the High-Contrast variant is the only NEW theme (Light, Dark, System are already wired). The PWA manifest is delivered as Next.js 14 App Router-native `app/manifest.ts` (preferred over `public/manifest.json` for the typed inline approach; decision in `research.md`). Service worker / offline mode is OUT of scope per spec.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Two PostgreSQL tables (user_preferences + locale_files) | Field-guide research confirmed neither `auth/` nor `accounts/` stores any user-scoped preferences today; the substrate must come from somewhere. The `localization/` BC is the constitutional owner (line 494). Locale files are versioned (`locale_files.version`) so hot-rolling a new translation does not race with in-flight requests; an in-process LRU keyed on `(locale_code, version)` produces sub-microsecond lookups. | Add `language` / `theme` / `timezone` columns to `users` table directly: rejected — Principle IV violation (other BCs would query users.language directly across boundaries); also bloats the users row unnecessarily. Single JSONB `preferences` column on users: rejected — same Principle IV concern; also harder to query (e.g., "find all users whose default workspace is X"). Locale files in S3 / MinIO: rejected — Principle XVI prefers generic S3 only when files are large/binary; locale catalogues are small JSON < 1 MB total per locale, fit comfortably in PG + per-process LRU. |
| Per-process LRU for locale-file content (not Redis) | Locale files are read on every request that renders i18n strings (i.e., almost every request). A Redis round-trip (~1 ms p95) would dominate the i18n resolution budget. The LRU is bounded by `LOCALE_LRU_SIZE = 12` (6 locales × 2 versions for the rollover window) so memory is bounded; the cache key is `(locale_code, version)` so version bumps invalidate naturally. | Redis cache: rejected — round-trip dominates the per-request budget. No cache: rejected — every request would hit PG. In-process LRU with no version key: rejected — version rollovers would require process restart. |
| `next-intl` over `react-i18next` | `next-intl` is App-Router-native (server-component-friendly; the de-facto Next.js 14 i18n choice), produces smaller client bundles, and integrates with the existing middleware pattern at `apps/web/middleware.ts` for URL-hint resolution. `react-i18next` would require a client-side provider that defeats the platform's existing server-rendering pattern. | `react-i18next`: rejected — client-side-only orientation; bundle size; ergonomics with App Router server components. Hand-rolled i18n: rejected — would re-implement what the chosen library provides for free. |
| App Router-native `app/manifest.ts` over `public/manifest.json` | Next.js 14 App Router supports a TypeScript-typed `manifest.ts` that produces the JSON at build. This integrates with the platform's existing typed-everywhere convention (TypeScript 5.x strict per feature 015) and lets the manifest reference the same brand constants the rest of the UI uses (avoiding duplicate brand strings in two files). | `public/manifest.json`: rejected — duplicate-source-of-truth for brand constants; loses TypeScript type-checking. |
| Custom ESLint rule for "no hardcoded JSX user-facing strings" | Constitution rule 13 is explicitly a "code-review blocker" that needs CI enforcement; rule 13 cannot be human-only. `eslint-plugin-formatjs` is the closest off-the-shelf option but is opinionated about ICU MessageFormat; the platform's `next-intl` integration uses ICU but a thin custom rule keeps the message-format orthogonal to the rule-13 enforcement. The rule allowlists pre-existing files at the start of the rollout so the cross-cutting refactor lands incrementally without breaking the lint baseline mid-feature. | `eslint-plugin-formatjs` only: viable but couples rule-13 enforcement to a specific message-format opinion. Manual code review only: rejected — rule 13 is a "code-review blocker" only when humans catch every instance; we can't rely on humans for 5,000+ strings. |
| Notification language resolution at dispatch site (NOT recipient-side) | Platform-string portions of notifications must render in the recipient's language at the moment they are dispatched — by the time they reach the recipient's inbox, the language is baked in (an email cannot retroactively re-render its body). The dispatch site at `notifications/service.py:64+` is the canonical place; the resolution is `await localization_service.get_user_language(recipient_user_id)` returning a string. Failure falls back to DEFAULT_LOCALE (English) per the Constraints rationale — fail-open for language preserves delivery. | Render at recipient-side (e.g., re-translate when the user opens an email): rejected — emails are immutable post-send; would require live-translation infrastructure. |
| Drift-check runs per-namespace, not whole-catalogue | A typical PR touches a few namespaces (e.g., `marketplace.*` for a marketplace feature). Whole-catalogue drift would force the PR author to fix translations for sections they haven't touched — operationally unfair and noisy. Per-namespace drift identifies precisely which namespaces are over the 7-day budget; the PR fails only if it touches an over-budget namespace. | Whole-catalogue drift: rejected — operationally noisy; false-positive rate too high. |
| New ESLint rule allowlists pre-existing files at start of rollout | The cross-cutting string-extraction work spans 26 main routes + ~hundreds of components + ~thousands of strings. Forcing a single PR to do it all is a 5–8 week change. The allowlist lets the rollout land incrementally — each route's PR removes itself from the allowlist as part of its work. By the end of Wave 11D, the allowlist is empty and the rule is fully enforced. | Big-bang refactor: rejected — too risky; reviewable surface area exceeds practical limits. No enforcement until done: rejected — without enforcement the rollout drifts; new strings keep leaking in. |
| axe-core parameterised across 4 themes × 6 locales | The High-Contrast theme MUST exceed AA (FR-490.5); the AA test must run on every theme. Translated strings can have different lengths and break layouts, occasionally introducing AA violations only visible in non-English locales (e.g., a German translation that's 40% longer overflows a button). The cartesian (24 × surface-count) is the canonical proof for SC-006. | Run axe-core only on Light + English: rejected — would miss High-Contrast regressions and locale-induced AA violations entirely. |

## Dependencies

- **`audit/` BC (existing)** — `AuditChainService.append` at `audit/service.py:49–72` is the canonical write path. Confirmed unchanged.
- **`auth/` BC (existing)** — `auth/models.py` does NOT currently store any user preference fields; all preference storage is greenfield in this feature. The user-existence check in `LocalizationService.get_for_user` calls `AuthService.exists(user_id)` (public service interface; Principle IV).
- **`workspaces/` BC (existing)** — `default_workspace_id` references `workspaces.id`; the membership check (a user can only set a workspace they're a member of as default) goes through `WorkspaceService.is_member(user_id, workspace_id)`.
- **`notifications/` BC (feature 077)** — `AlertService` at `notifications/service.py:64+` does NOT currently accept a `language` parameter. This feature adds an additive optional parameter; the dispatch site calls `await localization_service.get_user_language(recipient_user_id)` and passes the result to the template renderer; on resolution failure, falls back to `DEFAULT_LOCALE` (English).
- **`security_compliance/` BC (UPD-024)** — not directly used; no secrets handled.
- **Existing `apps/web/`** (Next.js 14 App Router established by feature 015) — `apps/web/app/layout.tsx:17` already wires `<NextThemesProvider>`; this feature wraps it with `<NextIntlClientProvider>`. `apps/web/components/layout/command-palette/CommandPaletteProvider.tsx:18` already binds Cmd+K; this feature extends with per-route registration.
- **`next-themes@0.4.4`** (already in `apps/web/package.json`) — the substrate for theme switching. This feature adds the High-Contrast variant via Tailwind's class strategy.
- **`cmdk@1.0.0`** (already in `apps/web/package.json`) — the substrate for the command palette. This feature adds per-route command registration + the help overlay.
- **NEW frontend dependencies** — `next-intl@3.x`, `@axe-core/playwright@4.x`, `@formatjs/intl-localematcher@0.5.x`. Added to `apps/web/package.json` in this feature.
- **Existing CI pipeline** — `.github/workflows/ci.yml:417–451 test-frontend` job runs vitest coverage today; this feature extends it with `pnpm test:a11y` (Playwright + @axe-core/playwright) and adds a separate `translation-drift` job.
- **Existing settings stub** — `apps/web/app/(main)/settings/page.tsx` exists as a 1-line placeholder; this feature fills it (the index page links to sub-pages including the new `/preferences` route) without breaking the existing path reservation.
- **Constitution rule 13, 28, 38** — this feature is the canonical implementation that all three rules presume exists. The CI checks (the lint rule for 13, the axe-core run for 28, the drift script for 38) are first-class deliverables here.
- **Constitution § REST Prefix Registry lines 811–812** — `/api/v1/me/preferences` and `/api/v1/locales/*` already declared; admin authoring uses the segregated `/api/v1/admin/*` prefix per rule 29.
- **Constitution § Feature Flag Inventory line 890** — `FEATURE_I18N=true` is "always on"; no toggle.
- **Translation vendor** — Lokalise / Crowdin / Phrase. The choice is a planning concern (deferred to research.md). The integration shape is the same regardless: the vendor publishes per-locale JSON files; a CI step pulls them into `apps/web/messages/{locale}.json` on each merge to main; the audit-chain entry on locale-file publish records the version + vendor source ref.

## Wave Placement

**Wave 11** — placed after notifications (077, Wave 5), cost governance (079, Wave 7), incident response (080, Wave 8), multi-region (081, Wave 9), and tags/labels/saved-views (082, Wave 10). The brownfield input nominated **Wave 10**, but this feature integrates cross-cuttingly into the surfaces those features deliver: the saved-view dialog (082) needs i18n, the runbook viewer (080) needs i18n, the cost dashboard (079) needs i18n, the regions / maintenance / capacity panels (081) need i18n, the tag editor (082) needs i18n. Placing this in Wave 10 alongside 082 would force every prior feature's UI to be re-touched in two waves; placing it in Wave 11 lets the cross-cutting refactor land once across all stable UI surfaces. The trade-off: prior features ship with English-only strings during their own wave; the i18n extraction happens in Wave 11. This is the cleaner ordering.

**Note on the input's effort estimate** — the planning input estimated 6 story points (~3 days). The plan as designed is materially larger:

- **2 PG tables** + Alembic migration
- **`localization/` BC** (full BC: models, schemas, exceptions, events, repository, service, three sub-services, router, dependencies)
- **2 REST router groups** (`/api/v1/me/preferences` + `/api/v1/locales/*`) + admin segregation
- **1 cross-BC integration** in `notifications/service.py` for FR-CC-4
- **String extraction across 26 main routes + components**: estimated **2,000–5,000 translation keys** at v1; 6 locales × 3,000-mid = ~18,000 translation entries to ship
- **Translation vendor pipeline setup** (vendor selection + sync workflow + publish-on-merge step)
- **Custom ESLint rule** for rule-13 enforcement with allowlist
- **Drift-check Python script** + CI integration
- **axe-core wiring** (Playwright + `@axe-core/playwright`) **+ fix any existing AA violations** across the audited surfaces
- **High-Contrast theme** designed and tested across all surfaces (status badges, charts, focus indicators)
- **Per-route command registration + Help Overlay** across 26 routes
- **Responsive audit + fixes** across 26 routes (mobile / tablet breakpoints; "best on desktop" hint where applicable)
- **PWA manifest + icon set** (no service worker)
- **User-preferences page** (greenfield route at `/settings/preferences`)
- **Admin locale-file page** (greenfield route at `/admin/locales`)
- **Locale switcher component** in the application shell
- **Grafana dashboard** + OpenAPI tags + E2E suite + new operator journey (constitutionally-named "J15 Accessibility User journey" per rule 28)
- **Unit + integration + a11y + visual + E2E test coverage** to ≥ 95%

Realistically this is **10–15× the input's estimate** — possibly the largest cross-cutting refactor in the platform's recent history. Recommend a Wave 11A–11F split:

- **Wave 11A**: Backend `localization/` BC + 2 PG tables + audit emission + REST contracts (~2 days). Delivers the substrate.
- **Wave 11B**: `next-intl` install + middleware + layout integration + 6 empty locale catalogues + the custom ESLint rule with full allowlist (no extractions yet) (~2 days). Delivers the i18n machinery; existing UI continues working unchanged.
- **Wave 11C**: String extraction across the 26 main routes + components (parallelizable across multiple devs by route group). The ESLint allowlist shrinks per PR until empty (~1–2 weeks).
- **Wave 11D**: Translation vendor setup + initial 6-locale delivery + drift-check CI (~1 week, partially blocked on vendor turnaround).
- **Wave 11E**: axe-core wiring + High-Contrast theme + AA violation fixes + responsive audit (~1 week).
- **Wave 11F**: Command palette per-route registration + Help Overlay + PWA manifest + user-preferences page + admin locale-file page (~1 week).

The 3-day budget could land **Wave 11A only** (backend BC + REST contracts) — useful but the user-visible work is still future. If the goal is "ship i18n + a11y to users in one push," budget at least 6–8 weeks of coordinated frontend work across multiple devs. The constitution's rules 13 / 28 / 38 are explicit code-review blockers; lighting them up partially produces a ratchet that prevents future regressions but does not retroactively fix the existing strings.
