---
description: "Task list for UPD-045 — Public Status Page, Platform State Banner, and Remaining Workbench UIs (feature 095)"
---

# Tasks: UPD-045 — Public Status Page, Platform State Banner, and Remaining Workbench UIs

**Input**: Design documents from `specs/095-public-status-banner-workbench-uis/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: REQUIRED. Spec FR-695-50 / FR-695-51 / FR-695-52 mandate E2E journeys J21, J07, J09; Constitution Rule 25 (BC E2E suites), Rule 28 (axe-core), Rule 41 (AA fail the build). Unit + integration tests included alongside implementation per Brownfield Rule 3 ("New code MUST include tests").

**Organization**: Tasks grouped by user story (US1–US8 from spec.md). Each story is independently testable and deliverable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different file, no incomplete-task deps)
- **[Story]**: US1–US8 (from spec.md). Setup / Foundational / Polish phases have no story label.
- File paths absolute from repo root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: project initialisation and structural plumbing common to all three tracks.

- [X] T001 Confirm Alembic migration slot 095 is still free (verify under `apps/control-plane/migrations/versions/`); if claimed by an upstream merge, renumber to next-free at the top of every migration-touching task in this file.
- [X] T002 [P] Add `feedgen>=1.0,<2.0` to `apps/control-plane/pyproject.toml` (under `dependencies`) and re-lock with `uv lock` (or repo's lock command).
- [X] T003 [P] Scaffold `apps/web-status/` Next.js 14 project: create `apps/web-status/package.json`, `apps/web-status/next.config.mjs` with `output: 'export'`, `apps/web-status/tsconfig.json`, `apps/web-status/tailwind.config.ts` mirroring `apps/web/tailwind.config.ts`, `apps/web-status/postcss.config.mjs`, `apps/web-status/app/layout.tsx`, `apps/web-status/app/globals.css`, `apps/web-status/.gitignore`, `apps/web-status/README.md`. Add `apps/web-status` to root `pnpm-workspace.yaml`. Dependencies: `next@14`, `react@18`, `react-dom@18`, `tailwindcss@3.4`, `lucide-react`, `date-fns@4`. NO `next-intl` (per research R12).
- [X] T004 [P] Create `apps/web-status/Dockerfile` (multi-stage: node 20-alpine build → nginx 1.27-alpine serve `/usr/share/nginx/html` mounted from `out/` + a volume for `last-known-good.json`).
- [X] T005 Add a one-line additive change to `apps/control-plane/src/platform/common/auth_middleware.py`: introduce `EXEMPT_PREFIXES: frozenset[str]` alongside the existing `EXEMPT_PATHS`, with a `startswith()` check in the middleware path matching (per research R1 implementation note). Existing exact-match semantics preserved; no current EXEMPT_PATHS entry overlaps the new prefix family.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: schema, channel registration, BC scaffold, locale parity, shared component move. **NO user-story work may begin until this phase is checkpoint-complete.**

### Database & migration

- [X] T006 Author Alembic migration `apps/control-plane/migrations/versions/095_status_page_and_scenarios.py` per `data-model.md` §"Migration summary": creates `platform_status_snapshots`, `status_subscriptions`, `subscription_dispatches`, `simulation_scenarios` tables; adds nullable `simulation_runs.scenario_id` FK; seeds synthetic `system_status` workspace (per research R7). Include all indexes (`IX_platform_status_snapshots_generated_at_desc`, `IX_status_subscriptions_user_id`, `IX_status_subscriptions_workspace_id`, `UQ_status_subscriptions_channel_target_confirmed` partial, `IX_subscription_dispatches_*`, `IX_simulation_scenarios_workspace_id_archived_at`, `UQ_simulation_scenarios_workspace_name_active` partial, `IX_simulation_runs_scenario_id`).
- [ ] T007 Run `alembic upgrade head` against the dev cluster and verify all 4 new tables + the new column exist with the exact constraints listed; capture output for the PR description.

### `status_page/` bounded context scaffold

- [X] T008 [P] Create `apps/control-plane/src/platform/status_page/__init__.py` and the empty BC structure files per research R10: `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`, `me_router.py`, `events.py`, `exceptions.py`, `dependencies.py`, `projections.py`, `feed_builders.py`. Each file gets a module-level docstring referencing FR-675–FR-682 and `specs/095-public-status-banner-workbench-uis/plan.md`.
- [X] T009 [P] Implement `apps/control-plane/src/platform/status_page/exceptions.py`: `SubscriptionNotFound`, `ConfirmationTokenInvalid`, `ConfirmationTokenExpired`, `RateLimitExceeded`, `SubscriptionAlreadyConfirmed`, `WebhookVerificationFailed` — all inheriting from `PlatformError` (per `apps/control-plane/src/platform/common/exceptions.py`).
- [X] T010 Implement `apps/control-plane/src/platform/status_page/models.py`: `PlatformStatusSnapshot`, `StatusSubscription`, `SubscriptionDispatch` SQLAlchemy classes per `data-model.md` §1, §2, §3. Use existing mixins (`UUIDMixin`, `TimestampMixin`) from `apps/control-plane/src/platform/common/models/`. Include the state-machine constants documented in data-model.md §2.

### WebSocket channel registration

- [X] T011 [P] Extend `apps/control-plane/src/platform/ws_hub/subscription.py`: add `ChannelType.PLATFORM_STATUS = "platform-status"`; add a new `USER_SCOPED_GLOBAL_CHANNELS = frozenset({ChannelType.ALERTS, ChannelType.ATTENTION, ChannelType.PLATFORM_STATUS})` (per `contracts/platform-status-ws.md`); extend `CHANNEL_TOPIC_MAP[ChannelType.PLATFORM_STATUS] = ["multi_region_ops.events", "incident_response.events", "platform.status.derived"]`.
- [X] T012 [P] Extend `apps/web/types/websocket.ts`: add `"platform-status"` to the `WsChannel` union (per `contracts/platform-status-ws.md`).

### i18n parity

- [X] T013 Create `apps/web/messages/it.json` by copying the full key set from `apps/web/messages/en.json` verbatim (research R3). Italian translations are a follow-up; English-fallback content keeps key parity. Add `apps/web/messages/it.json` to the import allow-list in the next-intl loader (`apps/web/i18n/request.ts` or equivalent).
- [X] T014 Add UPD-045 i18n namespace stub keys to all six FR-620 locales (`en`, `es`, `de`, `fr`, `it`, `zh-CN`) AND to `ja` (preserved per R3): namespaces `platformStatus`, `simulations.scenarios`, `discovery.session`, `discovery.hypotheses`, `discovery.experiments`, `discovery.evidence`. Use the existing extraction script (`apps/web/scripts/i18n-extract.*`) if present; otherwise hand-author canonical English keys in `en.json` first and copy.

### Shared component move (Track C dependency)

- [X] T015 Move `apps/web/app/(main)/agent-management/[fqn]/contract/_components/RealLLMOptInDialog.tsx` to `apps/web/components/features/shared/RealLLMOptInDialog.tsx` (per research R8). Update the existing `ContractPreviewPanel.tsx` import path. Verify with `pnpm typecheck` and `pnpm test` that the contract preview still renders.

### Helm chart placeholders (Track A dependency)

- [X] T016 [P] Add the `webStatus` block to `deploy/helm/platform/values.yaml` with placeholder defaults (`enabled: false`, `image: { repository: "", tag: "" }`, `host: "status.local"`, `replicaCount: 2`). Activation happens in T026.
- [X] T017 [P] Create the empty Helm template files `deploy/helm/platform/templates/web-status-deployment.yaml`, `deploy/helm/platform/templates/web-status-ingress.yaml`, `deploy/helm/platform/templates/status-snapshot-cronjob.yaml`, `deploy/helm/platform/templates/configmap-status-routes.yaml` with `{{- if .Values.webStatus.enabled }}` guards. Body is filled in T026/T027/T028.

**Checkpoint**: foundation complete — all eight user stories may now begin in parallel.

---

## Phase 3: User Story 1 — Visitor checks platform status from outside the app (Priority: P1) 🎯 MVP

**Goal**: visitors can reach `status.musematic.ai` from any network and see overall + per-component + active-incident + 30-day-uptime status. The page survives a main-app outage.

**Independent Test**: open the public URL from a network with no access to the main app; page renders within 2s; subscribe affordances visible; axe-core AA passes.

### Tests for US1

- [X] T018 [P] [US1] Unit test snapshot composition in `apps/control-plane/tests/unit/status_page/test_service.py::test_compose_snapshot_overall_state_aggregation` covering 5 cases (all operational → operational; one degraded → degraded; one outage → partial_outage; all outage → full_outage; active maintenance → maintenance).
- [X] T019 [P] [US1] Unit test feed builders in `apps/control-plane/tests/unit/status_page/test_feed_builders.py`: RSS 2.0 + Atom 1.0 valid against W3C feed-validator-style assertions; stable-IDs match the scheme in `contracts/feed-formats.md`; subscriber identifiers MUST NOT appear (security note).
- [X] T020 [P] [US1] Integration test for public endpoints in `apps/control-plane/tests/integration/status_page/test_public_endpoints.py`: `/api/v1/public/status` returns 200 without auth, response shape matches `contracts/public-status-api.openapi.yaml#/components/schemas/PlatformStatusSnapshot`; `/api/v1/public/components/{id}` returns history; `/api/v1/public/incidents` filters by status; `/api/v1/public/status/feed.{rss,atom}` produces valid XML with correct content-type.
- [X] T021 [P] [US1] Vitest + RTL test for `apps/web-status/components/StatusBanner.test.tsx` (variants: operational/degraded/partial_outage/full_outage/maintenance — color + icon + text per FR-695-12 / SC-009).

