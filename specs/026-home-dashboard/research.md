# Research: Home Dashboard

**Branch**: `026-home-dashboard` | **Date**: 2026-04-11 | **Phase**: 0

## Decision Log

### Decision 1 — Page Route Location
- **Decision**: `apps/web/app/(main)/home/page.tsx` — a React Server Component (RSC) wrapper that immediately defers to a `HomeDashboard` client component for interactivity.
- **Rationale**: Next.js 14+ App Router convention within the existing `(main)` route group (established in feature 015 scaffold). The RSC outer shell can prefetch initial data on the server; the client component (`"use client"`) owns WebSocket subscriptions and interactive state. Route group `(main)` provides the authenticated app shell layout (sidebar, topnav) automatically.
- **Alternatives considered**: Full client component page — rejected because RSC allows initial data prefetch without client-side flash. Full RSC with no client component — rejected because WebSocket subscriptions require client-side lifecycle.

### Decision 2 — Component Organization
- **Decision**: Feature components live in `apps/web/components/features/home/`. Four sub-components, each independently composable: `WorkspaceSummary`, `RecentActivity`, `PendingActions`, `QuickActions`. The page assembles them. A shared `DashboardLayout` wrapper handles the responsive grid.
- **Rationale**: Feature-grouped components (established in feature 015) keep related code together. Each sub-component is independently testable with mocked data. Matches the pattern from the existing scaffold (`components/features/auth/`, etc.).
- **Alternatives considered**: Co-located in `app/(main)/home/_components/` — rejected because the existing scaffold uses `components/features/` for reusable feature components, and some components (e.g., `RecentActivity`) may be reused in workspace-specific views.

### Decision 3 — Server State: TanStack Query
- **Decision**: Four TanStack Query `useQuery` hooks, one per dashboard section: `useWorkspaceSummary`, `useRecentActivity`, `usePendingActions`. All defined in `apps/web/lib/hooks/use-home-data.ts`. Query keys use the workspace ID for scoped caching. `staleTime: 30_000` (30s) to avoid excessive refetching; `refetchInterval: 30_000` as fallback polling when WebSocket is disconnected.
- **Rationale**: Constitution mandate: TanStack Query for all server state; never `useEffect + useState` for data fetching. 30s stale time matches the WebSocket fallback polling interval from spec FR-018. Query invalidation on WebSocket events provides real-time updates without polling overhead when connected.
- **Alternatives considered**: `useSuspenseQuery` for all sections — rejected because per-section error boundaries with independent loading states (FR-013 partial failure isolation) require regular `useQuery` with per-query error handling. Server-side `fetch` in RSC — rejected because the data must be reactive (WebSocket-updated).

### Decision 4 — Real-Time Updates: WebSocket Integration
- **Decision**: Subscribe to three WebSocket channels on mount (from the existing `lib/ws.ts` WebSocketClient, feature 015): `execution` (execution state changes), `interaction` (new interactions/attention), `workspace` (approval/metric changes). On relevant events, call `queryClient.invalidateQueries()` for the affected query key. Connection state tracked in a `useWebSocketStatus` hook that exposes `isConnected: boolean`.
- **Rationale**: The existing `WebSocketClient` (feature 015) handles reconnection, backoff, and per-topic subscriptions. Using `queryClient.invalidateQueries()` rather than manually setting query data is simpler, avoids optimistic update bugs, and ensures consistency. Three channels cover all dashboard update scenarios.
- **Alternatives considered**: Manual query data patching on WebSocket events — rejected as error-prone (requires matching server response shape exactly). Zustand for WebSocket state — rejected because the data is server state (belongs in TanStack Query); only connection status is client state.

### Decision 5 — Client State: Zustand
- **Decision**: No new Zustand store is needed. The dashboard reads `workspace_id` from the existing `useWorkspaceStore()` (feature 015 scaffold). When `workspace_id` changes (user switches workspace), all `useQuery` keys include `workspace_id` and automatically refetch.
- **Rationale**: The workspace context is already managed by the existing Zustand workspace store (feature 015). Adding a new store for dashboard-only state would violate the "no unnecessary state" principle — query cache handles all server data, and workspace context is global.
- **Alternatives considered**: Dashboard-specific Zustand slice for section expansion/collapse — rejected as unnecessary for the current spec scope.

### Decision 6 — Shared Components Reuse
- **Decision**: Reuse these components from the feature 015 scaffold without modification:
  - `Timeline` — for the recent activity feed
  - `MetricCard` — for the workspace summary grid
  - `StatusBadge` — for activity/delivery status labels
  - `EmptyState` — for zero-data states in all sections
  - `WebSocketClient` (`lib/ws.ts`) — for real-time subscriptions
  - `lib/api.ts` fetch wrapper — for all API calls
- **Rationale**: These were explicitly built as shared components in feature 015. Reusing them ensures visual consistency and avoids duplicating component implementations. The `Timeline` and `MetricCard` components accept generic data shapes via props.
- **Alternatives considered**: Custom timeline implementation — rejected; the existing Timeline component meets all spec requirements. Inline fetch instead of `lib/api.ts` — rejected (constitution: use existing infrastructure).

