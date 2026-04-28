# Feature Specification: Public Status Page, Platform State Banner, and Remaining Workbench UIs

**Feature Branch**: `095-public-status-banner-workbench-uis`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: UPD-045 — User-visible platform state surfaces (independent public status page, in-app `<PlatformStatusBanner>`, maintenance-mode graceful UX, incident subscription) plus completion of the simulation and scientific-discovery workbench UIs (scenario editor, digital-twin panel, hypothesis library, experiment launcher, evidence inspector).

---

## Brownfield Reconciliations *(authored from verified repo research, 2026-04-28)*

The brownfield input is mostly accurate but contains the following reconciliations that this spec preserves verbatim because they shape downstream planning. Each item below cites the verified source.

1. **Section 118 IS canonical.** The brownfield input's "FRs: FR-675 through FR-682 (section 118)" claim is correct. `docs/functional-requirements-revised-v6.md:3594` heads "## 118. Public Status Page, Maintenance Banner, and User-Visible Platform State" and FR-675 → FR-682 follow at lines 3596–3618.

2. **Constitutional anchors exist as Rules 48–49.** `.specify/memory/constitution.md:274-281` defines: Rule 48 "Platform state is user-visible" and Rule 49 "Public status page is operationally independent" — both directly load-bearing. Rule 45 (every backend capability has UI) at line 258 also applies. These anchors are stronger than the input frames them.

3. **Maintenance backend already emits a public read endpoint.** `apps/control-plane/src/platform/multi_region_ops/router.py:438-442` already exposes `GET /api/v1/maintenance/status-banner` *without* auth. The input's "no in-app platform status banner" gap is correct for the UI surface, but the backend signal already exists. The new public-status backend will compose with this endpoint, not replace it.

4. **Maintenance Kafka events exist.** `maintenance.mode.enabled` and `maintenance.mode.disabled` are already emitted (constitution `:771-772`). What is missing is the **WebSocket fan-out channel** so the in-shell banner can refresh in real time without polling. This spec treats the WS channel as the new in-band requirement, not the Kafka events.

5. **Incident subscription is greenfield in this codebase.** `apps/control-plane/src/platform/incident_response/router.py` exposes incident CRUD (`/api/v1/incidents`, `/api/v1/admin/incidents/integrations/*`), but no subscribe/email/RSS/webhook surfaces. The input's framing as "extends UPD-031" is correct; concretely, every subscription endpoint is net-new.

6. **Discovery backend supports everything FR-681 needs.** `apps/control-plane/src/platform/discovery/router.py` already exposes session CRUD, `GET /sessions/{id}/hypotheses`, `POST /hypotheses/{hypothesis_id}/experiment`, `POST /experiments/{id}/execute`, `GET /experiments/{id}`, `GET /hypotheses/{id}/critiques`. The input's discovery backend additions are NOT new; this spec is **frontend-only on the discovery side** plus an evidence-detail confirm-shape pass.

7. **Simulation backend already has digital-twin endpoints.** `POST /twins`, `GET /twins/{id}`, `GET /twins/{id}/versions`, `POST /twins/{id}/predict`, `POST /{run_id}/compare` already exist. The spec adds **scenario CRUD** (`/api/v1/simulations/scenarios`) and the **scenario-run trigger** as net-new backend; the digital-twin panel is **frontend-only** on top of existing endpoints.

8. **The graph library is XYFlow + Dagre, not Cytoscape.** `apps/web/components/features/discovery/HypothesisNetworkGraph.tsx` already implements the network view with `@xyflow/react ^12.10.2` + `@dagrejs/dagre ^3.0.0` (per `apps/web/package.json`). The input's "`<HypothesisGraph>` reusing existing Cytoscape integration" is incorrect — the canonical primitive is XYFlow and `<HypothesisGraph>` (if introduced) MUST extend the existing XYFlow setup. No Cytoscape dependency MAY be added.

9. **Existing public-endpoint pattern is exception-list, not `/api/public/` prefix.** `apps/control-plane/src/platform/common/auth_middleware.py` carries an exempt-paths list (e.g., `/api/v1/accounts/register`, `/api/v1/auth/oauth/providers`, `/.well-known/agent.json`, `/api/v1/maintenance/status-banner`). This spec follows the established pattern: new public endpoints are auth-exempted in middleware, not mounted under a separate `/api/public/` tree. The route paths in this spec use `/api/v1/public/...` to make the public scope visually distinct, but the middleware exemption pattern is reused (no new router-tree construct).

