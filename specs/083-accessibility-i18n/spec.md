# Feature Specification: Accessibility (WCAG 2.1 AA) and Internationalization

**Feature Branch**: `083-accessibility-i18n`
**Created**: 2026-04-26
**Status**: Draft
**Input**: User description: "Bring the UI to WCAG 2.1 AA accessibility compliance, add internationalization for 6 languages (English, Spanish, French, German, Japanese, Chinese Simplified), dark mode, command palette, keyboard shortcuts, responsive design, and user preferences."

> **Scoping note (clarifies the brownfield input):** The brownfield input said this feature "modifies frontend (`apps/ui/`)." The actual frontend lives at **`apps/web/`** (Next.js 14 App Router; established by feature 015 `nextjs-app-scaffold`, extended by every subsequent UI feature). The path correction is recorded loudly so future planners do not chase the non-existent `apps/ui/` directory. The `localization/` bounded context is correctly named — the constitution declares it as the owner of UPD-030 at line 494.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Internationalisation Foundation: Every User-Facing String Goes Through `t()` (Priority: P1)

The web UI MUST be made fully internationalisable: every user-facing string in the platform's web surface is extracted into per-locale message catalogues, the application is wrapped in an i18n provider that resolves the active locale from (in order) the user's persisted preference, the URL hint, the browser preference, and finally the platform default; translation drift between the canonical English source and the other locales is detected by CI per the constitution's existing rule 38 ("Canonical English content can lead translation by at most 7 days"); and locale-specific formatting (dates, numbers, currencies) follows the active locale's conventions with the user's persisted override taking precedence over browser preference. Six languages — English, Spanish, French, German, Japanese, Chinese (Simplified) — are delivered at launch.

**Why this priority**: Until every user-facing string flows through `t()` and a locale-resolver, the platform is monolingual forever and constitution rule 13 ("Every user-facing string goes through i18n. Hardcoded strings in JSX/TSX are a code-review blocker") cannot be enforced. P1 is "the i18n substrate exists, six languages ship, and translation drift is observable" — every other capability in this feature stacks on top.

**Independent Test**: Switch the active locale (via the user-preference setting, the URL hint, and the browser) and confirm the platform's UI strings change accordingly across at least three distinct surfaces (login, marketplace listing, agent detail). Detect a deliberate translation gap by removing one Spanish string from the catalogue and confirming the CI parity check fails. Verify that a date displayed in the marketplace renders as `MM/DD/YYYY` in `en-US`, `DD/MM/YYYY` in `es-ES`, `YYYY/MM/DD` in `ja-JP`, and that a currency renders with the active locale's symbol and decimal convention.

**Acceptance Scenarios**:

1. **Given** an authenticated user with persisted language preference `es`, **When** the user navigates to any localised page, **Then** every user-facing string on that page renders in Spanish; no English fragment leaks through.
2. **Given** an unauthenticated visitor with browser preference `fr-FR` and no platform preference, **When** the visitor opens the marketplace, **Then** strings render in French; the platform default (English) is used as fallback only for strings missing from the French catalogue.
3. **Given** a user with persisted preference `de` and a URL containing `?lang=ja`, **When** the page loads, **Then** the URL hint takes precedence (Japanese) for that session; the persisted preference is not silently overwritten.
4. **Given** a developer adds a new English string in a UI component, **When** the build runs CI, **Then** the parity check identifies the missing translations across the other five locales and either fails the build (after the 7-day grace per rule 38) or surfaces a warning (within grace).
5. **Given** a date displayed on the agent-detail page, **When** the active locale is `es-ES`, **Then** the date renders as `DD/MM/YYYY`; numbers use `.` as thousands separator and `,` as decimal; currency uses `€` with the locale's positioning convention.
6. **Given** a missing translation for a specific string in a non-English locale, **When** the page renders, **Then** the platform falls back to the English source rather than displaying the raw `t('key.path')` literal — no "translation key" leaks into the UI.

---

### User Story 2 - WCAG 2.1 AA Compliance Verified by axe-core in CI (Priority: P2)

The web UI MUST conform to WCAG 2.1 Level AA: keyboard navigation works for every interactive element, screen readers announce the right context via ARIA labels, colour contrast meets AA ratios, text resizes to 200% without loss of functionality, focus indicators are visible everywhere, and information is never conveyed by colour alone. The constitution already establishes the enforcement mechanism (rule 28: axe-core runs in headless browser automation and fails the build on any AA violation); this feature lights it up and brings the existing UI into compliance.