### Decision 7 — Pending Actions: Inline Actions
- **Decision**: Approve/reject actions on pending approval cards use TanStack Query `useMutation`. On success, `queryClient.invalidateQueries(['pending-actions', workspace_id])`. Card optimistically removes itself from the list during mutation (optimistic update). Navigation actions use Next.js `useRouter().push()`.
- **Rationale**: `useMutation` is the correct TanStack Query pattern for write operations. Optimistic removal prevents the awkward "I clicked approve but the card is still here" experience. `useRouter` for navigation is the Next.js App Router standard.
- **Alternatives considered**: `fetch` directly without TanStack mutation — rejected (violates TanStack Query mandate for all server state operations). Server action — rejected as unnecessary complexity for a simple API call.

### Decision 8 — Responsive Layout
- **Decision**: Metric cards: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4`. Activity + pending actions: single column on mobile, two columns (`lg:grid-cols-2`) on desktop. Quick actions: `flex flex-wrap gap-2` row on all screen sizes. No custom CSS — Tailwind responsive prefixes only.
- **Rationale**: Constitution: Tailwind utility classes only, no custom CSS files (except `globals.css`). The responsive grid approach matches the scaffold's existing DataTable and MetricCard usage patterns.
- **Alternatives considered**: CSS Grid with named areas — rejected (requires custom CSS). Flex-only layout — rejected; CSS Grid with Tailwind `grid-cols-*` is more predictable for card alignment.

### Decision 9 — Empty States and Error States
- **Decision**: Each section has its own error boundary (`<ErrorBoundary fallback={<SectionError />}>`). On `useQuery` error, the section shows a `SectionError` component with a retry button that calls `refetch()`. Empty states use the existing `EmptyState` component from feature 015 with section-specific copy. Loading states use Tailwind `animate-pulse` skeleton divs, not a global spinner.
- **Rationale**: FR-013 mandates partial failure isolation. Per-section error boundaries prevent one failing API from blocking the entire dashboard. Skeleton loading (not spinners) matches modern dashboard UX conventions and prevents layout shift.
- **Alternatives considered**: Single page-level error boundary — rejected (violates FR-013 partial failure requirement). Global spinner during initial load — rejected (poor UX for a multi-section dashboard; sections should load independently).

### Decision 10 — API Endpoints Consumed
- **Decision**: Four backend API endpoints consumed by the dashboard:
  1. `GET /api/v1/workspaces/{ws_id}/analytics/summary` — workspace summary metrics (active agents, running executions, pending approvals count, cost) from analytics BC (feature 020) 
  2. `GET /api/v1/workspaces/{ws_id}/interactions?sort=created_at:desc&limit=10` — recent interactions from interactions BC (feature 024)
  3. `GET /api/v1/workspaces/{ws_id}/executions?sort=created_at:desc&limit=10` — recent executions from execution BC
  4. `GET /api/v1/workspaces/{ws_id}/pending-actions` — combined endpoint returning pending approvals, failed executions, and attention requests sorted by urgency
- **Rationale**: Pulling from the canonical bounded-context endpoints avoids data duplication. The `pending-actions` endpoint is a BFF (Backend for Frontend) aggregation endpoint that merges approvals, failed executions, and attention requests into a single urgency-sorted list — matching the dashboard's exact data need without multiple waterfall requests.
- **Alternatives considered**: Three separate API calls (approvals + failed executions + attention) — rejected as waterfall fetching hurts the 2-second load SC-001 target; a single combined endpoint is more efficient. GraphQL aggregation — rejected; the platform uses REST throughout.

### Decision 11 — Testing Strategy
- **Decision**: Vitest + React Testing Library (RTL) for component unit tests + interaction tests. MSW (Mock Service Worker) for API mocking in tests. Playwright for e2e tests (full dashboard render + real-time update simulation). Test coverage target: 95% per spec SC-009.
- **Rationale**: Feature 015 scaffold established Vitest + RTL + Playwright + MSW as the frontend testing stack. No new tooling needed.
- **Alternatives considered**: Jest instead of Vitest — rejected; scaffold uses Vitest. Cypress instead of Playwright — rejected; scaffold uses Playwright.

### Decision 12 — Connection Status Indicator
- **Decision**: A `ConnectionStatusBanner` component renders a small non-intrusive banner at the top of the dashboard (below the page header) when `isConnected === false`. Banner text: "Live updates paused — reconnecting…". Disappears automatically when connection is restored. The banner uses Tailwind `transition-all` for smooth appear/disappear. No persistent WebSocket status in the sidebar or topnav (scope: dashboard page only, per spec).
- **Rationale**: Spec FR-018 requires a connection indicator but does not mandate where or how prominent. A non-intrusive top-of-section banner is less alarming than a sidebar status while still being clearly visible. `transition-all` prevents jarring flashes.
- **Alternatives considered**: Toast notification — rejected as toasts are transient and the connection state may persist; a persistent banner is more appropriate. Sidebar status icon — rejected; the spec scopes the indicator to the dashboard, not a global status.