### Implementation for US1

- [X] T022 [US1] Implement `apps/control-plane/src/platform/status_page/repository.py` (~110 LOC) — async SQLAlchemy queries: `get_current_snapshot()`, `insert_snapshot()`, `list_components()`, `get_component_history(component_id, days=30)`, `list_active_incidents()`, `list_recent_resolved_incidents(days=7)`, `get_uptime_30d()`.
- [X] T023 [US1] Implement `apps/control-plane/src/platform/status_page/service.py` snapshot composition (~80 of the ~220 LOC for this BC): `StatusPageService.compose_current_snapshot()` reads from `incidents`, `maintenance_windows`, and component health-poll cache; writes to `platform_status_snapshots` and `status:snapshot:current` Redis key (TTL 90s) + `status:fallback:lastgood` (TTL 24h). Computes `overall_state` per data-model §1 enum.
- [X] T024 [US1] Implement `apps/control-plane/src/platform/status_page/projections.py`: (a) Kafka consumer for `multi_region_ops.events` + `incident_response.events` triggering immediate snapshot recomposition; (b) APScheduler job firing every 60s polling each service's `/healthz` + `/readyz`; (c) APScheduler daily job computing 30d uptime rollup (writes to `platform_status_snapshots.payload.uptime_30d` on the next snapshot generation).
- [X] T025 [US1] Implement `apps/control-plane/src/platform/status_page/feed_builders.py` (~80 LOC) — `build_rss(snapshot, incidents)` and `build_atom(snapshot, incidents)` using `feedgen` per `contracts/feed-formats.md`. Produces UTF-8 bytes; sets canonical `<atom:link rel="self">`.
- [X] T026 [US1] Implement `apps/control-plane/src/platform/status_page/router.py` GET endpoints: `/api/v1/public/status`, `/api/v1/public/components/{id}`, `/api/v1/public/incidents`, `/api/v1/public/status/feed.rss`, `/api/v1/public/status/feed.atom`. Use `Cache-Control: public, max-age=30` header per contract. Add `X-Snapshot-Age-Seconds` and `X-Snapshot-Source` response headers.
- [X] T027 [US1] Wire the `status_page` router in `apps/control-plane/src/platform/main.py`: add `app.include_router(status_page_router)` after `incident_response_router` (line 1650 area). Append the public paths to `EXEMPT_PREFIXES` in `auth_middleware.py`: `frozenset({"/api/v1/public/"})`.
- [X] T028 [P] [US1] Build `apps/web-status/lib/status-client.ts` — fetches `/api/v1/public/status`; on network error, falls back to embedded `/last-known-good.json`; on stale (>5 min) emits a banner indicator.
- [X] T029 [P] [US1] Build `apps/web-status/lib/i18n.ts` — minimal 6-locale dictionary selected by `Accept-Language` header (research R12). Strings: page title, status labels (operational/degraded/partial_outage/full_outage/maintenance), "All systems operational", "Subscribe to updates", "Last updated", "30-day uptime".
- [X] T030 [US1] Implement `apps/web-status/app/page.tsx` overall status page — server-rendered shell + client-hydrated current state via `lib/status-client.ts`. Uses `<StatusBanner>` (T031), `<ComponentRow>` (T032). Pulls 30d uptime from snapshot.
- [X] T031 [P] [US1] Implement `apps/web-status/components/StatusBanner.tsx` with all five variants from data-model §1; severity = color + icon (Lucide) + text per FR-695-12. ARIA-live `polite` for state changes.
- [X] T032 [P] [US1] Implement `apps/web-status/components/ComponentRow.tsx` — per-component row with name, state dot, last-check timestamp (date-fns), 30d uptime %.
- [X] T033 [P] [US1] Implement `apps/web-status/components/IncidentTimeline.tsx` — sorted active + recently-resolved with severity badge.
- [X] T034 [US1] Implement `apps/web-status/app/components/[id]/page.tsx` — per-component detail page with 30-day history chart (use a small SVG chart; do NOT add Recharts to web-status dep-tree to keep bundle minimal).
- [X] T035 [US1] Implement `apps/web-status/app/history/page.tsx` — 30-day incident archive list (resolved incidents).
- [X] T036 [US1] Author `apps/web-status/public/last-known-good.json` placeholder bootstrap (operational state with empty arrays) — overwritten at runtime by the CronJob.
- [X] T037 [US1] Fill in `deploy/helm/platform/templates/web-status-deployment.yaml` — separate Deployment in `platform-edge` namespace, `replicaCount` from values, image from values, volumeMount for `last-known-good.json` (emptyDir shared with the CronJob OR ConfigMap projected), `securityContext.runAsNonRoot: true`, no service-account binding to platform secrets (Rule 49 independence).
- [X] T038 [US1] Fill in `deploy/helm/platform/templates/web-status-ingress.yaml` — separate Ingress for `{{ .Values.webStatus.host }}`, TLS via cert-manager annotations consistent with the existing `deploy/helm/platform/templates/ingress.yaml` pattern.
- [X] T039 [US1] Fill in `deploy/helm/platform/templates/status-snapshot-cronjob.yaml` — runs every 60s; calls an internal endpoint `/api/v1/internal/status_page/regenerate-fallback` (admin-token-gated) which writes the latest snapshot to the shared volume as `last-known-good.json`.
- [X] T040 [US1] Add internal admin route `POST /api/v1/internal/status_page/regenerate-fallback` to `apps/control-plane/src/platform/status_page/router.py` (admin role gate via `require_superadmin` per Rule 30). Idempotent; writes to S3-compatible bucket OR ConfigMap-volume mount per the deployment topology chosen in T037.
- [X] T041 [US1] Write CDN/Ingress cache headers config: `Cache-Control: public, max-age=30, must-revalidate` for status; `max-age=60` for incidents; `max-age=60` for feeds. Document in `apps/web-status/README.md`.
- [ ] T042 [US1] Run axe-core sweep on `apps/web-status/` pages (overall, per-component, history) — fail build on serious/critical violations (Rule 41).