**Why this priority**: Accessibility is the inclusion guarantee. Without it the platform excludes a meaningful portion of users, fails legal-procurement requirements in many jurisdictions, and the constitution's rule 28 cannot be enforced in CI without the underlying compliance work. P2 is below P1 because i18n is the substrate that screen readers also need (translated ARIA labels) — but the gap between P1 and P2 is small in calendar time.

**Independent Test**: Run axe-core in headless-browser automation across all major UI surfaces (login, dashboard, marketplace, agent detail, workflow editor, fleet view, operator dashboard, admin settings). Verify zero WCAG 2.1 AA violations. Manually verify keyboard navigation through the marketplace's filter sidebar (Tab order is sensible, Escape dismisses popovers, arrow keys navigate the search results). Manually verify with a screen reader (VoiceOver / NVDA) that a status badge ("certification revoked") announces both the colour-coded severity AND the textual meaning.

**Acceptance Scenarios**:

1. **Given** the platform's web UI on any major surface, **When** axe-core runs in headless browser automation, **Then** zero WCAG 2.1 AA violations are reported.
2. **Given** a user navigating with keyboard only, **When** they Tab through any interactive page, **Then** focus order is sensible, every interactive element is reachable, focus is visibly indicated, Escape dismisses overlays, and arrow keys navigate within composite widgets.
3. **Given** a user with the system text size set to 200%, **When** they open any major surface, **Then** the layout adapts without overlap, truncation, or loss of interactive controls.
4. **Given** any UI surface that uses colour to convey state (status badges, severity indicators, alert pills), **When** the user views the surface, **Then** the colour is accompanied by a textual or icon-based cue so users who cannot perceive colour still receive the information.
5. **Given** a screen-reader user opens the agent-detail page, **When** the screen reader traverses the page, **Then** every interactive element announces its purpose via an ARIA label that is itself translated into the user's active locale.
6. **Given** the platform's CI pipeline, **When** a code change introduces an AA violation in any audited surface, **Then** the build fails with a clear pointer to the violating selector and the rule that was breached.

---

### User Story 3 - Theme Support: Light, Dark, System, High-Contrast (Priority: P3)

Users MUST be able to choose a theme — Light (default), Dark, System (follow OS preference), or High-Contrast — and that choice MUST persist per user across sessions. The High-Contrast variant is part of the WCAG 2.1 AA compliance package: users who need stronger contrast than the AA-compliant Light or Dark themes can select it. Theme switching is instant (no flash of incorrect theme on page load), and every UI surface honours the active theme without local overrides.