10. **WebSocket scaffolding is ready; the channel is not.** `apps/web/lib/ws.ts` provides `WebSocketClient` and `apps/web/types/websocket.ts` defines `WsChannel` (current values: `alerts`, `governance-verdicts`, `warm-pool`). A new `platform-status` channel and the matching backend producer are net-new but constructional, not architectural.

11. **E2E journeys J07 and J09 do not yet exist.** `tests/e2e/journeys/` contains only J01, J02, J03, J04, J10. The brownfield input's phrasing ("J07 Evaluator extension, J09 Scientific Discovery extension") is misleading: these journeys MUST be authored from scratch as part of this feature, not extended. J21 Platform State is also new. This spec calls them out as net-new in user story 7.

12. **There is no `docs-status-site/` precedent and no Astro setup.** The repo's only static site is the MkDocs Material documentation under `docs/` with i18n plugin (en + de + es + fr + it + zh). The input's Astro suggestion is implementation framing, not a constraint. This spec is implementation-agnostic on the static-site framework choice; the operational requirement (Rule 49) is "topology MUST NOT share a single point of failure with the main platform". The plan phase will choose a stack (Astro is reasonable, but Next.js static export, MkDocs subsite, or plain HTML are equally acceptable).

13. **Profile versioning / Mock LLM provider are out of scope.** The brownfield input does not mention these but adjacent UPD-044 work introduced both. This spec inherits Rule 50 (Mock LLM provider for creator previews) as a constraint only where simulation scenario "preview" flows would otherwise call real LLMs — same defaulting rule applies.

14. **Effort framing.** The brownfield input did not state an effort estimate; planning will. For specification purposes, work splits naturally into three tracks (status-page surface, maintenance/banner UX, discovery+simulation UI completion) sized roughly equally.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Visitor checks platform status from outside the app (Priority: P1)

A user (or a prospective customer) cannot reach the main application and wants to verify whether the platform is degraded or whether their own network is at fault. They open the public status page from a different device or network.

**Why this priority**: When the platform is down, the absence of an independent status surface forces customers to file a support ticket or guess. Constitution Rule 49 mandates operational independence; without delivering this story, that rule is unmet. This is the most user-visible reliability signal the platform can ship.

**Independent Test**: Open the public status URL (e.g., `status.musematic.ai`) from a device on a network that has no access to the main app. The page renders the current overall status, per-component health, active incidents, and a 30-day historical uptime view. The page exposes subscription affordances (email confirm-opt-in, RSS, Atom, outbound webhook). Accessibility: a screen reader can read the overall status within the first focus stop and the page passes axe-core AA.

**Acceptance Scenarios**:

1. **Given** the main platform is healthy, **When** a visitor opens the public status URL, **Then** the page shows "All systems operational" within the first viewport, lists each in-scope component with last-check timestamp, and exposes subscription affordances.
2. **Given** the main platform is in a partial outage, **When** the visitor opens the public status URL, **Then** the page shows the affected components in degraded/outage state, lists the active incident with severity, last update, and an updates feed.
3. **Given** the main app's authenticated API is down, **When** the visitor opens the public status URL, **Then** the page still renders (it is not served from the same failure domain) and indicates the operational impact.
4. **Given** the visitor wants to subscribe by email, **When** they submit their email address, **Then** they receive a confirmation email and are subscribed only after they click the confirmation link.
5. **Given** the visitor uses an RSS reader, **When** they paste the page's RSS feed URL, **Then** the reader receives a feed updated within 60 seconds of any incident lifecycle change.
6. **Given** an automated scraper hits the status page, **When** the request rate exceeds the public-endpoint rate limit, **Then** the response is throttled gracefully (429 with retry-after) without affecting the page's availability for human visitors.

---

### User Story 2 — Authenticated user sees a maintenance banner before and during a window (Priority: P1)

An admin schedules a maintenance window. An authenticated user is signed in before the window opens and continues using the platform across the boundary.

**Why this priority**: Today the user experiences raw 503 responses when maintenance is active. Constitution Rule 48 explicitly forbids invisible errors from the user's perspective. The banner is the user-side counterpart to backend maintenance mode; both must ship together for the maintenance UX to be coherent.

**Independent Test**: Schedule a maintenance window in the future. As an authenticated user, navigate the app, and observe an info banner with the window's start time. As the window opens, observe the banner upgrade to a warning variant indicating in-progress maintenance and a tooltip on disabled actions citing the window-end time. Attempt a write action — observe a graceful modal explaining the state and offering to retry after the window. Observe that read-only navigation continues working.