**Checkpoint**: visitor can browse the public status page at `status.{env}.musematic.ai`; page survives main-app outage; axe-core AA passes.

---

## Phase 4: User Story 2 — Authenticated user sees a maintenance banner before and during a window (Priority: P1)

**Goal**: signed-in users see an info banner before scheduled maintenance, an upgraded warning banner during the window, disabled actions with tooltip, and a graceful `<MaintenanceBlockedAction>` modal on blocked write attempts.

**Independent Test**: schedule maintenance via admin → sign in → observe banner state machine across the window boundary; attempted write triggers modal not 503.

### Tests for US2

- [X] T043 [P] [US2] Vitest test `apps/web/__tests__/platform-status/PlatformStatusBanner.test.tsx` — renders all four maintenance variants per FR-695-11; severity uses color + icon + text; per-session dismiss; re-surface on next navigation.
- [X] T044 [P] [US2] Vitest test `apps/web/__tests__/platform-status/MaintenanceBlockedActionModal.test.tsx` — renders end-of-window time, retry-after CTA, no leaking 503 message.
- [X] T045 [P] [US2] Integration test `apps/control-plane/tests/integration/status_page/test_me_platform_status.py` — `/api/v1/me/platform-status` requires auth; returns user-affected-features map; reflects active maintenance window correctly.
- [X] T046 [P] [US2] Vitest test for `apps/web/lib/api.ts` 503 maintenance-envelope detection: triggers `MaintenanceBlockedError` on 503 with envelope shape; passes through other 503s as generic.

### Implementation for US2

- [X] T047 [US2] Implement `apps/control-plane/src/platform/status_page/me_router.py`: `GET /api/v1/me/platform-status` returns `MyPlatformStatus` per `contracts/authenticated-subscription-api.openapi.yaml`. Composes from current snapshot + the user's recent feature usage (best-effort heuristic from `analytics` BC if available; otherwise empty `affects_my_features`).
- [X] T048 [US2] Wire `me_router` in `apps/control-plane/src/platform/main.py` (after the public router include from T027).
- [X] T049 [US2] Implement `apps/web/lib/hooks/use-platform-status.ts` per `contracts/platform-status-ws.md` — TanStack Query against `/api/v1/me/platform-status` + `wsClient.subscribe('platform-status', onMessage)` invalidates the query on event. WS-disconnect → 30s polling fallback. Returns `{ data, isConnected, lastUpdatedAt }`.
- [X] T050 [US2] Implement `apps/web/components/features/platform-status/PlatformStatusBanner.tsx` — uses shadcn `<Alert>` primitive (`apps/web/components/ui/alert.tsx`); variants: `maintenance-scheduled` (info), `maintenance-in-progress` (warning), `incident-active` (warning|critical based on severity), `degraded-performance` (info). Severity = color (Tailwind) + icon (Lucide) + text label per FR-695-12. Dismiss button writes to `sessionStorage["platform-status-dismiss"]`.
- [X] T051 [US2] Implement `apps/web/components/features/platform-status/StatusIndicator.tsx` (shared with banner; duplicate of `apps/web-status/components/...` per R12).
- [X] T052 [US2] Implement `apps/web/components/features/platform-status/MaintenanceBlockedActionModal.tsx` — shadcn Dialog; reads window-end from a context provider; displays plain-language explanation; "Retry after X" button (disabled until window ends) and "Dismiss" button.
- [X] T053 [US2] Implement `apps/web/components/features/platform-status/MaintenanceModalProvider.tsx` — global subscriber to `MaintenanceBlockedError` thrown by `lib/api.ts`; mounts the modal once per page.
- [X] T054 [US2] Modify `apps/web/lib/api.ts` to detect 503 responses with the maintenance-envelope `{ code: "platform.maintenance.blocked", details: { window_end_at, ... } }` and throw `MaintenanceBlockedError`. Generic 503 still throws `ApiError` as today (no behavior change for non-maintenance).
- [X] T055 [US2] Modify `apps/web/app/(main)/layout.tsx` (line 51 area) to inject `<PlatformStatusBanner />` above `<Header />` and mount `<MaintenanceModalProvider />` once.
- [X] T056 [US2] Add maintenance-banner i18n keys to all 6 + 1 (ja) locales in `apps/web/messages/*.json`: `platformStatus.maintenanceScheduled`, `platformStatus.maintenanceInProgress`, `platformStatus.endsAt`, `platformStatus.dismiss`, `platformStatus.viewStatusPage`, `platformStatus.blockedActionTitle`, `platformStatus.blockedActionExplanation`.
- [ ] T057 [US2] Disabled-state audit: identify the canonical action button primitives (`apps/web/components/ui/button.tsx` or wrapper components in workbench pages) and add a `disabledByMaintenance` prop sourced from `usePlatformStatus()` + a tooltip citing `platformStatus.endsAt`. Apply on the top three writeable surfaces called out by spec (workflow trigger, agent invocation, scenario launch). Defer broader sweep to Polish phase if time-boxed.
- [X] T058 [US2] Wire WebSocket fan-out in `apps/control-plane/src/platform/ws_hub/router.py`: upon receipt of `multi_region_ops.events.maintenance_mode_enabled` / `_disabled`, broadcast `platform.maintenance.{started,ended}` envelope on the `platform-status` channel to all connected sessions.
- [ ] T059 [US2] Run axe-core sweep on `apps/web/app/(main)/home/` with the banner + modal forced on (test fixture); fail build on violations.

**Checkpoint**: maintenance banner state machine works end-to-end; blocked-action modal replaces silent 503s.

---

## Phase 5: User Story 3 — Authenticated user sees an incident banner with deep link to status (Priority: P1)

