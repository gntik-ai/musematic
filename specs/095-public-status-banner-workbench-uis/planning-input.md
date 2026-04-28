# UPD-045 — Public Status Page, Platform State Banner, and Remaining Workbench UIs

## Brownfield Context

**Current state (verified in repo):**
- Backend health endpoints exist per service (`/healthz`, `/readyz`).
- UPD-031 Incident Response adds incident-management backend and admin page only.
- UPD-025 Multi-Region adds maintenance mode backend + admin toggle.
- Simulation UI exists with `new / [runId] / compare / page.tsx` but no scenario editor for reusable scenarios.
- Discovery UI only has `/discovery/[session_id]/network/page.tsx` — missing session detail, hypothesis library, experiment launcher, evidence inspector.

**Gaps:**
1. **No public status page** — users and visitors cannot check platform health from outside the app. Customers have no independent way to verify outages or confirm the platform is up.
2. **No in-app platform status banner** — when maintenance mode is active or an incident is ongoing, the user sees generic errors instead of a contextual banner explaining the state.
3. **No incident subscription** — customers cannot subscribe to status updates via email, RSS, webhook.
4. **No maintenance-mode UX in user UI** — the admin can enable maintenance mode, but the user experience during that window is effectively broken (errors + no explanation).
5. **No simulation scenario editor** — existing pages allow running a simulation, but creating reusable scenarios requires API scripting.
6. **No digital twin visualization** — FR-271 and §14 describe digital twins; the UI does not surface them.
7. **Scientific discovery workbench is single-page** — only the network view exists; hypothesis library, experiment launcher, evidence inspector, session detail beyond network all missing.

**Extends:**
- UPD-025 Multi-Region HA (maintenance mode backend).
- UPD-031 Incident Response (admin incident management).
- Feature 051 Scientific Discovery (backend full; UI minimal).
- Simulation feature (backend full; UI partial).
- UPD-035 E2E (J07 Evaluator, J09 Scientific Discovery extensions).

**FRs:** FR-675 through FR-682 (section 118).

---

## Summary

UPD-045 makes the platform's state **visible** to the people affected by it, and fills the remaining UI gaps in simulation and scientific discovery workbenches. The feature delivers:

- Public status page (`status.musematic.ai`) — static, independent of the main app.
- `<PlatformStatusBanner>` component in the authenticated shell.
- Maintenance-mode graceful UX replacing generic errors.
- Incident subscription (email / RSS / webhook / Atom).
- Simulation scenario editor for reusable scenarios.
- Digital twin visualization on simulation detail pages.
- Scientific discovery workbench completion: hypothesis library, experiment launcher, evidence inspector.

---

## User Scenarios

### User Story 1 — Customer checks status during perceived outage (Priority: P1)

A customer can't reach the platform and wonders if it's down or their network.

**Independent Test:** Open `status.musematic.ai` in a separate network context (tethered phone, different network). See current status. Subscribe to updates.

**Acceptance:**
1. Public status page is hosted on a separate infrastructure path (static generation served from CDN or a dedicated tiny pod) so it remains reachable even if the main app is down.
2. Overall status (operational / degraded / partial outage / full outage) visible at first viewport.
3. Per-component status with last-check timestamp.
4. Active incidents with severity and updates feed.
5. 30-day historical uptime per component.
6. Subscribe-to-updates: email (confirm-opt-in), RSS feed URL, Atom feed URL, outbound webhook, Slack incoming webhook.
7. Accessibility AA compliant.

### User Story 2 — User sees maintenance banner and understands (Priority: P1)

Admin enables scheduled maintenance for Friday 23:00 UTC. A user logs in Friday at 22:00.

**Independent Test:** Admin schedules maintenance. User logs in before the window. Sees info banner with ETA. At 23:00, banner flips to warning with blocked-actions indicator. At 23:30, user attempts an action that is blocked — sees graceful modal, not a generic error.