**Why this priority**: Theme support is foundational productivity ergonomics. P3 because it sits below the i18n + accessibility floor (a dark theme isn't useful if half the strings are missing or unreadable to a screen reader), but it's a high-visibility everyday convenience that operators and creators expect on day one.

**Independent Test**: From the user-preferences page, switch from Light to Dark and confirm every major surface (dashboard, marketplace, agent detail, workflow editor, operator dashboard) renders the dark variant without any FOIT/FOUC; switch to System and confirm the platform follows the OS preference (toggle the OS to dark mode and observe the platform follow); switch to High-Contrast and confirm contrast ratios exceed AA thresholds across every surface; log out and back in and confirm the chosen theme persists.

**Acceptance Scenarios**:

1. **Given** a user with no persisted theme preference, **When** they first load the platform, **Then** the theme is `system` (follows the OS preference) and the platform displays without any flash of light theme during dark-mode page load.
2. **Given** a user with persisted preference `dark`, **When** they navigate between any major surfaces, **Then** every surface honours the dark theme — no surface falls back to light without an explicit user toggle.
3. **Given** a user toggles to `high_contrast`, **When** axe-core runs on any major surface, **Then** zero AA contrast violations are reported (high-contrast must exceed the AA bar).
4. **Given** a user has their OS in dark mode, **When** they choose the `system` theme option, **Then** the platform renders in dark; if they later switch the OS to light, the platform follows on next page load.
5. **Given** a user changes theme, **When** the change is saved, **Then** the preference is persisted server-side and applies on next session (different browser, different device).
6. **Given** a high-contrast theme user, **When** they view a status badge, **Then** the badge's information is conveyed by both a high-contrast colour AND a textual / iconographic cue (consistency with US2-AS4).

---

### User Story 4 - Command Palette and Keyboard Shortcuts for Power Users (Priority: P4)

The web UI MUST provide a global command palette opened by `Cmd+K` / `Ctrl+K` that lets users navigate, create, search, and toggle settings without reaching for the mouse; configurable keyboard shortcuts MUST cover common operations (new conversation, search marketplace, open workspace, toggle theme); and a help overlay MUST be reachable via `?` to discover available shortcuts. The command palette is per-page extensible — each route registers the commands relevant to its context (e.g., the marketplace page registers "search marketplace," the operator dashboard registers "open incidents tab").

**Why this priority**: Power-user productivity. The platform already includes `cmdk` as a dependency (per feature 015's tech stack — "shadcn Command palette (Cmd+K)"), so the substrate exists; this feature lights up the per-page registration, the configurable shortcut system, and the discoverability overlay. P4 because the command palette is a multiplier on already-functional surfaces; it is not the floor.

**Independent Test**: Press `Cmd+K` from any page; confirm the palette opens with a context-relevant command list (e.g., from the marketplace, "Search marketplace…" and "Filter by tag…" are top of the list); type a partial command name and confirm fuzzy-match works; press Enter and confirm the navigation/action executes; press `?` and confirm the help overlay lists every registered shortcut grouped by category; navigate without the mouse for an entire end-to-end task (login → marketplace → invoke an agent).

**Acceptance Scenarios**:

1. **Given** an authenticated user on any page, **When** they press `Cmd+K` (macOS) or `Ctrl+K` (other platforms), **Then** the command palette opens within the platform's stated p95 input-latency budget.
2. **Given** the command palette is open, **When** the user types a partial command name, **Then** fuzzy-match presents the most likely candidates; pressing Enter executes the top candidate; pressing Escape closes the palette without action.
3. **Given** different routes (marketplace, fleet view, operator dashboard, admin settings), **When** the palette opens on each route, **Then** the route's context-specific commands are registered alongside the platform-wide commands; commands are grouped by category in the palette UI.
4. **Given** any page, **When** the user presses `?`, **Then** the help overlay opens listing every keyboard shortcut grouped by category, each with its keystroke and a description, all localised to the active language.
5. **Given** a user customises a keyboard shortcut (when the platform supports customisation in v1; see Out of Scope below), **When** they save the binding, **Then** the new binding takes effect immediately and is persisted per user.
6. **Given** a keyboard shortcut conflicts with a system or browser shortcut (e.g., `Cmd+T` is "open new tab" in browsers), **When** the user attempts to register the conflicting binding, **Then** the platform refuses with a clear error rather than silently swallowing the keystroke.

---

### User Story 5 - Responsive Design and Progressive Web App for Read-Mostly Mobile Flows (Priority: P5)

The web UI MUST be usable on tablet and mobile viewports for **read-mostly** use cases — viewing executions, responding to approval requests, reviewing alerts, browsing the marketplace — while creator and operator workflows that require complex composition (workflow editing, fleet topology editing, admin configuration) remain desktop-first per FR-492. The platform MUST publish a PWA manifest so users can "install" the platform on their device's home screen; offline support is out of scope for v1, but the manifest is.

**Why this priority**: Mobile read-only is a real operational need (responding to a P1 alert from a phone is a common pattern); attempting to make the entire creator/operator surface mobile-first is a 10× project that doesn't pay back the way "make the read-mostly flows usable on mobile" does. P5 because it stacks above the floor of i18n + a11y + theming + power-user productivity; the read-mostly surfaces are valuable additively but the platform delivers value without them.

**Independent Test**: Open the platform on a 375px-wide viewport (iPhone SE simulator); verify the marketplace listing is browsable, the agent-detail page is readable, the operator dashboard's incidents tab is reviewable, an approval-request notification can be approved/rejected. Verify that creator/operator-edit surfaces (workflow editor, admin settings) display a graceful "best on desktop" hint rather than rendering a broken or unusable layout. Install the PWA on a phone home screen via the browser's install prompt; reopen from the home screen and confirm the platform launches without browser chrome.

**Acceptance Scenarios**:

1. **Given** a user on a 375px-wide viewport, **When** they navigate to the marketplace, **Then** the listing renders responsively with a mobile-appropriate layout (card stack, no horizontal scroll, readable text).
2. **Given** a user on a 768px-wide viewport (tablet), **When** they navigate to any read-mostly surface, **Then** the layout adapts to a tablet-appropriate two-column layout where applicable.
3. **Given** a user on a 1280px+-wide viewport (desktop), **When** they navigate to any surface, **Then** the platform renders the full desktop layout per existing UI features.
4. **Given** a user on a mobile viewport navigating to a creator/operator-edit surface (e.g., the workflow editor), **When** the page loads, **Then** the platform renders a "best experienced on desktop" hint with a clear path to read-only viewing rather than a broken edit surface.
5. **Given** the platform served over HTTPS, **When** a user visits on a mobile browser, **Then** the browser's PWA install prompt is available; installing places the platform on the home screen with the configured icon and short name.
6. **Given** an approval-request notification arrives on the user's mobile device, **When** the user taps to open it, **Then** the approval surface is fully usable on the mobile viewport (approve, reject, comment).

---

### Edge Cases

- **Locale precedence**: the order is (1) URL hint `?lang=` (per-session override), (2) user persisted preference, (3) browser `Accept-Language` header, (4) platform default (English). Documented and applied uniformly; never ambiguous.
- **Translation drift**: when English source leads other locales by > 7 days for a given namespace, CI fails per constitution rule 38; warnings appear within the grace window. The drift detector compares per-namespace timestamps in `locale_files`, not whole-catalogue equivalence, so partial drift is precisely identifiable.
- **Missing translation key**: the platform falls back to English; the raw `t('key.path')` literal NEVER reaches the UI. Missing keys are logged at WARN with the namespace + key for the translation team.
- **Right-to-left languages**: Arabic and Hebrew are explicitly out of scope for v1 per FR-489, but the i18n substrate MUST NOT preclude them — message catalogues, locale-resolver, and CSS layout must be RTL-ready by design (e.g., use `padding-inline-start` instead of `padding-left`).
- **Locale-specific formatting**: dates, numbers, and currencies follow the active locale's conventions. Per-user override (a user in `es-ES` who prefers ISO 8601 dates) is supported via the user-preferences surface.
- **Accessibility + i18n interaction**: ARIA labels are themselves translated. A screen-reader user with `language=ja` hears Japanese announcements. axe-core checks operate on the rendered (translated) DOM; translation must not introduce AA violations (e.g., a longer translated string MUST NOT cause overflow or cropping).
- **Theme + accessibility interaction**: the High-Contrast theme exceeds AA (closer to AAA where feasible). Light and Dark themes both meet AA. axe-core verifies all three.
- **System-theme tracking**: when a user chooses `system` and the OS toggles dark/light, the platform honours the change on next page load (and ideally live via `prefers-color-scheme` media query) without a manual refresh.
- **Theme flicker on initial load**: the platform avoids FOIT (flash of incorrect theme) by reading the persisted preference at server-render or immediately at script-start, so the first paint matches the chosen theme.
- **Command-palette shortcut conflicts**: `Cmd+K` is widely accepted; `Cmd+T` / `Cmd+W` etc. are reserved by browsers — the platform's customisation surface refuses these explicitly. Localised keyboard layouts (e.g., German `QWERTZ`) MUST be considered for the help overlay's key labels.
- **Help overlay (`?`)**: the `?` key is already used by the in-shell platform-status banner for some interactions in some surfaces; the spec's `?` overlay only opens when no input element has focus (so typing `?` into a search box doesn't hijack the user).
- **Mobile creator/operator-edit surfaces**: the "best on desktop" hint MUST NOT block read-only viewing of the same data; users on mobile can still inspect a workflow or fleet, just not edit it.
- **PWA + auth**: the PWA's launch context MUST honour the platform's existing JWT-refresh flow (per feature 015); a user launching from the home screen on a stale session is redirected to login per the existing `?redirectTo=` deep-link pattern.
- **PWA + offline**: offline mode is out of scope for v1; the manifest exists but the service worker does NOT cache application shell or data. Future work.
- **Per-user time zone**: every timestamp displayed in the UI honours the user's persisted time zone (FR-493). Server-side audit-chain timestamps remain UTC; conversion happens at the rendering layer.
- **High-contrast for status badges**: severity colours (critical / high / warning / info) all carry a textual or iconographic cue, AND the high-contrast theme's colour ramp is verified by axe-core to maintain contrast.
- **Translation of user-generated content**: the platform translates platform-string surfaces (UI labels, button text, error messages) only; user-generated content (workspace names, agent descriptions, runbook text from feature 080) is NOT translated and renders as-authored. Documented loudly to prevent surprise.
- **Notification language**: notifications delivered via the existing notifications subsystem (feature 077) honour the recipient's language preference for platform-string portions; user-generated content in the notification (e.g., the title of an incident) is not translated.
- **Empty translations**: a translator submitting an empty string for a key (vs. an actual translation) MUST be detected by CI and treated as drift, not silently merged. Empty is not the same as "intentionally identical to source".
- **Brand and product names**: platform names ("musematic"), agent FQNs, and similar identifiers are NEVER translated.

## Requirements *(mandatory)*

### Functional Requirements

**Internationalisation (FR-489)**

- **FR-489.1**: Web UI MUST extract every user-facing string into per-locale message catalogues; hardcoded user-facing strings in JSX/TSX components are forbidden (constitution rule 13 — "code-review blocker").
- **FR-489.2**: System MUST resolve the active locale from the priority order (URL hint > persisted user preference > browser preference > platform default `en`) and apply it consistently across all user-facing surfaces.
- **FR-489.3**: System MUST ship six locales at launch: `en`, `es`, `fr`, `de`, `ja`, `zh-CN`.
- **FR-489.4**: Translation pipeline MUST integrate with at least one professional translation workflow (e.g., a connector to a translation management system); the choice of vendor is a planning concern.
- **FR-489.5**: Locale-specific formatting (dates, numbers, currencies) MUST follow the active locale's conventions; the user MUST be able to override format conventions per their preference (e.g., always-ISO dates regardless of locale).
- **FR-489.6**: Right-to-left language support MUST be planned (CSS uses logical properties, layout is RTL-ready) but is NOT delivered at v1 (Arabic / Hebrew out of scope per spec § Out of Scope).
- **FR-489.7**: A missing translation key MUST fall back to the English source; raw key literals (`t('key.path')`) MUST NEVER reach the rendered UI.
- **FR-489.8**: Translation drift MUST be detected at CI per constitution rule 38; English content leading non-English by > 7 days for any namespace fails the build for PRs touching the affected sections.
- **FR-489.9**: Brand names, agent FQNs, and similar identifiers MUST NOT be translated; user-generated content MUST NOT be translated.

**Accessibility (FR-488)**

- **FR-488.1**: Every interactive element MUST be operable via keyboard alone — Tab traversal, Enter / Space activation, arrow keys for composite widgets, Escape to dismiss overlays.
- **FR-488.2**: Every interactive element MUST carry an accessible name (ARIA label, label association, or visible text) that is itself translated into the active locale.
- **FR-488.3**: Colour contrast MUST meet WCAG 2.1 AA ratios; the High-Contrast theme MUST exceed AA.
- **FR-488.4**: The UI MUST resize to 200% text without loss of functionality, layout overlap, or cropped controls.
- **FR-488.5**: Focus indicators MUST be visible on every interactive element; the indicator MUST be distinguishable in all four themes (Light / Dark / System / High-Contrast).
- **FR-488.6**: Information conveyed by colour MUST also be conveyed by text or icon (severity badges, status pills, alert indicators).
- **FR-488.7**: Form validation messages MUST be programmatically associated with their fields (`aria-describedby`) and announced by screen readers.
- **FR-488.8**: Constitution rule 28 enforcement MUST be wired: axe-core runs in headless browser automation across the audited surfaces; any AA violation fails the CI build with a pointer to the violating selector + rule.

**Theming (FR-490)**

- **FR-490.1**: Web UI MUST support four themes: Light (default for new users with no OS preference), Dark, System (follows OS preference), High-Contrast.
- **FR-490.2**: Theme choice MUST persist per user across sessions and devices.
- **FR-490.3**: Theme switching MUST NOT cause a flash of incorrect theme (FOIT) on initial page load; the persisted preference MUST be applied at first paint.
- **FR-490.4**: All UI surfaces MUST honour the active theme uniformly; surface-specific theme overrides are forbidden.
- **FR-490.5**: The High-Contrast theme MUST be a complete variant — every UI surface, status badge, focus indicator, and chart palette MUST be designed for it; falling back to Light or Dark within High-Contrast is forbidden.

**Command Palette and Keyboard Shortcuts (FR-491)**

- **FR-491.1**: Web UI MUST provide a global command palette opened by `Cmd+K` (macOS) / `Ctrl+K` (other platforms).
- **FR-491.2**: The palette MUST register per-route context-specific commands alongside platform-wide commands.
- **FR-491.3**: Common operations MUST have keyboard shortcuts: new conversation, search marketplace, open workspace, toggle theme. The set is configurable per user.
- **FR-491.4**: A help overlay reachable via `?` (when no input has focus) MUST list every registered shortcut grouped by category, all localised to the active language.
- **FR-491.5**: Keyboard shortcut customisation MUST refuse system / browser-reserved shortcuts (e.g., `Cmd+T`, `Cmd+W`) with a clear error.

**Responsive Design and PWA (FR-492)**

- **FR-492.1**: Web UI MUST be responsive across the documented breakpoints (mobile 375px, tablet 768px, desktop 1280px+).
- **FR-492.2**: Read-mostly surfaces (marketplace browsing, execution viewing, approval responses, alert review, agent detail viewing, runbook viewing, post-mortem reading) MUST be fully usable on mobile and tablet viewports.
- **FR-492.3**: Creator and operator-edit surfaces (workflow editor, fleet topology editor, admin configuration) MAY render a "best experienced on desktop" hint on mobile viewports but MUST NOT render a broken or unusable layout — read-only viewing of the same data MUST remain available on mobile.
- **FR-492.4**: A PWA manifest MUST be published with the platform's icon, short name, and theme colour; users MUST be able to "install" the platform via the browser's install prompt.
- **FR-492.5**: PWA offline mode is OUT of scope for v1; the manifest exists, the service worker does NOT cache application shell or data.
- **FR-492.6**: PWA launch context MUST honour the platform's existing JWT-refresh flow and the existing `?redirectTo=` deep-link pattern.

**User Preferences (FR-493)**

- **FR-493.1**: Each user MUST be able to configure their default workspace, notification preferences (channels + quiet hours, extending FR-433), UI theme, language, time zone, and data-export download format.
- **FR-493.2**: Preferences MUST be persisted server-side per user; preferences apply across sessions and devices.
- **FR-493.3**: Time zone MUST default to the browser's detected zone and be user-overridable; every timestamp in the UI MUST display in the user's persisted time zone (server-side timestamps remain UTC; conversion at the rendering layer).
- **FR-493.4**: Notification preferences MUST cover delivery channels (email, in-app, mobile push if PWA-installed) and quiet-hours per channel; the preferences integrate with feature 077's notifications subsystem rather than introducing a parallel surface.
- **FR-493.5**: Data-export download format preference (e.g., JSON / CSV / NDJSON) MUST be honoured by every export surface that accepts a format choice.
- **FR-493.6**: Preferences MUST be auditable per FR-CC-2 — preference changes emit audit-chain entries.

**Cross-Cutting**

- **FR-CC-1**: The `localization/` bounded context MUST be a backend BC under `apps/control-plane/src/platform/localization/` (constitution § "New Bounded Contexts" line 494; UPD-030); REST endpoints under the constitutionally-reserved `/api/v1/me/preferences` and `/api/v1/locales/*` prefixes (constitution § REST Prefix lines 811–812).
- **FR-CC-2**: Every preference mutation and every published locale-file version MUST emit an audit-chain entry through the platform's existing audit-chain service — never written directly (constitution rule 9, 32).
- **FR-CC-3**: Preferences and locale files MUST survive workspace archival; historical record is durable.
- **FR-CC-4**: Notifications subsystem (feature 077) MUST honour the user's language preference for platform-string portions of notifications; user-generated content portions remain as-authored.
- **FR-CC-5**: All operator-facing surfaces (preferences page, locale-file admin page) MUST be reachable from the existing application shell and the existing user-menu (constitution rule 45).
- **FR-CC-6**: The constitutional feature flag `FEATURE_I18N` is "always on" (constitution § Feature Flag Inventory line 890); this feature lights up the always-on path. There is no toggle to disable i18n in the deployed product.

### Key Entities

- **User Preferences**: Per-user persisted settings — default workspace, theme, language, time zone, notification preferences, data-export format. One row per user. The `localization/` BC is the canonical owner of this table; other BCs read it via the BC's public service interface.
- **Locale File**: A versioned per-locale message catalogue. The English catalogue is the source of truth; non-English catalogues are versioned forwards, with the published-at timestamp driving CI's drift check (rule 38).
- **Locale Code**: An IETF BCP-47 language tag (`en`, `es`, `fr`, `de`, `ja`, `zh-CN`). The set is fixed at v1 to the six languages enumerated above.
- **Translation Key Namespace**: A logical grouping of strings (e.g., `marketplace.*`, `auth.*`, `errors.*`); the drift check operates per-namespace so partial drift is precisely identifiable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: axe-core runs against every audited surface in CI and reports zero WCAG 2.1 AA violations on the post-feature build — verified by automated assertion in the pipeline.
- **SC-002**: Every user-facing string in the web UI is sourced from the per-locale catalogues (no hardcoded JSX/TSX strings) — verified by an automated lint check that flags hardcoded user-facing strings as build failures (rule 13).
- **SC-003**: Six locales (`en`, `es`, `fr`, `de`, `ja`, `zh-CN`) are present at launch with ≥ 95% translation coverage of the canonical English source — verified by a pre-launch drift check.
- **SC-004**: Translation drift > 7 days fails the CI build per rule 38 — verified by a deliberate-drift test (introduce a missing-translation gap, advance the clock fixture > 7 days, assert build fails).
- **SC-005**: Locale-specific formatting (dates, numbers, currencies) renders correctly in each of the six locales across at least three distinct UI surfaces — verified by automated UI snapshot tests.
- **SC-006**: All four themes (Light, Dark, System, High-Contrast) pass axe-core AA checks on every audited surface — verified by parameterising the axe-core run across themes.
- **SC-007**: Theme switching produces no FOIT on initial page load in any theme — verified by automated visual regression testing.
- **SC-008**: Command palette opens within the platform's stated p95 input-latency budget (e.g., ≤ 100 ms) on every audited route — verified by automated latency assertions.
- **SC-009**: The help overlay (`?`) lists every registered keyboard shortcut localised to the active language — verified by automated assertion across the six locales.
- **SC-010**: Mobile (375px) viewport renders the read-mostly surfaces fully usable — verified by automated UI snapshot tests across at least the marketplace, execution viewer, approval surface, alert review, and incident detail views.
- **SC-011**: Creator/operator-edit surfaces on mobile viewport render the "best experienced on desktop" hint AND remain read-only-usable — verified by automated assertion across the workflow editor, admin settings, and at least three other edit surfaces.
- **SC-012**: PWA installable from a mobile browser; manifest passes the browser's installability checks — verified by automated PWA installability assertion.
- **SC-013**: User-preference mutations emit audit-chain entries — verified by automated audit-coverage check.
- **SC-014**: Every timestamp on every UI surface honours the user's persisted time zone — verified by automated assertion across at least three distinct surfaces with a user whose time zone differs from UTC.

## Assumptions

- The platform's existing web UI is `apps/web/` (Next.js 14 App Router established by feature 015). The `apps/ui/` path nominated by the brownfield input does not exist; the spec uses the real path.
- The platform's existing dependencies include `cmdk` (already in feature 015's tech stack as "shadcn Command palette (Cmd+K)") and `next-themes` (also in feature 015's tech stack); the substrate libraries are present and this feature lights up their per-feature usage.
- The `localization/` bounded context is a Python control-plane BC under `apps/control-plane/src/platform/localization/` (constitution § "New Bounded Contexts" line 494). This is a backend BC even though most of the *user-visible* work is in `apps/web/`; the BC owns user preferences storage, locale-file storage, and the drift-check telemetry.
- The platform's existing audit chain (UPD-024), notifications (feature 077), and workspace RBAC are reused; this feature does not introduce a parallel audit, notification, or authorization path.
- The set of six locales is fixed at v1; adding more is a future-additive change.
- Right-to-left language support (Arabic, Hebrew) is planned but not delivered at v1; the substrate is RTL-ready by design (CSS logical properties, layout structure) so the future addition does not require a refactor.
- PWA offline mode is out of scope for v1; the manifest exists, the service worker is not registered.
- User-generated content (workspace names, agent descriptions, runbook text) is NOT translated; only platform-string surfaces are.
- Notifications delivered through feature 077's subsystem honour the recipient's language preference for platform-string portions only.
- The High-Contrast theme is a complete variant; designing all four themes is part of this feature's deliverable, not a follow-up.
- The translation pipeline integrates with one professional vendor (e.g., Lokalise / Crowdin / Phrase); the choice of vendor is a planning concern.
- Translation review workflow (who approves translations) lives in the vendor's tooling, NOT the platform's audit chain — only the *publish* event of a locale-file version is audited platform-side.

## Out of Scope (v1)

- Right-to-left languages (Arabic, Hebrew). Planned, not delivered. The substrate is RTL-ready.
- PWA offline mode (service worker that caches the application shell or data). Manifest only at v1.
- Translation of user-generated content (workspace names, agent descriptions, runbook text, post-mortem text).
- Voice control / voice-driven interaction for accessibility (separate scope from WCAG 2.1 AA).
- Customisable colour themes beyond the four defined (Light / Dark / System / High-Contrast).
- Per-workspace locale defaults overriding per-user preferences.
- Live translation of incoming notifications already-rendered content (the language is selected at delivery time per the recipient's preference; subsequent updates do not retroactively re-translate).
- Localised currency conversion (the platform displays in the canonical currency declared at deployment per feature 079; locale formatting affects the *display* of the canonical value, not currency conversion).
- Full mobile creator/operator-edit support (workflow editor, fleet topology editor, admin configuration on mobile). Documented as desktop-first per FR-492.3.
- Public locale-file editing UI (translators use the vendor's tooling; platform admins import / publish completed locale-file versions).
- Translation memory / glossary management surfaces inside the platform.
- Per-user keyboard layout localisation beyond what the OS already provides (e.g., the platform does not remap keys for QWERTZ vs QWERTY at the application layer; the OS handles it).

## Dependencies and Brownfield Touchpoints

This feature is additive to the existing platform. The relevant existing capabilities the new bounded context relies on or extends:

- **Existing `localization/` bounded context slot** (Constitution § "New Bounded Contexts" line 494 — owns UPD-030 — and the constitutionally-declared REST prefixes `/api/v1/me/preferences` and `/api/v1/locales/*` at lines 811–812): this is the home for the implementation.
- **Existing `apps/web/` frontend** (established by feature 015 `nextjs-app-scaffold`): every UI feature merged after 015 lives under `apps/web/app/(main)/` and `apps/web/app/(auth)/`. This feature touches the application shell and every route group additively (extracts strings, applies the theme provider, registers commands per route).
- **`cmdk` library** (already in feature 015's tech stack): the substrate for the global command palette. This feature lights up per-route command registration on top of the existing `cmdk` integration.
- **`next-themes` library** (already in feature 015's tech stack): the substrate for theme switching. This feature lights up the four-theme variant set including High-Contrast.
- **Feature 077 (notifications)**: notification language honours the recipient's user-preference language; FR-CC-4 binds this without introducing a parallel notification path.
- **Audit chain** (`audit/service.py:48 AuditChainService.append`): the canonical write path for every preference mutation and every locale-file publish event (FR-CC-2, rule 9, 32).
- **Constitution rule 13** ("Every user-facing string goes through i18n. Hardcoded strings in JSX/TSX are a code-review blocker"): this feature is the canonical implementation that rule 13 presumes exists. The CI lint check that enforces rule 13 is delivered by this feature.
- **Constitution rule 28** ("Accessibility is tested, not promised. The Accessibility User journey (J15) runs axe-core in headless browser automation and fails the build on any WCAG AA violation"): this feature lights up the rule-28 enforcement and brings the existing UI into compliance so the rule's CI gate produces zero violations.
- **Constitution rule 38** ("Multi-language parity is enforced, not hoped. Canonical English content can lead translation by at most 7 days. Beyond that, CI blocks merges touching affected sections"): this feature delivers the drift-check tooling that rule 38 presumes exists.
- **Constitutional feature flag `FEATURE_I18N`** (line 890): "always on" — no toggle. This feature operates under the always-on assumption.
- **Existing user / workspace identity surfaces**: user preferences attach to the existing `users.id` foreign key; default-workspace preference references the existing `workspaces.id`.
- **Existing JWT auth + `?redirectTo=` deep-link pattern** (feature 017 `login-auth`): the PWA launch flow honours these; FR-492.6 binds.

The implementation strategy (specific tables, services, schemas, Helm chart layout, and code-level integration points across `apps/web/`'s 30+ existing routes) is intentionally deferred to the planning phase. The brownfield input that motivated this spec is preserved in the feature folder as `planning-input.md`.