**Goal**: incident lifecycle is visible in-shell within ≤ 5s of severity change; banner deep-links to the public incident detail page.

**Independent Test**: trigger synthetic incident at warning → banner appears within 5s; click → land on public incident detail; resolve → banner disappears within 10s.

### Tests for US3

- [ ] T060 [P] [US3] Vitest test `apps/web/__tests__/platform-status/PlatformStatusBanner.incident.test.tsx` — incident severity warning|critical drives the variant; deep link points to public host (NOT admin); banner upgrades on severity change.
- [ ] T061 [P] [US3] Integration test `apps/control-plane/tests/integration/status_page/test_ws_incident_fanout.py` — opening a WS connection, triggering an `incident.triggered` Kafka event, asserts a `platform.incident.created` event is broadcast on the `platform-status` channel within 1s; resolution similarly.

### Implementation for US3

- [ ] T062 [US3] Extend `apps/web/components/features/platform-status/PlatformStatusBanner.tsx` (T050) with the `incident-active` variant: maps incident severity (`info`|`warning`|`high`|`critical`) → banner severity (`info`|`warning`|`warning`|`critical`); link target = `${webStatusHost}/incidents/${incident_id}` (env var injected via Next.js public runtime config).
- [ ] T063 [US3] Wire WebSocket fan-out in `apps/control-plane/src/platform/ws_hub/router.py`: on `incident_response.events.incident.triggered/.updated/.resolved` consumption, broadcast `platform.incident.{created,updated,resolved}` per `contracts/platform-status-ws.md` payload to the `platform-status` channel.
- [ ] T064 [US3] Add incident-banner i18n keys: `platformStatus.incidentActive`, `platformStatus.incidentSeverity.{info,warning,high,critical}`, `platformStatus.viewIncident`. Apply across all 6+1 locales.

**Checkpoint**: severity changes propagate within 5s p95; deep-links land on public surface (not admin).

---

## Phase 6: User Story 4 — Customer subscribes to platform incident updates (Priority: P2)

**Goal**: anonymous-visitor email/webhook/Slack/RSS/Atom subscriptions; HMAC-signed webhooks; confirm-opt-in for email; unsubscribe links.

**Independent Test**: subscribe via email on public page → confirm via link → trigger incident → email arrives within 2 minutes; resolve → resolution email arrives; verify RSS/Atom updates in 60s; verify webhook delivery is HMAC-signed.

### Tests for US4

- [ ] T065 [P] [US4] Integration test `apps/control-plane/tests/integration/status_page/test_subscription_flow.py::test_email_confirm_opt_in` — POST email → 202 anti-enumeration; subscription row in `pending`; click confirmation link → row in `healthy`; trigger incident → `subscription_dispatches` row created.
- [ ] T066 [P] [US4] Integration test for webhook subscription: POST URL → 202; immediate test ping delivered with correct HMAC signature header (verifies via `notifications/deliverers/webhook_deliverer.py:43-89` reuse); subscription `healthy` only on 2xx test ping. Persistent failures land in `webhook_deliveries.status='dead_letter'`.
- [ ] T067 [P] [US4] Unit test `apps/control-plane/tests/unit/status_page/test_service.py::test_dispatch_fanout` — given an `incident.triggered` event and N subscriptions with overlapping scope filters, assert exactly the matching subset gets a dispatch row.
- [ ] T068 [P] [US4] Vitest test `apps/web-status/components/SubscribeForm.test.tsx` — RHF + Zod email validation; submit → 202 → success message (anti-enumeration; never confirms whether email exists).

### Implementation for US4

- [ ] T069 [US4] Implement remaining `apps/control-plane/src/platform/status_page/service.py` methods (~140 of the ~220 LOC): `submit_email_subscription(email, scope)` (creates `pending` row + sends confirm email), `confirm_email_subscription(token)`, `unsubscribe(token)`, `submit_webhook_subscription(url, scope, contact_email)` (creates `OutboundWebhook` row tied via `webhook_id` to a new `status_subscriptions` row, scope_components → `event_types` mapping), `submit_slack_subscription(webhook_url, scope)`, `dispatch_event(event_kind, payload)` (fans out to all matching `confirmed_at IS NOT NULL && health='healthy'` subscriptions).
- [ ] T070 [US4] Implement confirmation-token generation: `secrets.token_urlsafe(32)` → SHA-256 → store hash; raw token sent in confirmation email/webhook test. Unsubscribe tokens are scoped per-subscription, generated on subscribe, persisted hashed (separate column or reuse same `confirmation_token_hash` for both — prefer two columns: `confirmation_token_hash` and `unsubscribe_token_hash`; update T010 model + T006 migration if needed).
- [ ] T071 [US4] Add Redis rate-limit logic in `apps/control-plane/src/platform/status_page/dependencies.py`: sliding-window counter `status:subscribe:rate:{ip}` (5 req/min default, 10 burst) per `plan.md` Storage table.
- [ ] T072 [US4] Implement `apps/control-plane/src/platform/status_page/router.py` POST/GET endpoints: `POST /api/v1/public/subscribe/email`, `GET /api/v1/public/subscribe/email/confirm`, `GET /api/v1/public/subscribe/email/unsubscribe`, `POST /api/v1/public/subscribe/webhook`, `POST /api/v1/public/subscribe/slack`. Per-IP rate limit dependency wired.
- [ ] T073 [US4] Subscribe `status_page.dispatch_event` to the in-process Kafka consumer that already fires from T024: every consumed `incident.triggered/.updated/.resolved` and `maintenance.{enabled,disabled}` triggers `dispatch_event` with the appropriate `event_kind`. Reuses `notifications/deliverers/webhook_deliverer.send_signed()` for the `webhook` channel.
- [ ] T074 [US4] Extend `apps/control-plane/src/platform/notifications/webhooks_service.py` allowed-event-types to include the status-page kinds: `incident.created`, `incident.updated`, `incident.resolved`, `maintenance.scheduled`, `maintenance.started`, `maintenance.ended`, `component.degraded`, `component.recovered`. Validation should accept these in `OutboundWebhook.event_types` array.
- [ ] T075 [US4] Implement email transport for confirmation + lifecycle notifications: reuse the existing `notifications/email/` sender (find via repo grep at task time). Email templates live under `apps/control-plane/src/platform/status_page/email_templates/`: `confirm_subscription.txt`/`.html`, `incident_created.{txt,html}`, `incident_updated.{txt,html}`, `incident_resolved.{txt,html}`, `maintenance_scheduled.{txt,html}`, `maintenance_started.{txt,html}`, `maintenance_ended.{txt,html}`, `unsubscribed.{txt,html}`. Every email includes the unsubscribe link (FR-695-24).
- [ ] T076 [US4] Implement bounce handling: extend `notifications/email/` bounce hook (or — if absent — flag a follow-up TODO) to mark `status_subscriptions.health='unhealthy'` on hard bounce (per spec edge case + FR-695-23 dead-letter pattern). Until bounce hook is wired, document the manual remediation in `quickstart.md`.
- [ ] T077 [US4] Implement `apps/web-status/app/subscribe/page.tsx` — form for email/webhook/Slack subscription with scope-component multiselect; uses `<SubscribeForm>` (T078).
- [ ] T078 [P] [US4] Implement `apps/web-status/components/SubscribeForm.tsx` — RHF + Zod; channel discriminated union; submits to `/api/v1/public/subscribe/{email|webhook|slack}`; renders an anti-enumeration confirmation regardless of whether the email already exists.
- [ ] T079 [US4] Implement `apps/web-status/app/subscribe/confirm/page.tsx` (handles `?token=...` query param via client component, calls `GET /api/v1/public/subscribe/email/confirm`, renders success/expired/invalid states).
- [ ] T080 [US4] Implement `apps/web-status/app/unsubscribe/page.tsx` (similar; handles unsubscribe token).
- [ ] T081 [US4] Display the RSS + Atom feed URLs prominently on `apps/web-status/app/page.tsx` and `subscribe/page.tsx` (visitors copy/paste into their reader; no backend interaction needed).