**Acceptance Scenarios**:

1. **Given** a future maintenance window is scheduled, **When** an authenticated user loads any page in the main shell, **Then** an info-variant banner renders at the top with title, scheduled-start time, optional ETA-to-end, link to the public status page, and a session-level dismiss action.
2. **Given** maintenance is currently active, **When** the same user navigates the app, **Then** the banner upgrades to warning variant, severity is conveyed by color AND icon AND text (not color alone), and the link directs to the incident detail on the public status page.
3. **Given** maintenance is currently active, **When** the user attempts an action that the maintenance gate would block, **Then** a `<MaintenanceBlockedAction>` modal explains the state in plain language, cites the window's end time, and offers either to wait or to dismiss.
4. **Given** maintenance is currently active, **When** the user performs a read-only operation, **Then** the operation succeeds normally without modal interception.
5. **Given** the maintenance window ends earlier than scheduled (admin disables it), **When** the next render occurs in the user's session, **Then** the banner disappears and previously disabled actions become enabled without requiring a refresh.
6. **Given** a user dismisses the banner, **When** they navigate to a new route, **Then** the banner re-surfaces (dismiss is per-session, not permanent) consistent with the user-visible-state requirement.

---

### User Story 3 — Authenticated user sees an incident banner with deep link to status (Priority: P1)

An incident is opened mid-session. A logged-in user notices that something feels degraded and wants to confirm whether the platform is impacted.

**Why this priority**: Incident visibility (as opposed to maintenance) is the second pillar of Rule 48. Without it, an active incident is silent from the user's view, which the constitution forbids. Users should never have to guess "is it me or the platform".

**Independent Test**: Trigger a synthetic incident at warning severity. While signed in, observe the banner appear automatically (no full page reload required). Click the link — land on the incident's detail surface on the public status page. Resolve the incident and observe the banner disappear automatically.

**Acceptance Scenarios**:

1. **Given** an incident exists at severity warning or higher, **When** an authenticated user is in the shell, **Then** the banner renders with an "incident active" variant carrying the title and last-update summary.
2. **Given** an active incident, **When** the user clicks the banner link, **Then** they land on the incident's public detail page (not on an authenticated admin page).
3. **Given** the user remains in the app, **When** the incident moves to a higher severity (warning → critical), **Then** the banner upgrades within five seconds without a full reload.
4. **Given** the incident is resolved, **When** the resolution event is observed, **Then** the banner disappears within ten seconds.

---

### User Story 4 — Customer subscribes to platform incident updates (Priority: P2)

A customer wants to be notified out-of-band whenever an incident is opened, updated, or resolved.

**Why this priority**: Subscription closes the loop between incident management and customer awareness without requiring continuous monitoring of the status page. Email/RSS/Atom/webhook coverage is FR-678 and is greenfield in this codebase.

**Independent Test**: From the public status page, subscribe via email (confirm-opt-in). Trigger an incident. Verify a notification arrives within two minutes. Update the incident; verify a follow-up arrives. Resolve the incident; verify a resolution notification arrives. Verify the RSS and Atom feeds reflect the same lifecycle within 60 seconds. Verify an HMAC-signed outbound webhook (per the established outbound-webhook pattern) is delivered.

**Acceptance Scenarios**:

1. **Given** the visitor enters an email address on the status page, **When** they submit the subscription, **Then** a confirmation email is sent and the subscription remains inactive until the visitor clicks the confirmation link (no notifications are sent before confirmation).
2. **Given** an active subscription, **When** an incident is created, updated, or resolved, **Then** an email is dispatched within two minutes containing the title, severity, latest update, and an unsubscribe link.
3. **Given** a visitor wants to scope their subscription, **When** they choose specific components (e.g., API only), **Then** they receive notifications only for incidents impacting those components.
4. **Given** a customer prefers integration over email, **When** they register an outbound webhook, **Then** webhook deliveries are HMAC-signed using the established outbound-webhook pattern, delivery is retried with exponential backoff on transient failures, and persistent failures land in a dead-letter inspection surface.
5. **Given** a customer prefers a Slack channel, **When** they register a Slack incoming webhook URL, **Then** incident lifecycle events are posted there.
6. **Given** a subscription has confirmed-bounced email delivery, **When** the operator reviews subscription health, **Then** the operator dashboard surfaces the unhealthy subscription for review.

---

### User Story 5 — Authenticated user manages their own status subscriptions (Priority: P2)