**Acceptance:**
1. `<PlatformStatusBanner>` renders at the top of every authenticated page when state is not operational.
2. Variants: maintenance scheduled (info) / maintenance in progress (warning, blocks affected features) / incident active (warning or critical) / degraded performance (info).
3. Banner shows concise title, link to status page, optional ETA, dismiss-for-session action.
4. Severity conveyed by color AND icon AND text (not color alone).
5. During maintenance: affected actions disabled with clear tooltip citing the maintenance window end time.
6. Read-only operations continue to work.
7. Blocked action attempts show graceful modal explaining the state.

### User Story 3 — Subscriber receives incident notifications (Priority: P2)

A customer subscribes to incidents via email. An incident is created with severity major.

**Independent Test:** Subscribe via email on status page. Trigger an incident via admin. Receive email within 2 minutes. Resolve incident. Receive resolution email.

**Acceptance:**
1. Email subscription uses confirm-opt-in.
2. Subscriptions can be scoped to components.
3. Notifications sent within 2 minutes of incident creation / update / resolution.
4. RSS and Atom feeds update within 60 seconds.
5. Outbound webhook delivery is HMAC-signed per UPD-028.
6. Unsubscribe link in every email.

### User Story 4 — Evaluator creates a reusable simulation scenario (Priority: P2)

An evaluator wants to test a new reasoning pattern across 10 runs with varying inputs.

**Independent Test:** Navigate to `/evaluation-testing/simulations/scenarios/new`. Configure agents, workflow template, tool mock set, input distributions, assertions. Save. Launch scenario. Verify 10 runs execute.

**Acceptance:**
1. Scenario editor allows configuring all parameters per FR-679.
2. Digital twin fidelity configurable: which subsystems are mocked vs real.
3. Success criteria and assertions editable with inline schema.
4. Save creates a named scenario in the scenario library.
5. Launch runs the scenario with N iterations.
6. Results aggregated in `/evaluation-testing/simulations/[runId]/page.tsx`.

### User Story 5 — Evaluator inspects digital twin divergence (Priority: P2)

An evaluator suspects a simulation diverged from production behavior.

**Independent Test:** Open a simulation run's detail page. Open digital twin panel. See which components ran as mocks vs real, divergence points, simulated vs wall-clock time, trace comparison to a reference production execution.

**Acceptance:**
1. Digital twin panel shows mock/real component list.
2. Divergence points highlighted (where simulated behavior differed from expected).
3. Simulated time vs wall-clock time comparison.
4. Link to reference production execution if available.
5. Operators can reproduce the same inputs in production for debugging.

### User Story 6 — Research scientist explores hypothesis library (Priority: P3)

A research scientist opens the discovery workbench to review the current hypothesis catalog for their session.

**Independent Test:** Open `/discovery/{session_id}`. Navigate to hypotheses tab. Filter by confidence tier. Select a hypothesis. Launch an experiment to test it.

**Acceptance:**
1. `/discovery/{session_id}/page.tsx` is the session detail with tabs: overview, hypotheses, experiments, evidence, network.
2. `/discovery/{session_id}/hypotheses/page.tsx` lists hypotheses with ranking by confidence / novelty.
3. Filter by state (proposed, testing, confirmed, refuted), by confidence tier.
4. Hypothesis detail with evidence pointers, related hypotheses.
5. `/discovery/{session_id}/experiments/new/page.tsx` experiment launcher.
6. `/discovery/{session_id}/evidence/{evidence_id}/page.tsx` evidence inspector.

---

### Edge Cases

- **Status page static generation fails**: fall back to "last known state" with an age warning. Alert to platform operator.
- **Email subscription email bounces**: mark subscription unhealthy; operator dashboard surfaces it.
- **Maintenance mode ends abruptly mid-user-action**: banner disappears; user can retry the previously blocked action.
- **Status page under heavy load during major outage**: CDN caching protects; stale but accurate content acceptable.
- **Simulation scenario with invalid inputs**: validation prevents save; clear error messages.
- **Digital twin divergence where real production execution unavailable**: panel notes this clearly instead of mocking a comparison.

---

## UI Routes (Next.js)