**Checkpoint**: full subscription stack works; HMAC webhooks delivered; confirmation flow audit-logged.

---

## Phase 7: User Story 5 — Authenticated user manages their own status subscriptions (Priority: P2)

**Goal**: signed-in users add/edit/remove their subscriptions at `/settings/status-subscriptions` (Rule 45 / Rule 46).

**Independent Test**: navigate to `/settings/status-subscriptions` → list current subs → add webhook → save → test ping delivered → remove sub → verify no further dispatch.

### Tests for US5

- [ ] T082 [P] [US5] Integration test `apps/control-plane/tests/integration/status_page/test_me_subscriptions.py` — `/api/v1/me/status-subscriptions` GET/POST/PATCH/DELETE; cross-user attempts return 403 (Rule 46); creating a webhook subscription delivers a test ping; deletion stops further dispatch.
- [ ] T083 [P] [US5] Vitest test `apps/web/__tests__/settings/status-subscriptions.test.tsx` — list/add/edit/remove flows; optimistic update; error rollback.

### Implementation for US5

- [ ] T084 [US5] Implement `apps/control-plane/src/platform/status_page/me_router.py` subscription endpoints per `contracts/authenticated-subscription-api.openapi.yaml`: `GET/POST/PATCH/DELETE /api/v1/me/status-subscriptions[/{id}]`. Self-scoped (Rule 46) — no `user_id` param, always uses authenticated principal. Audit-chain entries on every mutation (Rule 9).
- [ ] T085 [US5] Implement `apps/web/app/(main)/settings/status-subscriptions/page.tsx` — page shell + list + add-subscription dialog.
- [ ] T086 [P] [US5] Implement `apps/web/components/features/platform-status/StatusSubscriptionList.tsx` — TanStack Table with channel, scope, health, confirmed-at columns; remove action with confirm dialog.
- [ ] T087 [P] [US5] Implement `apps/web/components/features/platform-status/AddSubscriptionForm.tsx` — RHF + Zod; channel discriminated union; submits to `/api/v1/me/status-subscriptions`; for webhook channel displays the test-ping verification state.
- [ ] T088 [US5] Add settings-subscriptions i18n keys to all 6+1 locales: `platformStatus.subscriptions.title`, `.add`, `.empty`, `.channelEmail`, `.channelWebhook`, `.channelSlack`, `.scope.allComponents`, `.scope.specificComponents`, `.health.{pending,healthy,unhealthy,unsubscribed}`, `.removeConfirm`.

**Checkpoint**: authenticated subscription mgmt page passes axe-core AA; cross-user attempts blocked by 403.

---

## Phase 8: User Story 6 — Evaluator authors a reusable simulation scenario, runs it, and inspects digital-twin divergence (Priority: P2)

**Goal**: scenario library + editor; launch with N iterations; digital-twin panel on run detail.

**Independent Test**: navigate to `/evaluation-testing/simulations/scenarios/new` → save → launch with N=10 → 10 runs queued → open any run → digital-twin panel renders divergence summary or "no reference available".

### Tests for US6

- [ ] T089 [P] [US6] Unit test `apps/control-plane/tests/unit/simulation/test_scenarios_service.py` — validation: plaintext-secret rejection, unknown FQN rejection, forbidden twin combo rejection, success_criteria empty-array rejection. ≥ 14 cases.
- [ ] T090 [P] [US6] Integration test `apps/control-plane/tests/integration/simulation/test_scenario_endpoints.py` — full CRUD; archive (soft-delete); `/run` queues N `simulation_runs` rows linked via `scenario_id`.
- [ ] T091 [P] [US6] Vitest test `apps/web/__tests__/simulations/SimulationScenarioEditor.test.tsx` — RHF + Zod validation, mock-LLM default, real-LLM opt-in via `<RealLLMOptInDialog>`.
- [ ] T092 [P] [US6] Vitest test `apps/web/__tests__/simulations/DigitalTwinPanel.test.tsx` — renders mock vs real lists, divergence highlights; "no reference available" empty state.

### Implementation for US6