An authenticated user adjusts which platform events they want to be notified about, from inside the app.

**Why this priority**: Constitution Rule 45 ("every backend capability has UI") obligates a user-facing surface for subscription management once subscription endpoints exist. Anonymous-only management would force customers to keep emails to find unsubscribe links.

**Independent Test**: Open `/settings/status-subscriptions`. View existing subscriptions, add a new one (e.g., webhook for major incidents only), edit one, remove one. Verify changes are reflected on the next incident.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they navigate to `/settings/status-subscriptions`, **Then** the page lists their current subscriptions (channel, scope, status) and provides controls to add/edit/remove.
2. **Given** the user adds a webhook subscription, **When** they save, **Then** an HMAC test ping is delivered and the subscription is marked active only if the test ping is acknowledged.
3. **Given** the user removes a subscription, **When** they confirm, **Then** no further notifications are sent through that channel.

---

### User Story 6 — Evaluator authors a reusable simulation scenario, runs it, and inspects digital-twin divergence (Priority: P2)

An evaluator wants to define a reusable simulation scenario (agents, workflow template, mock set, input distributions, success criteria) and run it multiple times. After a run, they want to see which subsystems were mocked vs real, where the simulation diverged from production, and the time/trace comparison.

**Why this priority**: FR-679 + FR-680 close the simulation workbench gap. Today, scenarios require API scripting, and digital-twin output (which §14 of system architecture surfaces as a primary concept) is not visualised. The backend is already complete (twin CRUD, prediction, comparison endpoints all exist).

**Independent Test**: Navigate to `/evaluation-testing/simulations/scenarios/new`. Configure a scenario (agents, workflow template, tool mock set, input distributions, success criteria/assertions). Save. From the scenario library, launch with N iterations. After completion, open the run detail page and switch to the digital-twin panel; verify mock vs real component listing, divergence highlights, simulated-vs-wall-clock time, and a link to a reference production execution if one exists.

**Acceptance Scenarios**:

1. **Given** an authorised evaluator opens the new-scenario page, **When** they configure agents, workflow template, mock set, input distributions, and assertions, **Then** the form validates inline (invalid inputs cannot be saved) and persists a named scenario in the scenario library.
2. **Given** a saved scenario, **When** the evaluator launches it with N iterations, **Then** N runs are queued and each appears in the run list with status and links to its detail page.
3. **Given** a completed simulation run, **When** the evaluator opens the run detail page, **Then** the new digital-twin panel shows: a mock-vs-real component listing, divergence points highlighted against the reference production behaviour, simulated time vs wall-clock time, and a deep link to the reference production execution if one exists.
4. **Given** no reference production execution exists for a run, **When** the evaluator opens the digital-twin panel, **Then** the panel renders explicitly stating "no reference production execution available" rather than showing fabricated comparison data.
5. **Given** a scenario preview action that would otherwise invoke an LLM, **When** the user is on the scenario editor, **Then** preview defaults to the mock LLM provider and a real-LLM preview is an explicit opt-in with a clear cost indicator (Rule 50).

---

### User Story 7 — Research scientist completes the discovery workbench loop (Priority: P3)

A research scientist opens a discovery session, browses the hypothesis library, picks a hypothesis, launches an experiment, and inspects supporting evidence.

**Why this priority**: FR-681 completes the discovery surface. Backend is fully built; today the UI exposes only the network view. The completion is high-value for the research workflow but lower-priority for the platform as a whole than user-visible state.

**Independent Test**: Open `/discovery/{session_id}`. Verify the session detail page renders tabs (overview, hypotheses, experiments, evidence, network). Switch to the hypothesis library, filter by state and confidence tier, sort by ranking signals. Open a hypothesis detail. Launch a new experiment from `/discovery/{session_id}/experiments/new`. Open evidence at `/discovery/{session_id}/evidence/{evidence_id}` and confirm deep-link source pointers.

**Acceptance Scenarios**:

1. **Given** an existing discovery session, **When** the scientist navigates to `/discovery/{session_id}`, **Then** the session detail page renders with tabs for overview, hypotheses, experiments, evidence, and network; existing `/network` continues to function.
2. **Given** the hypothesis-library tab, **When** the scientist filters by state (proposed/testing/confirmed/refuted) and confidence tier and sorts by ranking signals, **Then** the list updates accordingly and each hypothesis card shows enough detail to triage.
3. **Given** the scientist selects a hypothesis, **When** they open detail, **Then** evidence pointers, related hypotheses, and a launch-experiment action are present.
4. **Given** the launch-experiment action, **When** the scientist opens `/discovery/{session_id}/experiments/new`, **Then** the experiment-launcher form validates inputs against the existing experiment endpoint contract and triggers an experiment on submit.
5. **Given** an evidence reference, **When** the scientist opens `/discovery/{session_id}/evidence/{evidence_id}`, **Then** the evidence inspector renders source links (back to the originating execution, dataset, or critique) and supports deep-link navigation.
6. **Given** a related hypothesis network is requested, **When** the scientist switches to the network tab, **Then** the existing XYFlow-based `<HypothesisNetworkGraph>` continues to render unchanged (no Cytoscape dependency is added; the network view is reused, not rewritten).

---

### User Story 8 — E2E coverage protects the visibility layer (Priority: P2)

The platform team wants automated assurance that the user-visible state surfaces, simulation scenario flow, and discovery completion remain healthy across releases.

**Why this priority**: FR-682 mandates E2E coverage. Without it, regressions on banner rendering, public-status freshness, subscription dispatch, scenario editing, or discovery navigation would land silently. Existing journeys (J01, J02, J03, J04, J10) provide the harness; J07, J09, J21 are net-new authored here.

**Independent Test**: A new E2E journey J21 Platform State runs end-to-end (synthetic incident → public status reflects within 60s → banner appears in shell → subscriber receives email → RSS contains entry → resolve → all surfaces clear). New journeys J07 Evaluator and J09 Scientific Discovery cover the simulation scenario flow and the discovery hypothesis-library + experiment-launcher flow respectively.

**Acceptance Scenarios**:

1. **Given** the test harness, **When** J21 Platform State runs, **Then** it triggers a synthetic incident, observes the public status surface within 60 seconds, observes the in-shell banner, observes a subscriber email and RSS update, resolves the incident, and observes all surfaces clear.
2. **Given** the test harness, **When** J07 Evaluator runs, **Then** it authors a simulation scenario, launches it, observes the run detail page including the digital-twin panel, and asserts the divergence summary.
3. **Given** the test harness, **When** J09 Scientific Discovery runs, **Then** it loads a session, browses the hypothesis library, launches an experiment, and inspects evidence detail.
4. **Given** the existing journeys (J01, J02, J03, J04, J10), **When** UPD-045 lands, **Then** none of them regress.

---

### Edge Cases

- **Status page generation pipeline fails**: the page falls back to a "last known state" view with an explicit age stamp ("as of HH:MM UTC, regeneration delayed"). Operators are alerted via the existing alerting rule pattern.
- **Status page under load during a major outage**: the page is served via a CDN-or-equivalent edge layer with sufficient cache TTL that read availability is not coupled to origin health (Rule 49); stale-but-accurate content is acceptable.
- **Maintenance window ends abruptly mid-action**: the banner disappears at next render and the previously blocked action is retryable without page reload.
- **Maintenance window extended past originally scheduled end**: the banner's ETA updates; users with an open `<MaintenanceBlockedAction>` modal see the new end time on next interaction.
- **Email subscription delivery hard-bounces**: subscription is marked unhealthy and surfaced on the operator dashboard; further sends are paused until operator review.
- **Subscriber confirmation email never clicked**: subscription remains inactive; an internal cleanup routine eventually purges unconfirmed subscriptions.
- **Outbound webhook subscription endpoint persistently unreachable**: deliveries land in a dead-letter inspection surface; the subscription is flagged unhealthy.
- **Subscription rate-limit abuse (e.g., automated email submission)**: the email subscription endpoint is rate-limited and includes basic anti-abuse signal handling consistent with the platform's existing public-endpoint posture; abuse details are out of scope here.
- **Simulation scenario with invalid inputs**: validation prevents save with clear inline errors; partial drafts are not persisted.
- **Simulation scenario refers to deleted agents or workflows**: the editor surfaces this as a validation error before save and on launch; the scenario remains saved but flagged as unrunnable until corrected.
- **Digital-twin panel where no reference production execution exists**: panel renders an explicit "no reference available" state instead of fabricating comparison data.
- **Discovery evidence pointing to deleted source**: evidence inspector renders an explicit "source unavailable" state with the captured snapshot if one exists.
- **WebSocket platform-status channel disconnects**: the banner falls back to periodic polling against the public status endpoint and reconnects when WS becomes available.
- **Banner localisation gap**: if a string is missing in a locale, the banner falls back to English; the missing string is surfaced as a localisation backlog item.
- **User has multiple browser tabs open**: dismissing the banner in one tab does not dismiss it in others (per-session, per-tab is the expected behaviour for clarity).