```
apps/web/app/(main)/                         # Banner injection
  shell/components/PlatformStatusBanner.tsx  # NEW

apps/web/app/(main)/evaluation-testing/
├── simulations/
│   ├── scenarios/
│   │   ├── page.tsx                          # NEW: scenario library
│   │   ├── new/page.tsx                      # NEW: scenario editor
│   │   └── [id]/page.tsx                     # NEW: scenario detail
│   └── [runId]/page.tsx                      # existing, extended with digital twin panel
└── page.tsx                                  # existing

apps/web/app/(main)/discovery/
├── [session_id]/
│   ├── page.tsx                              # NEW: session detail with tabs (moved from network-only)
│   ├── hypotheses/page.tsx                   # NEW: hypothesis library
│   ├── experiments/
│   │   ├── page.tsx                          # NEW: experiments list
│   │   └── new/page.tsx                      # NEW: experiment launcher
│   ├── evidence/
│   │   └── [evidence_id]/page.tsx            # NEW: evidence inspector
│   └── network/page.tsx                      # existing
```

**Public status page** (separate deployment):
```
docs-status-site/                             # NEW: static site generator (Astro or similar lightweight framework)
├── public/                                   # Served from CDN or dedicated pod
│   ├── index.html                            # Overall status
│   ├── components/{component}.html           # Per-component pages
│   ├── feed.xml                              # Atom feed
│   ├── feed.rss                              # RSS feed
│   └── subscribe/                            # Email subscription flow
```

The static site regenerates every 60 seconds via a cron job hitting health endpoints.

## Shared Components

- `<PlatformStatusBanner>` — global banner in authenticated shell; WebSocket subscription to platform state channel.
- `<MaintenanceBlockedAction>` — modal shown on blocked action during maintenance.
- `<StatusIndicator>` — reusable dot/text rendering operational state.
- `<ComponentStatusRow>` — row for status page per-component table.
- `<SimulationScenarioEditor>` — full editor.
- `<DigitalTwinPanel>` — visualization in simulation detail.
- `<HypothesisCard>` — card for library list.
- `<HypothesisGraph>` — graph reusing existing Cytoscape integration.
- `<ExperimentLauncher>` — launcher form with parameter validation.
- `<EvidenceInspector>` — inspection view with source links.

## Backend Additions

- `GET /api/public/status` — public endpoint (no auth) returning platform state. Rate-limited but generous.
- `GET /api/public/incidents` — public endpoint returning active + recent incidents.
- `GET /api/public/status/feed.{rss,atom}` — feeds.
- `POST /api/public/subscribe/email` — email subscription with confirm-opt-in.
- `GET /api/v1/me/platform-status` — authenticated version with user-specific context (which features are affected).
- `GET /api/v1/simulations/scenarios` / `POST` / `PUT {id}` / `DELETE {id}`.
- `POST /api/v1/simulations/scenarios/{id}/run`.
- `GET /api/v1/discovery/{session_id}/hypotheses` — already exists, confirm shape.
- `POST /api/v1/discovery/{session_id}/experiments` — trigger experiment.
- `GET /api/v1/discovery/{session_id}/evidence/{id}` — evidence detail.

## Acceptance Criteria

- [ ] Public status page deployed at `status.musematic.ai`
- [ ] Page available even when main app is down
- [ ] Per-component status, incidents, historical uptime rendered
- [ ] Subscription via email / RSS / webhook / Atom functional
- [ ] `<PlatformStatusBanner>` renders correctly on every authenticated page when state != operational
- [ ] Banner severity conveyed by color + icon + text
- [ ] Maintenance blocked actions show graceful modal
- [ ] Read-only operations continue during maintenance
- [ ] Simulation scenario editor functional with digital twin fidelity config
- [ ] Digital twin panel on simulation detail shows divergence
- [ ] Discovery session detail with tabs renders correctly
- [ ] Hypothesis library filterable and rankable
- [ ] Experiment launcher triggers experiments correctly
- [ ] Evidence inspector deep-links to sources
- [ ] J21 Platform State E2E journey passes
- [ ] J07 Evaluator extended to cover simulation scenario editor
- [ ] J09 Scientific Discovery extended to cover hypothesis library + experiment launcher
- [ ] All new pages pass axe-core AA
- [ ] All new pages localized in 6 languages