- [ ] T093 [US6] Extend `apps/control-plane/src/platform/simulation/models.py` — add `SimulationScenario` model + `scenario_id` FK on `SimulationRun` matching migration 095 (T006).
- [ ] T094 [US6] Extend `apps/control-plane/src/platform/simulation/schemas.py` — add `ScenarioCreate`, `ScenarioUpdate`, `ScenarioRead`, `ScenarioRunRequest`, `ScenarioRunSummary` Pydantic schemas matching `contracts/simulation-scenarios-api.openapi.yaml`.
- [ ] T095 [US6] Implement `apps/control-plane/src/platform/simulation/scenarios_service.py` (~180 LOC) — CRUD; validation per data-model §4 rules (#1 plaintext-secret regex via `security_compliance/` patterns; #2 FQN existence via `registry/` service; #3 workflow approval via `workflows/` service; #4 forbidden twin combos; #5 non-empty `success_criteria`). `launch_scenario(scenario_id, iterations, use_real_llm, confirmation_token)` queues N `simulation_runs` rows via the existing `simulation_controller` gRPC client.
- [ ] T096 [US6] Extend `apps/control-plane/src/platform/simulation/router.py` — add 5 new routes per the contract: `GET/POST /scenarios`, `GET/PUT/DELETE /scenarios/{id}`, `POST /scenarios/{id}/run`. Workspace-scoped (Rule 47); 422 on validation failures with detail payload.
- [ ] T097 [US6] Implement `apps/web/lib/hooks/use-simulation-scenarios.ts` — TanStack Query hooks: `useScenarios(workspaceId)`, `useScenario(id)`, `useCreateScenario()`, `useUpdateScenario(id)`, `useArchiveScenario(id)`, `useRunScenario(id)`.
- [ ] T098 [US6] Implement `apps/web/lib/hooks/use-digital-twin.ts` — TanStack Query against `GET /api/v1/simulations/{run_id}` + the existing `GET /api/v1/simulations/comparisons/{report_id}` to compose `DigitalTwinDivergenceReport` per data-model §6.
- [ ] T099 [US6] Implement `apps/web/components/features/simulations/SimulationScenarioEditor.tsx` (~500 LOC) — full RHF + Zod editor with sections: Identity (name/description), Agents (FQN multiselect), Workflow Template (optional), Mock Set (default = mock-LLM provider per Rule 50; tool-mock declarations), Input Distribution (uniform/normal/categorical/fixed), Twin Fidelity (per-subsystem mock vs real), Success Criteria (assertions array), Run Schedule (optional). Inline JSON schema validation. Real-LLM preview opt-in via the moved `<RealLLMOptInDialog>` from T015.
- [ ] T100 [P] [US6] Implement `apps/web/components/features/simulations/ScenarioLibraryTable.tsx` — TanStack Table with name, description, last-run state, archived-at; row actions: open, edit, archive, launch.
- [ ] T101 [P] [US6] Implement `apps/web/components/features/simulations/ScenarioRunDialog.tsx` — N-iterations confirmation; capacity warning if N > workspace cap; surfaces `<RealLLMOptInDialog>` if "use real LLM" toggled.
- [ ] T102 [US6] Implement `apps/web/app/(main)/evaluation-testing/simulations/scenarios/page.tsx` — library page; uses `ScenarioLibraryTable`; "New scenario" button.
- [ ] T103 [US6] Implement `apps/web/app/(main)/evaluation-testing/simulations/scenarios/new/page.tsx` — wraps `<SimulationScenarioEditor mode="create" />`.
- [ ] T104 [US6] Implement `apps/web/app/(main)/evaluation-testing/simulations/scenarios/[id]/page.tsx` — wraps `<SimulationScenarioEditor mode="edit" scenarioId={id} />` + recent-runs list; launch button mounts `<ScenarioRunDialog>`.
- [ ] T105 [US6] Implement `apps/web/components/features/simulations/DigitalTwinPanel.tsx` — mock vs real component list, divergence-points list (highlighted), simulated vs wall-clock time, link to ref-prod-execution if `reference_available`; explicit "no reference available" empty state.
- [ ] T106 [US6] Modify `apps/web/app/(main)/evaluation-testing/simulations/[runId]/page.tsx` — embed `<DigitalTwinPanel runId={runId} />` as a new tab/section; existing run detail content unchanged.
- [ ] T107 [US6] Add simulation-scenarios + digital-twin i18n keys to all 6+1 locales: `simulations.scenarios.title`, `.new`, `.empty`, `.fields.{name,description,agents,workflowTemplate,mockSet,inputDistribution,twinFidelity,successCriteria,runSchedule}`, `.validation.{plaintextSecret,unknownFqn,forbiddenTwinCombo,emptySuccessCriteria}`, `.run.iterations`, `.run.useRealLlm`, `.digitalTwin.title`, `.digitalTwin.mockComponents`, `.digitalTwin.realComponents`, `.digitalTwin.divergencePoints`, `.digitalTwin.simulatedVsWallClock`, `.digitalTwin.referenceProdExecution`, `.digitalTwin.noReferenceAvailable`.
- [ ] T108 [US6] Run axe-core sweep on the three new scenario pages + the extended run detail page.

**Checkpoint**: scenario CRUD + launch works; digital-twin panel renders for runs with and without ref-prod-execution.

---

## Phase 9: User Story 7 — Research scientist completes the discovery workbench loop (Priority: P3)

**Goal**: tabbed session detail with hypotheses library, experiment launcher, evidence inspector. Existing network view reused unchanged.

**Independent Test**: open `/discovery/{session_id}` → tabs render → filter hypotheses → open detail → launch experiment → open evidence → click source link.

### Tests for US7

- [ ] T109 [P] [US7] Vitest test `apps/web/__tests__/discovery/HypothesisFilterBar.test.tsx` — filter by state and confidence tier; sort by ranking.
- [ ] T110 [P] [US7] Vitest test `apps/web/__tests__/discovery/ExperimentLauncherForm.test.tsx` — RHF + Zod against the existing experiment endpoint contract; submit calls `POST /api/v1/discovery/hypotheses/{id}/experiment`.
- [ ] T111 [P] [US7] Vitest test `apps/web/__tests__/discovery/EvidenceInspectorView.test.tsx` — renders source links; deep-link param routing works.

### Implementation for US7

- [ ] T112 [US7] Implement `apps/web/lib/hooks/use-discovery-session.ts` — TanStack Query hooks for `GET /api/v1/discovery/sessions/{id}`, `/hypotheses`, `/experiments`. Reuses existing endpoints (no backend changes).
- [ ] T113 [US7] Implement `apps/web/lib/hooks/use-discovery-evidence.ts` — TanStack Query for `GET /api/v1/discovery/hypotheses/{id}/critiques` (evidence equivalent) and any related-source endpoint discovered at task time.
- [ ] T114 [US7] Implement `apps/web/components/features/discovery/HypothesisCard.tsx` — card with title, state badge, confidence tier, novelty score, evidence-count badge.
- [ ] T115 [P] [US7] Implement `apps/web/components/features/discovery/HypothesisFilterBar.tsx` — state filter (proposed/testing/confirmed/refuted), confidence tier filter, sort selector.
- [ ] T116 [P] [US7] Implement `apps/web/components/features/discovery/HypothesisDetailPanel.tsx` — evidence pointers list, related hypotheses list, "Launch experiment" CTA.
- [ ] T117 [P] [US7] Implement `apps/web/components/features/discovery/ExperimentLauncherForm.tsx` — RHF + Zod; targets `POST /api/v1/discovery/hypotheses/{hypothesis_id}/experiment` with the existing payload shape (verify shape against `apps/control-plane/src/platform/discovery/router.py:219-232` at task time).
- [ ] T118 [P] [US7] Implement `apps/web/components/features/discovery/EvidenceInspectorView.tsx` — renders evidence detail with source links (back to originating execution, dataset, or critique); deep-link navigation.
- [ ] T119 [US7] Implement `apps/web/app/(main)/discovery/[session_id]/page.tsx` — session detail with shadcn Tabs (`overview`, `hypotheses`, `experiments`, `evidence`, `network`); each tab routes to its dedicated page or renders inline. The `network` tab renders the existing `apps/web/app/(main)/discovery/[session_id]/network/page.tsx` content via dynamic import (NO rewrite of `<HypothesisNetworkGraph>` per FR-695-45).
- [ ] T120 [US7] Implement `apps/web/app/(main)/discovery/[session_id]/hypotheses/page.tsx` — library list using `<HypothesisCard>` + `<HypothesisFilterBar>`; URL-param state for filters.
- [ ] T121 [US7] Implement `apps/web/app/(main)/discovery/[session_id]/experiments/page.tsx` — experiments list (queries existing `GET /api/v1/discovery/experiments/{id}` per item OR a new lightweight list endpoint if missing — verify at task time and either add a backend endpoint OR derive from session).
- [ ] T122 [US7] Implement `apps/web/app/(main)/discovery/[session_id]/experiments/new/page.tsx` — wraps `<ExperimentLauncherForm>`.
- [ ] T123 [US7] Implement `apps/web/app/(main)/discovery/[session_id]/evidence/[evidence_id]/page.tsx` — wraps `<EvidenceInspectorView>`.
- [ ] T124 [US7] Add discovery i18n keys to all 6+1 locales: `discovery.session.{tabs.overview,tabs.hypotheses,tabs.experiments,tabs.evidence,tabs.network}`, `discovery.hypotheses.{title,filter,empty,confidenceTier,state.{proposed,testing,confirmed,refuted}}`, `discovery.experiments.{title,launch,running,completed}`, `discovery.evidence.{title,sources,unavailable}`.
- [ ] T125 [US7] Run axe-core sweep on the five new discovery pages.

**Checkpoint**: full discovery loop works frontend-only; existing network view unchanged.

---

## Phase 10: User Story 8 — E2E coverage protects the visibility layer (Priority: P2)

**Goal**: J21 Platform State, J07 Evaluator, J09 Scientific Discovery journeys pass; new BC suites pass; no regression in J01/J02/J03/J04/J10.

**Independent Test**: `pytest tests/e2e/journeys/test_j21_platform_state.py` etc. all green.

### Bootstrap

- [ ] T126 If `tests/e2e/journeys/` and `tests/e2e/suites/` directories do not yet exist on `main`, bootstrap them: create `tests/e2e/conftest.py` with `db`, `kafka_consumer`, `http_client`, `kind_cluster` fixtures (mirror feature 071's pattern if available; otherwise minimal fixtures using `httpx` + `aiokafka` + `asyncpg` per the constitutional Rule 26 "no mocking observability backends"). Create `tests/e2e/pyproject.toml` with pytest 8 + pytest-asyncio + pytest-html + pytest-timeout. Add Make targets `make e2e-up` / `make e2e-test` mirroring existing patterns.
- [ ] T127 If `/api/v1/_e2e/incidents/trigger` and `/api/v1/_e2e/incidents/resolve` dev-only endpoints (gated by `FEATURE_E2E_MODE`) do not exist, add them under `apps/control-plane/src/platform/incident_response/router.py` (or a dedicated `_e2e/` prefix per Rule 26 "Dev-only seeding/chaos endpoints live under `/api/v1/_e2e/*`"). Both return 404 in production.

### Journey J21 Platform State

- [ ] T128 [P] [US8] Implement `tests/e2e/journeys/test_j21_platform_state.py` — full visibility loop: subscribe (email + RSS) → trigger synthetic incident → assert public status reflects within 60s (poll `GET /api/v1/public/status`) → assert in-shell banner appears (open authenticated browser context, assert banner) → assert subscriber email in dev-MinIO bucket within 2 min → assert RSS feed item present → resolve → assert all surfaces clear within 10s.
- [ ] T129 [P] [US8] Implement `tests/e2e/suites/platform_state/test_public_status_page.py` — Playwright AA smoke test of `apps/web-status/` (overall, per-component, history pages); axe-core assertions.
- [ ] T130 [P] [US8] Implement `tests/e2e/suites/platform_state/test_status_banner_rendering.py` — banner state-machine across maintenance scheduled → started → ended (Playwright in authenticated context).
- [ ] T131 [P] [US8] Implement `tests/e2e/suites/platform_state/test_maintenance_mode_ux.py` — write attempt during maintenance → modal appears (NOT 503 page); read continues to work.
- [ ] T132 [P] [US8] Implement `tests/e2e/suites/platform_state/test_email_subscription.py` — confirm-opt-in flow; unsubscribe link works.
- [ ] T133 [P] [US8] Implement `tests/e2e/suites/platform_state/test_rss_feed.py` — feed validity (parsed by `feedparser`); incident lifecycle reflected within 60s.
- [ ] T134 [P] [US8] Implement `tests/e2e/suites/platform_state/test_webhook_subscription.py` — webhook test ping has correct HMAC signature; persistent failures dead-letter; replay possible.

### Journey J07 Evaluator

- [ ] T135 [P] [US8] Implement `tests/e2e/journeys/test_j07_evaluator.py` — Playwright: log in as evaluator → navigate to scenarios library → create new scenario → save → launch with N=2 iterations → 2 runs queued → open run detail → digital-twin panel asserts mock vs real list and divergence summary.
- [ ] T136 [P] [US8] Implement `tests/e2e/suites/simulation_ui/test_scenario_editor.py` — validation surfaces inline; plaintext-secret rejection produces a clear error; real-LLM toggle requires the `<RealLLMOptInDialog>` text confirmation.
- [ ] T137 [P] [US8] Implement `tests/e2e/suites/simulation_ui/test_digital_twin_panel.py` — explicit "no reference available" state when ref-prod-execution missing.

### Journey J09 Scientific Discovery

- [ ] T138 [P] [US8] Implement `tests/e2e/journeys/test_j09_scientific_discovery.py` — Playwright: log in as research scientist → open session → navigate to hypotheses tab → filter → open hypothesis detail → launch experiment → assert experiment runs → open evidence inspector → click source link.
- [ ] T139 [P] [US8] Implement `tests/e2e/suites/discovery_ui/test_session_detail.py` — tabs render, deep links to each tab work, `/network/` reuses existing graph.
- [ ] T140 [P] [US8] Implement `tests/e2e/suites/discovery_ui/test_hypothesis_library.py` — filter + sort interactions; pagination/empty states.
- [ ] T141 [P] [US8] Implement `tests/e2e/suites/discovery_ui/test_experiment_launcher.py` — form submission triggers backend POST; success state displays returned experiment id.
- [ ] T142 [P] [US8] Implement `tests/e2e/suites/discovery_ui/test_evidence_inspector.py` — source links functional; deleted-source explicit "source unavailable" state.

### Regression sentinels

- [ ] T143 [US8] Run the existing journey set (J01, J02, J03, J04, J10) to confirm no regression introduced by Track A/B/C work; flag any failure as a regression blocker before merge.

**Checkpoint**: J21 + J07 + J09 + 13 suite tests + 5 existing journeys all green.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: i18n parity, observability, audit-chain audit, docs, dashboard, perf.

- [ ] T144 [P] Run `apps/web/scripts/i18n-check.*` (or equivalent) — verify all UPD-045 namespaces have parity across en, es, de, fr, it, zh-CN; log Italian + non-English strings still using English fallbacks for the localisation team backlog.
- [ ] T145 Disabled-state sweep across remaining write surfaces beyond T057's top-three (workflow editor, agent management, marketplace publish, fleet ops, etc.) — apply `disabledByMaintenance` consistently.
- [ ] T146 [P] Author Grafana dashboard JSON `deploy/helm/observability/templates/dashboards/status_page.json` per Rule 24/27 — panels: snapshot regen latency p50/p95, subscription dispatch latency p95, RSS/Atom freshness, public-status request rate + 4xx/5xx + cache-hit-ratio, dead-letter webhook depth.
- [ ] T147 [P] Audit-chain entry verification: write `apps/control-plane/tests/integration/status_page/test_audit_chain.py` asserting subscription-confirm, unsubscribe, webhook-rotation, admin manual-snapshot-override emit audit-chain entries via `audit_chain_service.py` (Rule 9).
- [ ] T148 [P] Verify Rule 31 — no `PLATFORM_SUPERADMIN_PASSWORD`-style log fields in any new logging path. Lint pass + manual code review.
- [ ] T149 [P] Verify Rule 22 / Rule 40 — no `workspace_id`, `user_id`, `goal_id`, or subscriber `email` in Loki labels. All such fields appear in JSON payload only.
- [ ] T150 Run perf checks: SC-001 (p95 ≤ 2s on apps/web-status/ from cold cache), SC-002 (banner ≤ 5s p95 via WS), SC-003 (subscription dispatch ≤ 2 min, RSS/Atom ≤ 60s), SC-013 (10× burst with no origin degradation — use `vegeta` or repo's existing perf harness).
- [ ] T151 Update `docs/functional-requirements-revised-v6.md` cross-references — link FR-675…FR-682 anchor IDs to feature 095 spec.md (per Rule 36 "every new FR with UX impact must be documented"). Run the docs CI gate (`docs:check`) to validate.
- [ ] T152 Update `docs/system-architecture.md` §14 (digital twins) to reference the new `<DigitalTwinPanel>` UI surface; cross-link the public-status topology in the relevant operational section.
- [ ] T153 Run `pnpm build` and `pnpm typecheck` in both `apps/web/` and `apps/web-status/`; resolve any TS strictness regressions.
- [ ] T154 Verify Helm chart with `helm lint` + `kubeconform` per Rule 9 release-gate; render with realistic `webStatus.enabled=true` values overlay.
- [ ] T155 Run the full quickstart.md walkthrough end-to-end on a clean dev cluster; capture any drift from the documented steps and patch quickstart in-place.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)** — start immediately; no deps.
- **Phase 2 (Foundational)** — depends on Phase 1; **BLOCKS all user-story phases**.
- **Phase 3–9 (US1–US7)** — depend on Phase 2 only. Once Phase 2 checkpoints, US1, US2, US3, US4, US5, US6, US7 can proceed in parallel by separate developers.
- **Phase 10 (US8 — E2E)** — depends on its target user stories landing. J21 needs US1+US2+US3+US4 in place; J07 needs US6; J09 needs US7. Bootstrap (T126/T127) can land independently.
- **Phase 11 (Polish)** — depends on the user-story phases the polish item references.

### Cross-story dependencies (intentionally minimised)

- **US3 ⇢ US2**: US3 extends the same `<PlatformStatusBanner>` introduced by US2 (T050). If US3 lands first, it owns banner creation and US2 only adds the maintenance variants — adjust task ownership accordingly at PR time.
- **US5 ⇢ US4**: US5's authenticated subscription-mgmt page lists subscriptions that US4 created. Either order works (US5 can list zero rows initially).
- **US6 ⇢ T015 (Foundational)**: scenario editor depends on the moved `<RealLLMOptInDialog>`.
- **US7 ⇢ existing discovery backend** — none on this feature.

### Within each user-story phase

- Tests authored before or alongside implementation (per Brownfield Rule 3).
- Models → repository → service → router → frontend hooks → frontend components → pages.
- Story checkpoint runs the story's independent test before moving on.

### Parallel opportunities

- All `[P]` tasks within the same phase can run in parallel.
- Setup T002/T003/T004 are mutually independent.
- Foundational T008/T009 [P], T011/T012 [P], T013/T014 (sequenced — T013 must precede T014), T016/T017 [P].
- US1 implementation tasks T028/T029, T031/T032/T033 are mutually independent.
- US2 implementation: T050/T051/T052/T053 are mutually independent (different files).
- E2E suite tests within Phase 10 are all [P].

---

## Parallel Execution Examples

### Phase 2 (Foundational) — kick off simultaneously

```bash
# Two developers can work in parallel on Foundational
Task: "T008 [P] Scaffold status_page BC files"
Task: "T011 [P] Extend ws_hub ChannelType"
Task: "T012 [P] Extend WsChannel union (apps/web)"
Task: "T016 [P] Add webStatus block to values.yaml"
Task: "T017 [P] Create empty Helm template files"
# T013 (it.json) sequences before T014 (UPD-045 i18n keys)
```

### Phase 3 (US1) — split across two developers

```bash
# Backend dev:
T022 → T023 → T024 → T025 → T026 → T027 → T040
T018 [P] (unit test) || T019 [P] (feed test) || T020 [P] (integration)

# Frontend dev:
T028 [P] || T029 [P] || T030 || T031 [P] || T032 [P] || T033 [P] → T034 → T035
T021 [P] (Vitest)

# Helm dev:
T037 → T038 → T039 → T041
```

### Phase 10 (US8 — E2E) — fan out

```bash
# Once T126+T127 land, all suite tests are [P]:
Task: "T128 — J21 journey"
Task: "T129 — public status page suite"
Task: "T130 — banner rendering suite"
Task: "T135 — J07 journey"
Task: "T138 — J09 journey"
# ... and so on (T131–T142 all [P])
```

---

## Implementation Strategy

### MVP First

The smallest demonstrable increment is US1 (P1) alone — visitor-facing public status surface delivers Rule 49 + visibility outside the app. Sequence:

1. Phase 1 (Setup)
2. Phase 2 (Foundational, partial — T006/T007/T008/T009/T010 + T011 if WS desired later)
3. Phase 3 (US1)
4. Stop & validate against quickstart §1, §2, §4
5. Demo

### Incremental Delivery

After MVP:

1. + US2 (in-shell maintenance banner) — Rule 48 first half
2. + US3 (incident banner) — Rule 48 second half; same banner primitive, low cost
3. + US4 (anonymous subscriptions) — closes FR-678 / Rule 17 surface
4. + US5 (authenticated subscription mgmt) — Rule 45 closure for subscriptions
5. + US6 (scenario editor + digital-twin panel) — FR-679/680 closure
6. + US7 (discovery workbench completion) — FR-681 closure
7. + US8 (E2E coverage) — FR-682 closure; runs as a release gate
8. Polish phase

### Parallel Team Strategy

With three developers post-Foundational:

- **Dev A** (backend lean): US1 backend → US4 (subscription engine + RSS/Atom + dispatch) → US5 (`/api/v1/me/...`)
- **Dev B** (frontend lean): US1 web-status site → US2 banner → US3 incident variant → US5 frontend page
- **Dev C** (workbench lean): US6 (scenario editor + digital-twin panel) → US7 (discovery completion) → starts E2E (US8) bootstrap once US1+US2 land

E2E (US8) tasks parallelise across all three devs in Phase 10.

---

## Notes

- `[P]` tasks edit different files with no incomplete-task deps — safe for parallel agent execution.
- `[Story]` label maps task to spec.md user story for traceability.
- Every story is independently testable; checkpoints in each phase enforce that.
- Brownfield Rule 3: new code MUST include tests. Test tasks land alongside implementation, not at the end.
- Brownfield Rule 5: every spec/plan cites exact files and functions — preserved in this task list.
- Commit cadence: commit after each task or each cohesive `[P]` cohort.
- Avoid: cross-story file conflicts (the file inventory in `plan.md` keeps US1's files distinct from US6's).
- The `<RealLLMOptInDialog>` move in T015 is intentionally Foundational so both US6 and any future user-story consumers reference the canonical shared path.