---

## Requirements *(mandatory)*

### Functional Requirements

#### Public status surface

- **FR-695-01**: The platform MUST publish a public status surface (no authentication) that renders overall platform state, per-component status with last-check timestamp, active incidents with severity and update feed, scheduled maintenance windows, recently resolved incidents (≥ 7-day history), and a 30-day per-component historical uptime view. *(implements FR-675)*
- **FR-695-02**: The public status surface MUST remain reachable when the main authenticated platform is unavailable. The deployment topology MUST NOT share a single point of failure with the main platform. *(constitutional anchor: Rule 49)*
- **FR-695-03**: The public status surface's underlying data MUST regenerate at most every 60 seconds from authoritative health and incident sources, with a fallback "last known state" view when regeneration fails.
- **FR-695-04**: The public status surface MUST expose subscription affordances for: email (confirm-opt-in), RSS, Atom, outbound webhook (HMAC-signed), Slack incoming webhook. *(implements FR-678)*
- **FR-695-05**: Public endpoints supporting the status surface MUST be auth-exempt via the established middleware exception-list pattern (not a separate router-tree); they MUST be rate-limited at a level generous to human visitors and stricter to automated abuse.

#### In-app platform status banner and maintenance UX

- **FR-695-10**: The authenticated shell MUST render a `<PlatformStatusBanner>` at the top of every authenticated page when platform state is anything other than operational. *(implements FR-676; constitutional anchor: Rule 48)*
- **FR-695-11**: The banner MUST support variants for: maintenance scheduled (info), maintenance in progress (warning), incident active (warning or critical depending on severity), degraded performance (info).
- **FR-695-12**: Severity MUST be conveyed by color AND icon AND text (not color alone) and the banner MUST pass axe-core AA. *(constitutional anchor: Rule 41 / Rule 48)*
- **FR-695-13**: The banner MUST link to the corresponding incident or maintenance detail on the public status surface and MUST surface ETA when known.
- **FR-695-14**: The banner MUST support a per-session, per-tab dismiss action that re-surfaces on the next navigation (dismiss is not permanent).
- **FR-695-15**: When maintenance mode is active, write actions blocked by `MaintenanceGateMiddleware` MUST surface a `<MaintenanceBlockedAction>` modal explaining the state and citing the window-end time. Generic 503 errors MUST NOT reach the user. *(implements FR-677)*
- **FR-695-16**: Read-only operations MUST remain functional during maintenance.
- **FR-695-17**: The banner MUST refresh in near real time (≤ five seconds) on platform-state changes via a new WebSocket channel `platform-status`; if the WebSocket is unavailable, the banner MUST fall back to polling the public status endpoint at a generous interval.

#### Incident subscription

- **FR-695-20**: Email subscription MUST require confirm-opt-in; the subscription is inactive until the visitor clicks the confirmation link.
- **FR-695-21**: Subscriptions MAY be scoped to specific components (e.g., API only, marketplace only).
- **FR-695-22**: Notification dispatch (email, RSS, Atom, webhook, Slack) MUST occur within two minutes of incident creation, update, or resolution; RSS and Atom feeds MUST update within 60 seconds.
- **FR-695-23**: Outbound webhook deliveries MUST be HMAC-signed using the established platform pattern; transient failures MUST be retried with exponential backoff; persistent failures MUST land in a dead-letter inspection surface visible to operators.
- **FR-695-24**: Every email notification MUST include an unsubscribe link.
- **FR-695-25**: Authenticated users MUST be able to manage their own status subscriptions at `/settings/status-subscriptions`. *(implements FR-678; constitutional anchor: Rule 45)*

#### Simulation scenario editor and digital-twin visualisation

- **FR-695-30**: The platform MUST provide a simulation scenario editor at `/evaluation-testing/simulations/scenarios/new` and `/[id]` where authorised users can define agents, workflow template, tool mock set, input distributions, digital-twin fidelity (which subsystems are mocked vs real), success criteria, assertions, and run schedule. *(implements FR-679)*
- **FR-695-31**: A scenario library at `/evaluation-testing/simulations/scenarios/` MUST list saved scenarios with status, last run, and launch action.
- **FR-695-32**: Launching a scenario with N iterations MUST queue N runs that appear in the existing run list and link to existing run detail pages.
- **FR-695-33**: The simulation run detail page MUST be extended with a digital-twin panel showing: mock-vs-real component listing, divergence points against reference production behaviour, simulated time vs wall-clock time, and a deep link to a reference production execution when one exists. *(implements FR-680)*
- **FR-695-34**: When no reference production execution exists for a run, the panel MUST render an explicit "no reference available" state.
- **FR-695-35**: Scenario preview actions that would otherwise invoke an LLM MUST default to the mock LLM provider; real-LLM preview MUST be an explicit opt-in with a clear cost indicator. *(constitutional anchor: Rule 50)*

