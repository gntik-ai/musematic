# Quickstart: Home Dashboard

**Branch**: `026-home-dashboard` | **Date**: 2026-04-11

## Prerequisites

- `apps/web/` scaffold from feature 015 set up and running
- Backend control plane (`apps/control-plane/`) running with API profile
- Features 018 (workspaces), 020 (analytics), 024 (interactions) deployed
- WebSocket gateway (feature 019) running (`ws-hub` profile)
- Valid JWT from feature 014 (auth)

## Running the Frontend

```bash
cd apps/web
pnpm install
pnpm dev
# → http://localhost:3000
```

Navigate to `http://localhost:3000/home` after logging in. The dashboard renders at the `/(main)/home` route.

## Running Tests

```bash
cd apps/web

# Unit + component tests (Vitest + RTL)
pnpm test

# With coverage
pnpm test:coverage

# E2e tests (Playwright — requires dev server running)
pnpm test:e2e
```

## MSW Mock Setup (for offline development)

The dashboard works without a running backend when MSW mocks are active:

```bash
# Enable MSW mocks
NEXT_PUBLIC_MSW_ENABLED=true pnpm dev
```

MSW handlers for the dashboard are in:
- `apps/web/mocks/handlers/home.ts`

## Test Scenarios

### Scenario 1 — Workspace Summary Grid

1. Log in and navigate to `/home`
2. Observe: 4 metric cards appear within 2 seconds (SC-001)
3. Each card shows: numeric value + label + change indicator (↑↓ or stable)
4. Switch workspace via the workspace selector
5. Observe: all cards update to the new workspace's data within 2 seconds

**Expected cards**:
| Card | Label | Example Value |
|------|-------|---------------|
| Active Agents | "Active Agents" | 12 ↑ +3 |
| Running Executions | "Running Executions" | 4 → stable |
| Pending Approvals | "Pending Approvals" | 2 ↓ -1 |
| Current Cost | "Cost (Apr 2026)" | $142.50 ↑ +$12 |

### Scenario 2 — Recent Activity Feed

1. Navigate to `/home`
2. Observe: Timeline component shows up to 10 entries, newest first
3. Each entry has: title, relative timestamp ("3 min ago"), status badge
4. Click any entry → verify navigation to the correct detail page
5. In another browser tab, complete a workflow execution
6. Return to the dashboard — observe the new entry appears at the top within 1 second (real-time update)

### Scenario 3 — Pending Actions

1. Trigger a pending approval in a separate tab (start a policy-gated execution)
2. Navigate to `/home`
3. Observe: A pending approval card appears in the Pending Actions section
4. Click "Approve" → observe: card disappears (optimistic), success toast
5. Observe: "Pending Approvals" metric card decrements by 1

**Test: Failed execution card**
1. Trigger a workflow that will fail (e.g., invalid config)
2. Navigate to `/home`
3. Observe: A "high urgency" failed execution card appears with red left border
4. Click "View Details" → verify navigation to the execution detail page

### Scenario 4 — Quick Actions

1. Navigate to `/home`
2. Observe: 4 quick action buttons visible
3. Click "New Conversation" → verify navigation to `/conversations/new`
4. Click "Browse Marketplace" → verify navigation to `/marketplace`
5. Log in as a viewer-role user
6. Observe: "Upload Agent" and "Create Workflow" are disabled with tooltip "Requires write access"

### Scenario 5 — Real-Time Updates (WebSocket)

```bash
# Open the dashboard in a browser tab
# In another tab, trigger events:

# 1. Start a new execution
curl -X POST http://localhost:8000/api/v1/workspaces/{ws_id}/workflows/{wf_id}/execute

# Observe the dashboard tab:
# - Activity feed gains a new "execution started" entry
# - "Running executions" metric card increments
```

### Scenario 6 — Connection Loss Recovery

1. Open the dashboard in a browser
2. Open DevTools → Network → go offline
3. Observe: `ConnectionStatusBanner` appears ("Live updates paused — reconnecting…")
4. Observe: dashboard continues showing last-loaded data (not blank)
5. Go back online in DevTools
6. Observe: banner disappears; dashboard data refreshes

### Scenario 7 — Partial Failure Isolation

1. In MSW handlers, configure the analytics summary endpoint to return 500
2. Navigate to `/home`
3. Observe: `WorkspaceSummary` section shows "SectionError" with "Retry" button
4. Observe: `RecentActivity` and `PendingActions` load normally
5. Click "Retry" in WorkspaceSummary → if MSW mock is fixed, it loads

### Scenario 8 — Empty State

1. Create a brand-new workspace with no activity
2. Navigate to `/home` in that workspace
3. Observe:
   - WorkspaceSummary: 4 cards all showing "0" with "stable" indicators
   - RecentActivity: EmptyState ("No recent activity — start by creating an agent or running a workflow")
   - PendingActions: EmptyState ("All clear — no pending actions")
   - QuickActions: all 4 buttons enabled (for admin/owner role)

### Scenario 9 — Accessibility

```bash
# Run axe-core accessibility check
pnpm test:a11y
```

- Tab through all interactive elements — verify visible focus rings
- Enable a screen reader and navigate the dashboard
- Verify MetricCards have `aria-label` including the change indicator
- Verify EmptyState has descriptive text (not just an icon)
- Verify ConnectionStatusBanner has `role="status"` and `aria-live="polite"`

### Scenario 10 — Responsive Layout

Resize the browser window:
- **1280px+**: 4-column metric grid, 2-column activity/pending layout
- **768–1279px**: 2-column metric grid, stacked activity/pending
- **< 768px**: 1-column everything, quick actions wrap

Verify no horizontal scroll at any width ≥ 320px.

## Environment Variables (Frontend)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8001
NEXT_PUBLIC_MSW_ENABLED=false          # Set to true for mock-based dev
```
