# Quickstart & Acceptance Scenarios: Frontend Updates for All New Features

**Feature**: 070-frontend-updates-cross-cutting
**Date**: 2026-04-20

Ten acceptance scenarios (Q1–Q10), one per user story, each with concrete click paths, expected DOM assertions, and Playwright hints.

## Setup Prerequisites

- Backend features 053–067 shipped (or mocked via MSW in `apps/web/mocks/`)
- Logged-in test user with `platform_admin` role (covers all RBAC tiers; per-scenario RBAC is also exercised separately)
- Active workspace with ≥ 1 agent (modern + 1 legacy for coverage) and ≥ 1 conversation

---

## Q1 — US1 Agent Authoring with FQN, purpose, role, and visibility

**Route**: `/agents/create`

**Steps**:
1. Fill `Namespace` = `ops`, `Local Name` = `kyc-verifier-v2`, `Role Type` = `verdict_authority`
2. Attempt to save with purpose = "short" (< 50 chars) — Save button disabled, char-counter shows "5 / 50" in red
3. Fill `Purpose` textarea with ≥ 50 chars — char-counter turns neutral, Save enabled
4. Add visibility pattern `workspace:*/agent:compliance-*` — live preview renders "All workspaces, agents with names starting with 'compliance-'"
5. Click Save

**Expected**:
- `POST /api/v1/agents` called with full payload including `namespace`, `localName`, `purpose`, `roleType`, `visibilityPatterns[]`
- Redirect to agent detail page showing FQN `ops:kyc-verifier-v2`

**Legacy path**: open `/agents/<legacy-id>/edit` → banner "This agent predates FQN — assign a namespace to activate governance features" appears; Save disabled until both namespace + local_name provided.

**Playwright**: `e2e/agent-fqn-authoring.spec.ts`

---

## Q2 — US2 Marketplace discovery via FQN + certification

**Route**: `/marketplace`

**Steps**:
1. Type `ops:` in the search bar — 300 ms debounce, URL updates to `?q=ops%3A`
2. Only agents whose FQN starts with `ops:` appear; a collapsed "Legacy (uncategorized)" bucket appears at the bottom
3. One card shows certification expiring in 12 days → amber pill "Expires in 12 days"; hover reveals exact timestamp
4. One card has expired certification → red pill "Certification expired"; Invoke button disabled with tooltip "Agent is not currently certified for use"
5. Click clear search — URL removes `?q=`; legacy + modern agents interleaved again

**Playwright**: `e2e/marketplace-fqn-discovery.spec.ts`

---

## Q3 — US3 Workspace goal lifecycle + goal-scoped filter + decision rationale

**Route**: `/conversations/<id>` with active goal

**Steps**:
1. Workspace header shows goal chip `in_progress`, goal title, and "Complete Goal" button (enabled)
2. Toggle the "Goal-scoped" filter — URL updates to `?goal-scoped=true`; banner "Filtered to goal: {title}" appears; message list filters to GID-tagged messages only
3. Dismiss banner — filter clears; URL drops `goal-scoped`
4. Click an agent response → open debug panel → "Decision Rationale" section shows four collapsible sub-sections
5. Click "Complete Goal" → `ConfirmDialog` opens → confirm → goal chip becomes `completed`, button disables

**Playwright**: `e2e/workspace-goal-lifecycle.spec.ts`

---

## Q4 — US4 Alert settings + notification bell

**Route**: `/settings/alerts`

**Steps**:
1. Page loads with defaults: critical transitions ON (`execution.failed`, `trust.certification_expired`, `governance.verdict_issued`), informational OFF
2. Banner: "These are our recommended defaults; customize below"
3. Toggle `interaction.idle` OFF, delivery method = "in-app", save
4. Simulate WS `alert.created` event (via backend or MSW) — bell increments within 3 s, pulses briefly, dropdown shows new alert at top with "Just now"
5. Navigate to `/conversations/<id>` → toggle "Mute alerts for this interaction" → simulate another matching WS event → bell does NOT increment
6. Drop WebSocket connection → bell shows disconnected indicator → after reconnect, bell unread count matches server truth (reconciliation)

**Playwright**: `e2e/alert-settings-and-bell.spec.ts`

---

## Q5 — US5 Governance chain editor + visibility grants

**Route**: `/settings/governance`

**Steps**:
1. Three slots rendered (Observer / Judge / Enforcer); each shows the current assignment or "No {role} assigned — fleet default applies"
2. Drag `ops:verdict-authority` card from side panel into the Judge slot
3. Save → `ConfirmDialog` summarizes "Assign `ops:verdict-authority` as Judge?" → confirm
4. `PATCH /api/v1/governance/chain` called
5. Navigate to `/settings/visibility` → add grant `workspace:*/agent:compliance-*` → live preview lists matching agents → Save

**Keyboard-only path**: Tab to card → Space to pick → arrow keys to navigate → Space to drop.

**Playwright**: `e2e/governance-chain-editor.spec.ts`

---