#### Discovery workbench completion

- **FR-695-40**: The discovery workbench MUST expose a session detail page at `/discovery/{session_id}` with tabs for overview, hypotheses, experiments, evidence, and network. The existing `/discovery/{session_id}/network/` page MUST continue to function unchanged. *(implements FR-681)*
- **FR-695-41**: A hypothesis library page at `/discovery/{session_id}/hypotheses` MUST list hypotheses with filtering by state (proposed/testing/confirmed/refuted) and confidence tier and ranking by confidence/novelty signals.
- **FR-695-42**: Hypothesis detail MUST surface evidence pointers, related hypotheses, and a launch-experiment action.
- **FR-695-43**: An experiment launcher at `/discovery/{session_id}/experiments/new` MUST validate inputs against the existing experiment endpoint contract and trigger an experiment on submit.
- **FR-695-44**: An evidence inspector at `/discovery/{session_id}/evidence/{evidence_id}` MUST render source links and support deep-link navigation.
- **FR-695-45**: The hypothesis network view MUST reuse the existing XYFlow-based `<HypothesisNetworkGraph>`; no Cytoscape dependency MAY be added.

#### E2E coverage and accessibility/i18n

- **FR-695-50**: A new E2E journey **J21 Platform State** MUST exercise the visibility layer end-to-end: synthetic incident → public status surface within 60 seconds → in-shell banner → subscriber email → RSS update → resolve → all surfaces clear. *(implements FR-682)*
- **FR-695-51**: A new E2E journey **J07 Evaluator** MUST cover the simulation scenario authoring → launch → digital-twin panel inspection flow.
- **FR-695-52**: A new E2E journey **J09 Scientific Discovery** MUST cover the session detail → hypothesis library → experiment launcher → evidence inspector flow.
- **FR-695-53**: All net-new pages and components MUST pass axe-core AA. *(constitutional anchor: Rule 41)*
- **FR-695-54**: All net-new user-facing copy MUST be localised across the existing six locales (en, es, de, fr, it, zh).

#### Observability

- **FR-695-60**: Platform-state changes (maintenance enabled/disabled, incident open/update/resolve) MUST be observable on the existing audit trail (Rule 9) with full PII compliance and at the existing log/metric channels.
- **FR-695-61**: Subscription dispatch latency, RSS/Atom freshness, and public-status regeneration latency MUST be exposed as metrics on the existing observability stack.

### Key Entities *(include if feature involves data)*

