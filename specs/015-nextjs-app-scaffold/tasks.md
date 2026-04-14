# Tasks: Next.js Application Scaffold

**Input**: Design documents from `/specs/015-nextjs-app-scaffold/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ui-contracts.md ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)
- Tests included per spec requirement: "Test coverage ≥95% (if applicable)"

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Initialize the Next.js project, configure tooling, and establish the dev environment. Unblocks all subsequent phases.

- [X] T001 Initialize Next.js 14+ App Router project in `apps/web/` with `pnpm create next-app` — TypeScript strict mode, Tailwind CSS, App Router, no src/ directory, import alias `@/*`
- [X] T002 Configure `apps/web/tsconfig.json` with `strict: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`, path alias `@/*` → `./`
- [X] T003 [P] Configure `apps/web/tailwind.config.ts` — extend theme with CSS variable tokens (`--primary`, `--secondary`, `--brand-primary`, `--brand-secondary`, `--brand-accent`), `darkMode: 'class'`, custom spacing scale
- [X] T004 [P] Configure ESLint in `apps/web/eslint.config.mjs` — extend `next/core-web-vitals` + `@typescript-eslint/recommended-strict`
- [X] T005 Initialize shadcn/ui in `apps/web/` — run `npx shadcn init` with New York style, CSS variables theme, add all core primitives: `button card badge input select dropdown-menu dialog alert-dialog command sheet table tabs tooltip popover collapsible breadcrumb skeleton avatar separator scroll-area`
- [X] T006 Configure Vitest in `apps/web/vitest.config.ts` — jsdom environment, path aliases matching tsconfig, setup file `vitest.setup.ts` (RTL matchers + MSW server lifecycle)
- [X] T007 [P] Configure Playwright in `apps/web/playwright.config.ts` — base URL `http://localhost:3000`, Chromium + Firefox, screenshot on failure
- [X] T008 Create `apps/web/.env.example` with all required env vars: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, `NEXT_PUBLIC_APP_ENV`

**Checkpoint**: `pnpm build` completes with 0 errors. `pnpm test` runner starts successfully.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: TypeScript type definitions, query client, and MSW mock infrastructure — required by ALL user stories.

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [X] T009 [P] Write `apps/web/types/auth.ts` — `RoleType` union (10 values), `UserProfile`, `AuthState`, `TokenPair` interfaces per data-model.md
- [X] T010 [P] Write `apps/web/types/workspace.ts` — `Workspace`, `WorkspaceState` interfaces per data-model.md
- [X] T011 [P] Write `apps/web/types/api.ts` — `ApiError` class (extends Error, code/status/details), `ApiErrorPayload`, `PaginatedResponse<T>`, `CursorPaginatedResponse<T>`, `ApiRequestOptions` per data-model.md
- [X] T012 [P] Write `apps/web/types/navigation.ts` — `NavItem` (id/label/icon/href/requiredRoles/badge/children), `BreadcrumbSegment` per data-model.md
- [X] T013 [P] Write `apps/web/types/websocket.ts` — `WsConnectionState` union, `WsEvent<T>`, `WsMessage`, `WsEventHandler<T>`, `WsUnsubscribeFn` per data-model.md
- [X] T014 Write `apps/web/lib/query-client.ts` — export singleton `QueryClient` with `defaultOptions: { queries: { staleTime: 30_000, gcTime: 300_000, retry: 1 } }` for imperative access from Zustand stores
- [X] T015 Write `apps/web/mocks/handlers.ts` — MSW request handlers for auth endpoints (`POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`) and workspace endpoints (`GET /api/v1/workspaces`) with fixture responses
- [X] T016 Write `apps/web/mocks/browser.ts` — MSW `setupWorker` for browser dev environment; write `apps/web/vitest.setup.ts` — `setupServer` with handlers, `beforeAll`/`afterEach`/`afterAll` lifecycle

**Checkpoint**: All TypeScript types compile. MSW server initializes in test runner without errors.

---

## Phase 3: User Story 1 — Project Setup and Theme Configuration (Priority: P1) 🎯 MVP

**Goal**: Running development server with brand theme, light/dark mode toggle, SSR-safe (no FOIT), responsive layout.

**Independent Test**: `pnpm dev` starts. App renders brand colors. Theme toggle switches all elements to dark mode without page reload. `pnpm build` completes with 0 errors.

### Tests for User Story 1

- [X] T017 [P] [US1] Write Vitest test for ThemeProvider in `apps/web/components/providers/ThemeProvider.test.tsx` — verify theme class applied to `<html>`, verify toggle switches theme, verify SSR-safe `suppressHydrationWarning`
- [X] T018 [P] [US1] Write Playwright E2E smoke test in `apps/web/e2e/theme.spec.ts` — navigate to `/`, verify brand colors rendered, toggle dark mode, verify `.dark` class on `<html>`, verify no FOIT on reload

### Implementation for User Story 1

- [X] T019 [US1] Write `apps/web/app/globals.css` — `:root` CSS custom properties for all shadcn tokens (`--background`, `--foreground`, `--primary`, `--secondary`, `--muted`, `--accent`, `--destructive`, `--border`, `--ring`, `--radius`) + brand tokens (`--brand-primary: 238 84% 58%`, `--brand-secondary: 262 52% 47%`, `--brand-accent: 199 89% 48%`) in HSL format; `.dark` block with dark palette values
- [X] T020 [US1] Write `apps/web/components/providers/ThemeProvider.tsx` — wrap `next-themes` `ThemeProvider` with `attribute="class"`, `defaultTheme="system"`, `enableSystem`, `disableTransitionOnChange`
- [X] T021 [US1] Write `apps/web/components/providers/QueryProvider.tsx` — `QueryClientProvider` wrapping `children`, imports singleton from `lib/query-client.ts`, includes `ReactQueryDevtools` in development only
- [X] T022 [US1] Write root `apps/web/app/layout.tsx` — `<html suppressHydrationWarning>`, wraps `ThemeProvider` → `QueryProvider` → `WebSocketProvider` (stub for now) → `{children}`, includes `globals.css` import, sets metadata
- [X] T023 [US1] Create route group structure: `apps/web/app/(auth)/layout.tsx` (plain layout, no shell), `apps/web/app/(auth)/login/page.tsx` (placeholder: "Login page — coming soon"), `apps/web/app/(main)/page.tsx` (placeholder dashboard)
- [X] T024 [US1] Write `apps/web/next.config.ts` — TypeScript strict mode enforced, `reactStrictMode: true`, `poweredByHeader: false`

**Checkpoint**: `pnpm dev` → `http://localhost:3000` renders with brand colors. Dark mode toggle works. `pnpm build` passes. Theme test T017/T018 pass.

---

## Phase 4: User Story 3 — API Communication Layer (Priority: P1)

**Goal**: Typed fetch client with JWT injection, transparent token refresh on 401, 3× exponential backoff retry, ApiError normalization, TanStack Query factory hooks.

**Independent Test**: Call `api.get('/api/v1/workspaces')` — verify `Authorization: Bearer <token>` header in DevTools. Simulate 401 → verify token refreshed and request retried. Simulate network error → verify 3 retries with backoff.

### Tests for User Story 3

- [X] T025 [P] [US3] Write Vitest unit tests for `lib/api.ts` in `apps/web/lib/api.test.ts` — test JWT injection, 401 refresh-and-retry flow, 2nd 401 redirects to login, network error retry with backoff, ApiError normalization from `{"error": {...}}` responses, typed generic methods
- [X] T026 [P] [US3] Write Vitest unit tests for `lib/auth.ts` in `apps/web/lib/auth.test.ts` — test `refreshAccessToken()` success path (updates store, returns TokenPair), test failure path (clears auth, would redirect to login), test concurrent refresh deduplification

### Implementation for User Story 3

- [X] T027 [US3] Write `apps/web/lib/api.ts` — `createApiClient(baseUrl)` factory: typed `get<T>/post<T>/put<T>/patch<T>/delete<T>` methods; request interceptor reads `useAuthStore.getState().accessToken` and injects `Authorization: Bearer`; response interceptor calls `refreshAccessToken()` on 401 then retries once; on 2nd 401 calls `clearAuth()` and redirects to `/login`; network error retry up to 3× with exponential backoff (1000ms, 2000ms, 4000ms); transforms `{"error": {...}}` into `ApiError` instances with `code`, `status`, `details` fields
- [X] T028 [US3] Write `apps/web/lib/auth.ts` — `refreshAccessToken()`: reads `refreshToken` from `useAuthStore.getState()`, POSTs to `/api/v1/auth/refresh` using raw fetch (no client interceptor to avoid loops), on success calls `useAuthStore.getState().setTokens()`, returns `TokenPair`; on failure calls `clearAuth()` and redirects to `/login`; deduplifies concurrent calls (returns existing in-flight Promise)
- [X] T029 [US3] Write `apps/web/lib/hooks/use-api.ts` — factory functions: `useAppQuery<T>(key, fetcher, options?)` wrapping `useQuery` with defaults `staleTime: 30_000, gcTime: 300_000, retry: 1`; `useAppMutation<TData, TVars>(mutationFn, options?)` with `onSuccess` invalidation support; `useAppInfiniteQuery<T>(key, fetcher, options?)` with cursor-based page param

**Checkpoint**: T025/T026 tests pass. Manual test: call API via hook in a test page, verify JWT header in network tab.

---

## Phase 5: User Story 6 — Client-Side State Management (Priority: P2)

**Goal**: Zustand auth store (persists only refreshToken) and workspace store (invalidates queries on workspace switch). State persists across navigations; workspace switch triggers full query refetch.

**⚠️ Note**: US6 is P2 in the spec, but the auth store is required by US2 (app shell sidebar RBAC filtering). Implementing US6 before US2 unblocks US2.

**Independent Test**: Log in (mock) → verify `auth-storage` in localStorage contains `refreshToken` only (no `accessToken`, no `user`). Switch workspace → open React Query DevTools → verify all queries refetch. Log out → verify localStorage cleared.

### Tests for User Story 6

- [X] T030 [P] [US6] Write Vitest unit tests for `store/auth-store.ts` in `apps/web/store/auth-store.test.ts` — test `setTokens` persists only refreshToken to localStorage, test `setUser` updates user profile, test `clearAuth` clears all state including localStorage, test `isAuthenticated` computed from user presence
- [X] T031 [P] [US6] Write Vitest unit tests for `store/workspace-store.ts` in `apps/web/store/workspace-store.test.ts` — test `setCurrentWorkspace` calls `queryClient.invalidateQueries()`, test `setSidebarCollapsed` persists to localStorage, test `setWorkspaceList` updates list without invalidating queries

### Implementation for User Story 6

- [X] T032 [US6] Write `apps/web/store/auth-store.ts` — Zustand store with `user: UserProfile | null`, `accessToken: string | null`, `refreshToken: string | null`, `isAuthenticated: boolean`, `isLoading: boolean`; actions: `setTokens(pair: TokenPair)` sets both tokens + `isAuthenticated: true`, `setUser(user: UserProfile)`, `clearAuth()` resets all fields; `persist` middleware with key `auth-storage`, `partialize: (s) => ({ refreshToken: s.refreshToken })`
- [X] T033 [US6] Write `apps/web/store/workspace-store.ts` — Zustand store with `currentWorkspace: Workspace | null`, `workspaceList: Workspace[]`, `sidebarCollapsed: boolean`, `isLoading: boolean`; actions: `setCurrentWorkspace(ws)` sets workspace and calls `queryClient.invalidateQueries()` (imports from `lib/query-client.ts`), `setWorkspaceList(list)`, `setSidebarCollapsed(v)`; `persist` middleware with key `workspace-storage`, `partialize: (s) => ({ currentWorkspace: s.currentWorkspace, sidebarCollapsed: s.sidebarCollapsed })`

**Checkpoint**: T030/T031 tests pass. Zustand DevTools show both stores with correct initial state. localStorage contains `auth-storage` and `workspace-storage` keys after initialization.

---

## Phase 6: User Story 2 — App Shell and Navigation (Priority: P1)

**Goal**: Persistent app shell with collapsible sidebar (RBAC-filtered nav), header (workspace selector, user menu), breadcrumb, command palette (Cmd+K), auth guard on `(main)` layout.

**Independent Test**: Open app as mock "viewer" user → sidebar shows only viewer-permitted items. Press Cmd+K → command palette opens in ≤100ms. Collapse sidebar → collapses to icons in ≤200ms. Navigate to nested route → breadcrumbs update.

### Tests for User Story 2

- [X] T034 [P] [US2] Write Vitest component tests for Sidebar in `apps/web/components/layout/sidebar/Sidebar.test.tsx` — render with mock auth store (viewer role), verify admin-only items hidden; render with superadmin role, verify all items shown; verify `aria-current="page"` on active route; verify collapse/expand toggles CSS transition class
- [X] T035 [P] [US2] Write Vitest component tests for CommandPalette in `apps/web/components/layout/command-palette/CommandPalette.test.tsx` — verify Cmd+K opens dialog, verify type filters NAV_ITEMS by label, verify selecting item navigates, verify Escape closes
- [X] T036 [P] [US2] Write Playwright E2E test in `apps/web/e2e/app-shell.spec.ts` — verify sidebar renders, collapse/expand animation completes, command palette opens and navigates, breadcrumbs update on nested navigation

### Implementation for User Story 2

- [X] T037 [US2] Write `apps/web/components/layout/sidebar/nav-config.ts` — `NAV_ITEMS: NavItem[]` static array with at minimum: Dashboard (`/`, all roles), Agents (`/agents`, agent_operator/agent_viewer/workspace_admin/superadmin), Workflows (`/workflows`, workspace_editor/workspace_admin/superadmin), Analytics (`/analytics`, analytics_viewer/workspace_admin/superadmin), Policies (`/policies`, policy_manager/superadmin), Trust (`/trust`, trust_officer/superadmin), Settings (`/settings`, workspace_admin/superadmin); also export `QUICK_ACTIONS` array with 3–5 quick action callbacks
- [X] T038 [US2] Write `apps/web/components/layout/sidebar/Sidebar.tsx` — reads `useAuthStore().user.roles`, filters `NAV_ITEMS` where `item.requiredRoles.length === 0 || item.requiredRoles.some(r => roles.includes(r))` (superadmin bypasses); renders shadcn `NavigationMenu` or custom `<nav>`; collapsed state from `useWorkspaceStore().sidebarCollapsed`; CSS `transition-[width]` with `duration-200`; icons from `lucide-react`; `aria-current="page"` on active item; collapse toggle button with `ChevronLeft`/`ChevronRight` icon calling `setSidebarCollapsed`
- [X] T039 [US2] Write `apps/web/components/layout/header/WorkspaceSelector.tsx` — shadcn `DropdownMenu` listing `useWorkspaceStore().workspaceList`; selected item shows current workspace name; selecting calls `setCurrentWorkspace(ws)` from workspace store
- [X] T040 [US2] Write `apps/web/components/layout/header/UserMenu.tsx` — shadcn `DropdownMenu` with `Avatar` (initials fallback from `user.displayName`), shows email, logout menu item calls `clearAuth()` and redirects to `/login`
- [X] T041 [US2] Write `apps/web/components/layout/breadcrumb/Breadcrumb.tsx` — uses `usePathname()` to split path segments, maps to `BreadcrumbSegment[]`, renders shadcn `Breadcrumb` + `BreadcrumbItem` + `BreadcrumbLink`; last segment has `BreadcrumbPage` (no link); empty for root `/`
- [X] T042 [US2] Write `apps/web/components/layout/command-palette/CommandPaletteProvider.tsx` — `createContext` + `useReducer` for `open: boolean`; `useEffect` adds/removes global `keydown` listener for `(e.metaKey || e.ctrlKey) && e.key === 'k'`; exports `useCommandPalette()` hook
- [X] T043 [US2] Write `apps/web/components/layout/command-palette/CommandPalette.tsx` — shadcn `CommandDialog` (wraps cmdk); searches role-filtered `NAV_ITEMS` + `QUICK_ACTIONS`; navigation items execute `router.push(item.href)`; actions execute `action.callback()`; `CommandEmpty` shown when no results
- [X] T044 [US2] Write `apps/web/components/layout/header/Header.tsx` — `<header>` with flex layout: left=`WorkspaceSelector`, center=`Breadcrumb`, right=`ConnectionIndicator` + notifications icon (`Bell` from lucide) + `UserMenu`; height `h-16`; border-bottom via `border-b border-border`
- [X] T045 [US2] Write `apps/web/app/(main)/layout.tsx` — auth guard: reads `useAuthStore().isAuthenticated`; if false, `redirect('/login')`; renders `<CommandPaletteProvider>` → flex container with `<Sidebar>` + `<div className="flex-1 flex flex-col">` → `<Header>` + `<main className="flex-1 overflow-auto p-6">{children}</main>`; sidebar width controlled by `sidebarCollapsed` state

**Checkpoint**: T034/T035/T036 pass. Manual: sidebar renders and RBAC filter works. Sidebar collapses in ≤200ms. Command palette opens in ≤100ms. Breadcrumbs update.

---

## Phase 7: User Story 5 — Shared UI Components Library (Priority: P1)

**Goal**: 11 shared components — all dark-mode-aware, keyboard navigable, accessible, responsive. Rendered in dev showcase page at `/dev/components`.

**Independent Test**: Open `/dev/components` in dev mode. All 11 components render with sample data. Toggle dark mode — all components update correctly. Keyboard-only navigation works for interactive components.

### Tests for User Story 5

- [X] T046 [P] [US5] Write Vitest component tests for DataTable in `apps/web/components/shared/DataTable.test.tsx` — render with sample columns/data, verify sort on column click, verify filter input, verify pagination controls, verify empty state renders `EmptyState`, verify loading skeleton shown
- [X] T047 [P] [US5] Write Vitest component tests for StatusBadge in `apps/web/components/shared/StatusBadge.test.tsx` — verify each `StatusSemantic` maps to correct variant + icon, verify custom label overrides default
- [X] T048 [P] [US5] Write Vitest component tests for MetricCard in `apps/web/components/shared/MetricCard.test.tsx` — verify value/unit rendered, verify trend icon for each direction, verify loading skeleton, verify sparkline renders when data provided
- [X] T049 [P] [US5] Write Vitest component tests for ConfirmDialog in `apps/web/components/shared/ConfirmDialog.test.tsx` — verify opens when `open=true`, verify confirm button calls `onConfirm`, verify loading state disables both buttons, verify destructive variant applies `destructive` class
- [X] T050 [P] [US5] Write Vitest component tests for JsonViewer in `apps/web/components/shared/JsonViewer.test.tsx` — verify root renders expanded, verify nested objects collapsed at maxDepth, verify copy button writes to clipboard, verify null/boolean/number colors applied

### Implementation for User Story 5

- [X] T051 [P] [US5] Write `apps/web/components/shared/StatusBadge.tsx` — maps `StatusSemantic` to shadcn `Badge` variant (`healthy`→`default` + `CheckCircle2`, `warning`→`secondary` + `AlertTriangle`, `error`→`destructive` + `XCircle`, `inactive`→`outline` + `MinusCircle`, `pending`→`outline` + `Clock`, `running`→`default` + spinning `Loader2`); size variants via Tailwind `text-xs/sm/base`; `aria-label` includes status value
- [X] T052 [P] [US5] Write `apps/web/components/shared/EmptyState.tsx` — centered column layout with optional icon, `<h3>` title, `<p>` description, optional `<Button>` CTA; uses shadcn `Button` for CTA; `text-muted-foreground` for description
- [X] T053 [P] [US5] Write `apps/web/components/shared/ConfirmDialog.tsx` — wraps shadcn `AlertDialog`; `variant="destructive"` changes confirm button to destructive; `isLoading` shows `Loader2` spinner in confirm button and disables both buttons; caller responsible for closing via `onOpenChange(false)`
- [X] T054 [US5] Write `apps/web/components/shared/DataTable.tsx` — `useReactTable` from `@tanstack/react-table` with `getCoreRowModel`, `getSortedRowModel`, `getFilteredRowModel`, `getPaginationRowModel`; renders shadcn `Table/TableHeader/TableBody/TableRow/TableHead/TableCell`; sort via `aria-sort` on `<TableHead>`; loading state: 5 skeleton rows via shadcn `Skeleton`; empty state: renders `EmptyState` component; `totalCount` prop switches to server-side pagination (disables `getPaginationRowModel`)
- [X] T055 [P] [US5] Write `apps/web/components/shared/MetricCard.tsx` — shadcn `Card` with `CardHeader` (title + trend icon) and `CardContent` (value + unit + optional Recharts `AreaChart` sparkline 80px height, no axes/grid, `fill="hsl(var(--brand-primary) / 0.2)"`, `stroke="hsl(var(--brand-primary))"`); loading state uses shadcn `Skeleton`; `TrendingUp` (green), `TrendingDown` (red), `Minus` (gray) from lucide
- [X] T056 [P] [US5] Write `apps/web/components/shared/ScoreGauge.tsx` — Recharts `RadialBarChart` in fixed container (80/120/160px per size); single `RadialBar` with `background`; color: `< thresholds.warning` → `hsl(var(--destructive))`, `< thresholds.good` → `hsl(var(--warning))`, `>= thresholds.good` → `hsl(var(--brand-primary))`; score value centered in `<text>` element; optional label below
- [X] T057 [P] [US5] Write `apps/web/components/shared/CodeBlock.tsx` — shadcn `pre` with `rounded-md border border-border bg-muted p-4 overflow-x-auto`; highlight.js loaded via `dynamic(() => import('highlight.js/lib/core'))` + language registration on first render; copy button (`Copy`/`Check` icon, 2s reset) using `navigator.clipboard.writeText`; falls back to plain pre if highlight.js fails; optional `maxHeight` wraps in `overflow-y-auto` container
- [X] T058 [P] [US5] Write `apps/web/components/shared/JsonViewer.tsx` — recursive component using shadcn `Collapsible`; key names in `text-blue-500 dark:text-blue-300`, strings in `text-green-600 dark:text-green-400`, numbers in `text-amber-600 dark:text-amber-300`, booleans in `text-purple-600 dark:text-purple-300`, null in `text-muted-foreground italic`; objects/arrays show `{ N }` / `[ N ]` item count when collapsed; `maxDepth` collapses beyond threshold; copy button on root
- [X] T059 [P] [US5] Write `apps/web/components/shared/Timeline.tsx` — vertical list of `TimelineEvent` items; each renders: timestamp (formatted with `date-fns format`), `StatusBadge` if `event.status` present, label `font-medium`, optional description `text-sm text-muted-foreground`; connected by left-side vertical line using `before:` pseudo-element via Tailwind; loading state via `Skeleton`; `EmptyState` when events empty
- [X] T060 [P] [US5] Write `apps/web/components/shared/SearchInput.tsx` — shadcn `Input` with `Search` icon prefix; debounced via `useEffect` + `setTimeout` (default 300ms); `X` clear button shown when value non-empty; `isLoading` shows `Loader2` spinner instead of search icon; `aria-label` on input
- [X] T061 [P] [US5] Write `apps/web/components/shared/FilterBar.tsx` — horizontal flex row of shadcn `DropdownMenu` or `Popover`+`Checkbox` per filter; multi-select filters use `Checkbox` per option; single-select uses `Select`; active filter count badge on each filter button; "Clear all" button via `onClear` prop when any filter active
- [X] T062 [US5] Write `apps/web/app/(main)/dev/components/page.tsx` — dev-only showcase page (returns 404 in production via `if (process.env.NEXT_PUBLIC_APP_ENV !== 'development') notFound()`); renders all 11 shared components with realistic sample data; includes theme toggle to verify dark mode; groups by component type

**Checkpoint**: T046–T050 tests pass. `/dev/components` renders all 11 components in both light/dark mode. Keyboard navigation works.

---

## Phase 8: User Story 4 — Real-Time Updates via WebSocket (Priority: P2)

**Goal**: Persistent WebSocket connection with topic subscriptions, exponential backoff reconnect (1s→30s), reactive `connectionState`, `ConnectionIndicator` in header.

**Independent Test**: App loads → WebSocket connected (green dot in header). Stop backend WS server → "Reconnecting..." amber indicator appears. Restart server → auto-reconnects, subscriptions restored, green dot returns.

### Tests for User Story 4

- [X] T063 [P] [US4] Write Vitest unit tests for `lib/ws.ts` in `apps/web/lib/ws.test.ts` — mock `WebSocket` constructor; test `subscribe` registers handler and returns unsubscribe fn; test unsubscribe removes handler; test `send` serializes message; test reconnect logic calls `setTimeout` with backoff delays; test `onStateChange` fires on connection state transitions
- [X] T064 [P] [US4] Write Vitest component tests for ConnectionIndicator in `apps/web/components/layout/header/ConnectionIndicator.test.tsx` — verify green dot for `connected`, amber + "Reconnecting..." for `reconnecting`, red + "Disconnected" for `disconnected`, pulsing gray for `connecting`

### Implementation for User Story 4

- [X] T065 [US4] Write `apps/web/lib/ws.ts` — `WebSocketClient` class: constructor takes `url: string`; `connect()` creates `WebSocket(url)`, sets `onopen/onmessage/onclose/onerror` handlers; `onmessage` parses JSON envelope `{ channel, type, payload, timestamp }`, looks up handlers by channel, calls each; `onclose` schedules reconnect via `_scheduleReconnect()` with backoff `[1000,2000,4000,8000,16000,30000]` capped at 30s; `subscribe(channel, handler)` adds to `Map<string, Set<handler>>`, returns `() => set.delete(handler)`; `send(channel, type, payload)` calls `ws.send(JSON.stringify(...))` if connected; `connectionState` getter returns current `_state`; `onStateChange(handler)` adds to state change emitter; `disconnect()` clears reconnect timer + closes socket; on reconnect: replays all current subscriptions
- [X] T066 [US4] Write `apps/web/components/providers/WebSocketProvider.tsx` — creates `WebSocketClient` singleton via `useMemo`; `useEffect` calls `client.connect()` on mount, `client.disconnect()` on unmount; React context provides client instance; exports `useWebSocket()` hook; subscribes to `onStateChange` to re-render context on connection state change
- [X] T067 [US4] Write `apps/web/components/layout/header/ConnectionIndicator.tsx` — `useWebSocket()` to get client; subscribes to connection state via `useEffect` + `client.onStateChange`; `connected`: `<span className="h-2 w-2 rounded-full bg-green-500" />` with tooltip "Connected"; `reconnecting`: amber dot + "Reconnecting..." text; `disconnected`: red dot + "Disconnected" text + retry button (`client.connect()`); `connecting`: pulsing gray dot via `animate-pulse`
- [X] T068 [US4] Replace `WebSocketProvider` stub in `apps/web/app/layout.tsx` with real `WebSocketProvider` from `components/providers/WebSocketProvider.tsx`

**Checkpoint**: T063/T064 tests pass. Manual: green dot in header. Stop WS server → amber indicator. Restart → green dot returns, no manual refresh.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Error boundaries, final integration, coverage audit, build verification.

- [X] T069 Write `apps/web/app/error.tsx` — React error boundary with `useEffect` to log error; renders shadcn `Card` with `AlertTriangle` icon, error title, optional `error.message` in dev mode, "Try again" button calling `reset()`; `app/(main)/error.tsx` to scope boundary to main layout
- [X] T070 [P] Run full TypeScript check: `pnpm tsc --noEmit` — fix ALL errors until output is clean
- [X] T071 [P] Run ESLint: `pnpm next lint` — fix ALL warnings and errors until output is clean
- [X] T072 Run Vitest coverage: `pnpm test:coverage` — ensure `lib/` and `store/` modules hit ≥95% coverage; add missing test cases for any gaps in `lib/api.ts`, `lib/ws.ts`, `lib/auth.ts`, `store/auth-store.ts`, `store/workspace-store.ts`
- [X] T073 [P] Write `apps/web/e2e/full-flow.spec.ts` Playwright test — full flow: navigate to app → auth guard redirects to login → mock login (via MSW) → app shell renders → sidebar RBAC visible → collapse sidebar → open command palette → navigate via palette → verify breadcrumbs update → toggle dark mode
- [X] T074 Run `pnpm build` — verify First Load JS for main route < 200kB; if exceeded, identify large imports (highlight.js, recharts) and add dynamic imports where not already done
- [X] T075 Verify quickstart.md steps all pass end-to-end per `specs/015-nextjs-app-scaffold/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Requires Phase 1 complete — blocks ALL user story phases
- **Phase 3 (US1)**: Requires Phase 2 — foundational types needed for providers
- **Phase 4 (US3)**: Requires Phase 2 + Phase 3 partial (root layout, providers) — auth store stub needed for interceptor
- **Phase 5 (US6)**: Requires Phase 4 — workspace store depends on `queryClient` singleton from US3; auth store depends on `TokenPair` type used in API client
- **Phase 6 (US2)**: Requires Phase 5 — sidebar RBAC filter reads auth store; workspace selector reads workspace store
- **Phase 7 (US5)**: Requires Phase 2 — independent of US2/US3/US6 (only depends on shadcn types). **Can run in parallel with Phase 6.**
- **Phase 8 (US4)**: Requires Phase 3 (root layout for provider mount). **Can run in parallel with Phase 6 and Phase 7.**
- **Phase 9 (Polish)**: Requires all phases complete

### User Story Dependencies

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational: types + MSW)
    ↓
Phase 3 (US1: theme, route groups, providers)
    ↓
Phase 4 (US3: API client, auth.ts, hooks)
    ↓
Phase 5 (US6: Zustand stores)
    ↓
Phase 6 (US2: App shell) ←─ can also run concurrently with Phase 7 + Phase 8
Phase 7 (US5: Shared components) ←─ parallel with Phase 6 + Phase 8
Phase 8 (US4: WebSocket) ←─ parallel with Phase 6 + Phase 7
    ↓
Phase 9 (Polish)
```

### Within Each Phase

- All [P]-marked tasks within a phase operate on different files — safe to parallelize
- Non-[P] tasks depend on prior tasks in the same phase
- Tests for each story should be written before implementation tasks when following TDD

---

## Parallel Opportunities

### Phase 2 — Foundational (all 5 type files independent)

```
Parallel:
  T009 types/auth.ts
  T010 types/workspace.ts
  T011 types/api.ts
  T012 types/navigation.ts
  T013 types/websocket.ts
Sequential after types:
  T014 lib/query-client.ts → T015 mocks/handlers.ts → T016 vitest.setup.ts
```

### Phase 6 — App Shell (most components independent)

```
After T045 (main layout) is started:
Parallel:
  T037 nav-config.ts
  T039 WorkspaceSelector.tsx
  T040 UserMenu.tsx
  T041 Breadcrumb.tsx
  T042 CommandPaletteProvider.tsx
Sequential:
  T037 → T038 Sidebar.tsx
  T042 → T043 CommandPalette.tsx
  T039 + T040 + T041 + T043 → T044 Header.tsx
  T038 + T044 → T045 (main)/layout.tsx
```

### Phase 7 — Shared Components (all 11 components independent)

```
All parallel (T051–T061 operate on different files):
  T051 StatusBadge, T052 EmptyState, T053 ConfirmDialog,
  T054 DataTable (depends on T052), T055 MetricCard,
  T056 ScoreGauge, T057 CodeBlock, T058 JsonViewer,
  T059 Timeline (depends on T051+T052), T060 SearchInput,
  T061 FilterBar
Then:
  T062 dev/components showcase page (depends on all above)
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 3 only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 (theme, project structure) → **build passes, app renders**
4. Complete Phase 4: US3 (API client + hooks) → **typed API communication works**
5. **STOP and VALIDATE**: build passes, API client tests pass, dark mode works
6. Deploy / demo with placeholder pages

### Incremental Delivery

1. Setup + Foundational → project boots
2. US1 → themed app renders in light/dark
3. US3 → typed API client working
4. US6 → persistent auth/workspace state
5. US2 → navigable app shell with RBAC sidebar **(demo-ready)**
6. US5 → full component library **(development-ready for bounded contexts)**
7. US4 → real-time WebSocket **(production-ready)**
8. Polish → coverage + bundle size verified

### Parallel Team Strategy

After Phase 5 (US6) completes:
- **Developer A**: Phase 6 — App Shell (US2)
- **Developer B**: Phase 7 — Shared Components (US5)
- **Developer C**: Phase 8 — WebSocket (US4)

All three unblock independently once Zustand stores exist.

---

## Notes

- [P] tasks operate on distinct files — safe to parallelize within a phase
- Each phase ends with a **Checkpoint** — validate before proceeding
- US6 (P2) implemented before US2 (P1) due to dependency: sidebar RBAC filter requires auth store
- WebSocketProvider added as stub in T022 (root layout) to avoid circular dependency; replaced with real implementation in T068
- highlight.js in CodeBlock (T057) must be `dynamic(() => import(...))` to avoid server-side bundle bloat
- `lib/auth.ts` refreshAccessToken must NOT use `createApiClient()` — must use raw `fetch` to avoid interceptor loop
- Zustand `setCurrentWorkspace` calls `queryClient.invalidateQueries()` synchronously — `queryClient` imported from `lib/query-client.ts` (not from TanStack Query hooks to avoid React context dependency)