## Q6 — US6 Execution detail: trajectory + checkpoints + debate + ReAct

**Route**: `/operator/executions/<id>` with a 150-step ReAct execution that has 3 checkpoints and a debate section

**Steps**:
1. Page loads; Trajectory tab active; vertical timeline shows virtualized list (only ~30 steps in DOM at once); first step renders within 1 s
2. Each step shows index + FQN + duration + tokens + efficiency badge (green/amber/red or neutral "Unscored")
3. Deep link `?step=75` scrolls step 75 into view and highlights it
4. Open Checkpoints sidebar → click "Roll back" on checkpoint #2 → `ConfirmDialog` opens requiring typed checkpoint ID → type ID → confirm → rollback request fires
5. Switch to Debate tab → chat feed renders participant-colored bubbles; one participant shows tombstone "Agent no longer exists"
6. Switch to ReAct tab → each cycle card shows Thought / Action / Observation collapsible

**Playwright**: `e2e/execution-trajectory.spec.ts`

---

## Q7 — US7 Evaluation suite editor: rubric + calibration + comparison

**Route**: `/evaluation-testing/suites/<id>?section=rubric`

**Steps**:
1. Add 3 rubric dimensions (Accuracy 0.5, Fluency 0.3, Safety 0.2) — sum indicator shows "1.0" in green; Save enabled
2. Change Accuracy weight to 0.6 — sum indicator shows "1.1" in red within 100 ms; Save disabled
3. Revert to 0.5 → Save enabled again
4. Navigate to `?section=calibration` → box plot renders per dimension with min/Q1/median/Q3/max; Safety dimension shows outlier annotation (κ = 0.52 < 0.6)
5. Switch to `?section=comparison` → dropdown shows 4 methods; select `semantic_similarity` → description updates

**Playwright**: `e2e/evaluation-rubric-editor.spec.ts`

---

## Q8 — US8 Agent profile: contracts + A2A + MCP

**Route**: `/agents/<id>?tab=contracts`

**Steps**:
1. Contracts tab lists 3 contracts chronologically with badges (`active`, `superseded`, `superseded`)
2. Click two contracts → "Diff" button enables → two-column diff dialog opens
3. Switch `?tab=a2a` → Agent Card JSON rendered as syntax-highlighted block with Copy button; when agent has no A2A config → empty state with "Configure" CTA
4. Switch `?tab=mcp` → list of MCP servers with name + capability counts + health dot + Disconnect action
5. Click Disconnect → `ConfirmDialog` → confirm → server removed

**Playwright**: `e2e/agent-profile-a2a-mcp.spec.ts`

---

## Q9 — US9 Trust workbench: certifiers + expiries + surveillance

**Route**: `/trust-workbench?tab=certifiers`

**Steps**:
1. Click "Add Certifier" → form requires display name, HTTPS endpoint (http:// rejected), PEM public key (invalid format rejected), scope
2. Fill valid values → Save → certifier appears in list
3. Switch `?tab=expiries` → table lists all 47 certifications sorted by expiry-ascending; status chips green/amber/red with text labels
4. Click column header → sort toggles; URL persists sort param
5. Switch `?tab=surveillance` → agent picker → select agent → panel shows latest 20 signals + Recharts sparkline

**Playwright**: `e2e/trust-workbench-certifiers.spec.ts`

---

## Q10 — US10 Operator dashboard: warm pool + verdicts + decommission + gauges

**Route**: `/operator?panel=warm-pool`

**Steps**:
1. Warm-pool panel shows 3 profiles (small/medium/large); each card shows target vs actual with delta badge; one profile is amber "within 20%"
2. Click profile card → drawer opens with 5 most recent scaling events
3. WS `warm-pool.updated` event for that profile → card updates in place; if transitions to `below_target`, card flashes red
4. Scroll to verdict feed → `aria-live="polite"` region; WS `verdict.issued` event → new entry flashes briefly at top with offending FQN + verdict type + enforcer FQN + action taken
5. Click "Decommission Agent" for an agent → wizard opens → Stage 1 shows warning + downstream dependencies → Next → Stage 2 shows dry-run diff → Next → Stage 3 requires typing agent FQN → confirm → agent moves to `retiring` status
6. Reliability gauges panel shows three Recharts radial gauges (API / execution / event delivery); each shows 30-day availability with color threshold (green/amber/red)

**Playwright**: `e2e/operator-dashboard-expansions.spec.ts`

---

## Cross-cutting verification

After Q1–Q10 pass:

- Run the existing Playwright suite (`npx playwright test`) → all previously-passing scenarios still pass (SC-007)
- Run Vitest (`npm test`) → coverage ≥ 80% statements on new components (SC-010)
- Keyboard navigation: every new page reachable via Tab only; focus visible at all times (SC-006)
- Screen-reader spot-check: VoiceOver or NVDA announces bell badge changes, verdict-feed additions, warm-pool flashes
- Responsive check: shrink viewport to 375 px → all new panels stack single-column; no horizontal scroll