- **PlatformStatusSnapshot**: A time-stamped roll-up capturing overall platform status, per-component statuses, active incidents, scheduled maintenance windows, and recent resolved incidents. Source for both the public status surface and the in-shell banner. Regenerates from authoritative sources at most every 60 seconds.
- **StatusSubscription**: A single subscription owned either by an anonymous visitor (identified by a confirmation token) or by an authenticated user. Has a channel (email / RSS / Atom / webhook / Slack), optional component scope, confirmation state, health state (healthy / unhealthy / unsubscribed), and dispatch history.
- **SubscriptionDispatch**: A single dispatch attempt for an event × subscription pair. Carries timestamp, outcome (sent / retrying / dead-lettered), and HMAC signature data for webhooks.
- **SimulationScenario**: A reusable scenario definition referencing agents, a workflow template, a tool-mock set, input distributions, digital-twin fidelity, success criteria/assertions, and a run schedule. Launching produces N concrete simulation runs (existing entity).
- **DigitalTwinDivergenceReport**: A per-run derivation surfacing mock-vs-real component listing, divergence points relative to reference production behaviour, simulated-vs-wall-clock time, and a reference production execution link when available.
- **DiscoverySessionView**: A per-session UI projection of session, hypotheses (with ranking signals), experiments, evidence, and network references. Composed from existing discovery service entities; no new persistence on the discovery side.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The public status surface renders overall platform state and per-component status within ≤ 2 seconds at the 95th percentile from a clean cache, and remains reachable while the main authenticated platform is unavailable (verified by the J21 disaster simulation).
- **SC-002**: The in-shell `<PlatformStatusBanner>` reflects platform-state changes within ≤ 5 seconds at the 95th percentile via the new `platform-status` WebSocket channel; with WebSocket unavailable, the banner reflects state within ≤ 60 seconds via polling fallback.
- **SC-003**: 100% of incident lifecycle transitions (open / update / resolve) result in dispatched email and webhook notifications within 2 minutes (95th percentile) and RSS/Atom feed updates within 60 seconds (95th percentile), measured over a representative test window.
- **SC-004**: 0 generic 503 responses reach the user during an active maintenance window, measured by traffic-replay testing in J21; every maintenance-blocked write surfaces `<MaintenanceBlockedAction>` instead.
- **SC-005**: The simulation scenario editor allows an evaluator to define and launch a scenario in ≤ 5 minutes without API scripting, measured against a baseline task script in J07.
- **SC-006**: The digital-twin panel renders mock-vs-real component listing and divergence highlights for ≥ 95% of completed runs that have a reference production execution available; the explicit "no reference available" state renders for the remainder.
- **SC-007**: The discovery hypothesis library supports filter (by state and confidence tier) and ranking, with all interactions completing in ≤ 1 second at the 95th percentile on a session of 200+ hypotheses.
- **SC-008**: J07 Evaluator, J09 Scientific Discovery, and J21 Platform State all pass in CI on the v1.4.0 release branch and on `main` thereafter.
- **SC-009**: All net-new pages and components pass axe-core AA with zero serious or critical violations.
- **SC-010**: All net-new user-facing copy is delivered in all six locales (en, es, de, fr, it, zh) on the day of release; missing strings fall back to English with a localisation backlog item.
- **SC-011**: Customer support tickets attributable to "is the platform up?" and "why is this action blocked?" decline by an order of magnitude over the first three months post-release, measured against the pre-release baseline.
- **SC-012**: The status page deployment satisfies an independence test: with the main authenticated stack rendered fully unreachable in a controlled failure-injection drill, the status page remains reachable and reflects degraded state.
- **SC-013**: The public-status endpoint sustains a sudden 10x request burst without origin degradation, served from edge cache.

---

## Assumptions

- **Existing maintenance backend is reused unchanged**, including `MaintenanceGateMiddleware`, the public `/api/v1/maintenance/status-banner` endpoint, and the `maintenance.mode.enabled/disabled` Kafka events. The new WebSocket `platform-status` channel composes with these signals; no maintenance backend rewrites are in scope.
- **Existing incident backend is reused unchanged**, including incident CRUD, severities, and lifecycle. Subscription endpoints (email/RSS/Atom/webhook/Slack) are net-new and consume the existing incident events.
- **Existing simulation backend is reused unchanged**, including digital-twin CRUD, prediction, and comparison endpoints. Scenario CRUD and the scenario-run trigger are net-new.
- **Existing discovery backend is reused unchanged**; the discovery side is frontend-only except for an evidence-detail confirm-shape pass.
- **Existing graph library** (`@xyflow/react` + `@dagrejs/dagre`) is the canonical primitive for hypothesis-network rendering. No Cytoscape dependency may be introduced.
- **Existing public-endpoint pattern** (auth-middleware exception list) is extended for new status endpoints; a separate `/api/public/` router-tree is not introduced.
- **Existing authenticated shell** at `apps/web/app/(main)/` is the integration point for `<PlatformStatusBanner>`; no new shell layout is created.
- **Existing six-locale translation pipeline** (en, es, de, fr, it, zh) is the localisation surface; no new locales are introduced here.
- **HMAC-signed outbound webhook pattern** already in use by other platform features is reused for status-page webhook subscriptions; no new signing mechanism is introduced.
- **Operator dashboard** for unhealthy-subscription review reuses the existing operator surface conventions; no new dashboard product is created.
- **Status-page hosting topology** must satisfy Rule 49 (no shared single point of failure with the main platform); the choice of static-site framework and hosting target is implementation, not specification.
- **Cost indicator on real-LLM scenario preview** reuses the existing cost-indicator pattern from creator workbench (UPD-044); no new pattern is invented.
- **Out of scope for this feature**: a new operator-side dashboard product, anti-abuse hardening beyond standard rate-limits, profile versioning, structural changes to the existing six locales, and any backend changes to the discovery workbench beyond the evidence-detail confirm-shape pass.
