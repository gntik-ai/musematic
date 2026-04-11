# Quickstart: Next.js Application Scaffold

**Feature**: 015-nextjs-app-scaffold  
**Date**: 2026-04-11

---

## Prerequisites

- Node.js 20+
- pnpm 9+
- Backend API running (feature 013/014) — or use MSW mocks (see below)

---

## Install & Run

```bash
# From repo root
cd apps/web
pnpm install
pnpm dev
```

Application starts at `http://localhost:3000`.

---

## Environment Setup

Copy `.env.example` to `.env.local` and fill in:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
NEXT_PUBLIC_APP_ENV=development
```

For offline development without a running backend, MSW intercepts all requests. Set `NEXT_PUBLIC_APP_ENV=development` — MSW handlers in `mocks/handlers.ts` provide fixture responses.

---

## Verify: Theme & Dark Mode

1. Open `http://localhost:3000` in a browser
2. Verify the page renders with brand colors (primary blue/indigo, not browser defaults)
3. Click the theme toggle in the header
4. Verify ALL UI elements switch to dark mode simultaneously — no un-themed elements
5. Reload the page — theme selection persists

**Expected**: No white flash on load (FOIT prevention via `next-themes` `suppressHydrationWarning`)

---

## Verify: App Shell

1. Log in with a test user (or use MSW mock — any credentials accepted in dev)
2. Verify sidebar renders with navigation items filtered to the user's role
3. Click the collapse toggle at the bottom of the sidebar
4. Verify sidebar collapses to icons only within 200ms — no layout jitter
5. Verify main content expands to fill freed space
6. Navigate to a nested route (e.g., `/agents/create`)
7. Verify breadcrumbs update: `Home > Agents > Create Agent`

---

## Verify: Command Palette

1. Press `Cmd+K` (macOS) or `Ctrl+K` (Windows/Linux)
2. Verify the command palette opens within 100ms
3. Type a partial navigation item name (e.g., "age")
4. Verify filtered results appear instantly
5. Use arrow keys to select a result
6. Press `Enter` — verify navigation occurs
7. Press `Escape` — verify palette closes

---

## Verify: API Client

```typescript
// In browser console or test file:
import { createApiClient } from '@/lib/api';
const api = createApiClient(process.env.NEXT_PUBLIC_API_URL);

// Test JWT injection
const result = await api.get('/api/v1/workspaces');
// Inspect: Network tab should show Authorization: Bearer <token> header

// Test 401 refresh flow
// 1. Manually expire access token in auth store
// 2. Make a request — verify no error thrown, token auto-refreshed
// 3. Check auth store — access token updated
```

---

## Verify: WebSocket Connection

1. Open browser DevTools → Network → WS tab
2. Load the application
3. Verify a WebSocket connection is established to `NEXT_PUBLIC_WS_URL`
4. Open DevTools console and run:

```javascript
// Connection state indicator should show green dot
// To test reconnection:
// 1. Shut down the backend WebSocket server
// 2. Verify "Reconnecting..." indicator appears in header
// 3. Restart the backend
// 4. Verify connection restored and indicator returns to green
```

---

## Verify: Shared Components (Storybook / Dev Page)

A development-only page at `/dev/components` renders all shared components with sample data.

```bash
# Access in development only (NEXT_PUBLIC_APP_ENV=development):
open http://localhost:3000/dev/components
```

Verify:
- DataTable: renders sample rows, sort/filter/pagination works
- StatusBadge: all 6 variants visible
- MetricCard: shows value + trend + sparkline
- ScoreGauge: renders at 3 sizes, color thresholds correct
- CodeBlock: syntax highlighting, copy button works
- JsonViewer: tree renders, expand/collapse works, copy works
- ConfirmDialog: opens on button click, requires explicit confirmation

Toggle dark mode — verify ALL components update without visual artifacts.

---

## Verify: State Management

```typescript
// Auth store
import { useAuthStore } from '@/store/auth-store';
const { user, isAuthenticated, refreshToken } = useAuthStore.getState();

// After login: user and isAuthenticated should be set
// refreshToken should be persisted in localStorage under key "auth-storage"
// accessToken should NOT be in localStorage

// Workspace store
import { useWorkspaceStore } from '@/store/workspace-store';
const { currentWorkspace } = useWorkspaceStore.getState();

// Call setCurrentWorkspace — all TanStack Query caches should invalidate
// (check React Query DevTools network waterfall for refetch activity)
```

---

## Run Tests

```bash
# Unit + component tests (Vitest)
pnpm test

# Watch mode
pnpm test:watch

# Coverage report
pnpm test:coverage
# Coverage threshold: 95% for lib/ and store/ modules

# E2E tests (Playwright)
pnpm test:e2e
# Requires application running on localhost:3000
```

---

## Build Verification

```bash
pnpm build
# Expected: 0 TypeScript errors, 0 ESLint errors
# Build output: .next/
# Key bundle size targets: First Load JS < 200kB for main route

pnpm start
# Verify production build serves correctly
```
