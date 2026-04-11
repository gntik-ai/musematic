# Research: Next.js Application Scaffold — Frontend Foundation

**Feature**: 015-nextjs-app-scaffold  
**Date**: 2026-04-11  
**Phase**: 0 — Pre-design research

---

## Decision 1: Next.js App Router Layout — Route Groups for Shell Separation

**Decision**: Use a route group `(main)` for all authenticated shell-wrapped pages and `(auth)` for unauthenticated pages (login, etc.). The root layout `app/layout.tsx` sets up providers (QueryClientProvider, ThemeProvider). The `(main)/layout.tsx` renders the AppShell and guards for authentication. This prevents the app shell from appearing on login/error pages.

**Rationale**: Constitution mandates Next.js 14+ App Router. Route groups allow different layouts for authenticated vs. unauthenticated pages without affecting URL paths. This is the canonical App Router pattern for dashboard applications. The user input specifies `app/(main)/` as the target structure.

**Alternatives considered**:
- Single root layout with conditional shell rendering: Causes layout flash on unauthenticated pages. Rejected.
- Pages Router: Constitution mandates App Router. Rejected.
- Middleware-only auth guard: Middleware can't access Zustand; layout-level guard is more composable. Rejected.

---

## Decision 2: Tailwind Theme — CSS Custom Properties with shadcn/ui Token Mapping

**Decision**: Define brand colors as HSL values in `globals.css` as CSS custom properties under `:root` (light) and `.dark` (dark). shadcn/ui maps its design tokens to these properties. Custom additions: `--brand-primary`, `--brand-secondary`, `--brand-accent`. Tailwind config extends with semantic token names mapping to the CSS vars. Dark mode via `class` strategy (toggled by `next-themes`).

**Rationale**: Constitution mandates shadcn/ui for all primitives and Tailwind CSS for styling. shadcn/ui uses CSS variables for theming by default — this allows a single toggle to switch all components between light and dark without JavaScript-in-CSS. `next-themes` provides SSR-safe theme toggling with no flash of incorrect theme (FOIT).

**Alternatives considered**:
- Tailwind `dark:` variants only: Requires duplicating styles for dark mode on every component. CSS vars + class strategy is DRY. Rejected.
- Inline styles for brand colors: Breaks the utility-class model. Rejected.
- Hardcoded hex colors: Non-semantic; dark mode would require full stylesheet duplication. Rejected.

---

## Decision 3: API Client — Fetch Wrapper with Interceptor Pattern

**Decision**: `lib/api.ts` exports a `createApiClient(baseUrl: string)` factory returning a typed client object. Internally wraps `fetch` with:
1. **Request interceptor**: Reads access token from `useAuthStore.getState()`, injects `Authorization: Bearer` header.
2. **Response interceptor**: On 401, calls `lib/auth.ts` `refreshAccessToken()`, retries once. On 2nd 401 → redirect to login.
3. **Retry logic**: On network errors (`TypeError`), retries up to 3 times with exponential backoff (1s, 2s, 4s).
4. **Error normalization**: Transforms API error responses (`{"error": {"code", "message", "details"}}`) into typed `ApiError` class instances.
5. **Type safety**: Methods `get<T>`, `post<T>`, `put<T>`, `patch<T>`, `delete<T>` return `Promise<T>`.

**Rationale**: Constitution mandates `httpx` on Python side; frontend mirror should be equally typed and robust. Avoiding third-party HTTP client libraries (axios, ky) keeps the bundle lean and aligns with constitution's "no alternative component libraries" preference. The interceptor pattern matches TanStack Query's `queryFn` expectations.

**Alternatives considered**:
- axios: External dependency; `fetch` is now sufficient with our wrapper. Rejected.
- tRPC: Requires tRPC server setup on Next.js; we're consuming a Python FastAPI backend. Rejected.
- SWR instead of TanStack Query: Constitution mandates TanStack Query v5. Rejected.

---

## Decision 4: WebSocket Client — Event-Driven with Topic Subscriptions

**Decision**: `lib/ws.ts` exports `WebSocketClient` class:
- Constructor takes `url: string`.
- Manages single `WebSocket` instance with auto-reconnect (exponential backoff: 1s, 2s, 4s, 8s, cap 30s).
- `subscribe(channel: string, handler: (event: WsEvent) => void) → () => void` returns unsubscribe function.
- `send(channel: string, payload: unknown) → void` serializes and sends.
- `connectionState: 'connecting' | 'connected' | 'disconnected' | 'reconnecting'` — reactive (emits state change events).
- On reconnect: replays all active subscriptions.
- Messages follow `{ channel: string; type: string; payload: unknown }` envelope.

A React context `WebSocketProvider` wraps the app and exposes the client via `useWebSocket()` hook. Individual components subscribe/unsubscribe in `useEffect`.

**Rationale**: Constitution mandates "Native WebSocket API with reconnection wrapper". The topic/channel model aligns with the Kafka event model on the backend (`auth.events`, `runtime.lifecycle`, etc.). The unsubscribe pattern prevents memory leaks in React components.

**Alternatives considered**:
- Socket.IO: Heavier protocol with its own server requirements. Constitution mandates native WebSocket. Rejected.
- Server-Sent Events: Unidirectional; platform needs bidirectional real-time. Rejected.
- Per-component WebSocket connections: Wastes connections; single shared connection is more efficient. Rejected.

---

## Decision 5: Zustand Store Design — Slice Pattern with Persistence

**Decision**: Two stores:

1. **`auth-store.ts`**: `AuthState` with `user: UserProfile | null`, `accessToken: string | null`, `refreshToken: string | null`, `isAuthenticated: boolean`. Actions: `setTokens`, `setUser`, `clearAuth`. Persisted to `localStorage` via `zustand/middleware persist` (only `refreshToken` persisted; access token is re-acquired on page load).

2. **`workspace-store.ts`**: `WorkspaceState` with `currentWorkspace: Workspace | null`, `workspaceList: Workspace[]`. Actions: `setCurrentWorkspace`, `setWorkspaceList`. When `setCurrentWorkspace` is called, invokes `queryClient.invalidateQueries()` to refetch all workspace-scoped data. Persisted to `localStorage` (workspace preference).

**Rationale**: Constitution mandates Zustand 5.x for client state. Only `refreshToken` is persisted (not access token) — access tokens should be short-lived and re-acquired on load. Workspace preference persisted so users don't lose their selection on refresh. Query invalidation on workspace switch ensures fresh data per workspace.

**Alternatives considered**:
- Redux Toolkit: Heavier; constitution mandates Zustand. Rejected.
- React Context for workspace: Does not persist; causes prop drilling. Rejected.
- Persisting access tokens: Security risk — short-lived tokens should not be in localStorage. Rejected.

---

## Decision 6: TanStack Query v5 Integration — Factory Hook Pattern

**Decision**: `lib/hooks/use-api.ts` exports factory functions that create typed hooks:
- `useQuery<T>(key: QueryKey, fetcher: () => Promise<T>, options?)` — thin wrapper for read operations with sane defaults (staleTime: 30s, gcTime: 5min).
- `useMutation<TData, TVars>(mutationFn, options?)` — with automatic query invalidation on success.
- `useInfiniteQuery<T>(key, fetcher, options?)` — for paginated lists.

The `QueryClientProvider` is in `app/layout.tsx`. `queryClient` is exported from `lib/query-client.ts` for imperative invalidation from Zustand actions.

**Rationale**: Constitution mandates TanStack Query v5 for all API data fetching. Factory hooks enforce consistent defaults (caching times, error handling) across all bounded context features. Exporting the `queryClient` singleton allows Zustand's workspace store to invalidate queries imperatively on workspace switch.

**Alternatives considered**:
- useEffect + useState for data fetching: Constitution explicitly forbids this pattern. Rejected.
- Per-bounded-context query clients: Breaks shared cache invalidation. Rejected.
- React Query v4: Constitution mandates v5. Rejected.

---

## Decision 7: Sidebar Navigation — Static Config with RBAC Filter

**Decision**: `components/layout/sidebar/nav-config.ts` exports `NAV_ITEMS: NavItem[]` — a static array of navigation items with `{ label, icon, href, requiredRoles: RoleType[] }`. The `Sidebar` component reads the current user's roles from `useAuthStore()` and filters items where `item.requiredRoles.some(r => userRoles.includes(r))`. Superadmin sees all items.

Sidebar collapse state managed in `workspace-store.ts` (`sidebarCollapsed: boolean`). Collapsed state persists to localStorage.

**Rationale**: Client-side role filtering is appropriate for navigation visibility — it's UX, not security. The actual API endpoints enforce RBAC on the backend. Static nav config is simple, type-safe, and easy to extend. Constitution mandates Zustand for client state — sidebar collapse belongs there.

**Alternatives considered**:
- Server-fetched nav items: Adds latency and complexity; nav items don't change per request. Rejected.
- Dynamic role definitions: Too complex for a scaffold; predefined role-to-nav mapping is sufficient. Rejected.
- React Context for sidebar state: Doesn't persist. Rejected.

---

## Decision 8: Command Palette — cmdk via shadcn/ui Command Component

**Decision**: Use the shadcn/ui `Command` component (which wraps `cmdk`) for the command palette. Opened via `Cmd+K` (Mac) / `Ctrl+K` (Windows/Linux) using a global `useEffect` keydown listener in the `CommandPaletteProvider`. The palette searches `NAV_ITEMS` and a static list of quick actions. Results are filtered client-side. Navigation items open their route; actions execute callbacks.

**Rationale**: Constitution mandates shadcn/ui for all UI primitives. shadcn/ui's `Command` component provides the full command palette UI including keyboard navigation, fuzzy search, and grouping. `cmdk` is the underlying library used by shadcn/ui Command.

**Alternatives considered**:
- Custom fuzzy search: Reinvents what cmdk already provides. Rejected.
- kbar: Alternative command palette library; constitution mandates shadcn/ui. Rejected.
- Spotlight-style with API-backed search: Platform content search is a separate feature. Rejected for this scaffold.

---

## Decision 9: Shared Component Patterns — Composition over Configuration

**Decision**: All shared components live in `components/shared/`. Each component is a single file exporting a single named export (e.g., `DataTable`). Props interfaces are defined in the same file. Components use shadcn/ui primitives exclusively (no raw HTML elements where a primitive exists). Dark mode is handled by the CSS variable theme — components need no dark mode logic.

Key component decisions:
- **DataTable**: wraps shadcn/ui `Table` + TanStack Table v8 for sort/filter/pagination state management.
- **MetricCard**: uses shadcn/ui `Card` + Recharts `SparklineChart` (custom thin wrapper).
- **StatusBadge**: shadcn/ui `Badge` with variant mapping (healthy→success, warning→warning, error→destructive).
- **ScoreGauge**: Recharts `RadialBarChart` in a 120px × 120px container.
- **CodeBlock**: shadcn/ui `pre` + `highlight.js` for syntax highlighting (loaded lazily).
- **JsonViewer**: custom tree renderer using shadcn/ui `Collapsible` for expand/collapse.
- **ConfirmDialog**: shadcn/ui `AlertDialog`.

**Rationale**: Constitution mandates shadcn/ui for all UI primitives. Composition over configuration keeps components focused and testable. TanStack Table v8 is the standard for complex tables — it pairs naturally with TanStack Query.

**Alternatives considered**:
- AG Grid: Commercial license; constitution mandates shadcn/ui primitives. Rejected.
- react-table v7: Outdated; TanStack Table v8 is the successor. Rejected.
- CSS Modules: Constitution mandates Tailwind utility classes. Rejected.

---

## Decision 10: TypeScript Configuration — Strict with Path Aliases

**Decision**: `tsconfig.json` with `strict: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`. Path aliases: `@/*` → `./` (root). ESLint config extends `next/core-web-vitals` + `@typescript-eslint/recommended-strict`. All shared types in `types/` directory: `types/auth.ts`, `types/workspace.ts`, `types/api.ts`, `types/navigation.ts`.

**Rationale**: Constitution mandates TypeScript 5.x strict mode. Path aliases prevent deeply nested relative imports (`../../../../components/...`). Shared types directory prevents circular imports between `lib/`, `components/`, and `store/`.

**Alternatives considered**:
- Relaxed TypeScript (no strict): Defeats the purpose of TypeScript. Rejected.
- Types co-located with components: Fine for component-specific types but shared types need a dedicated location. Hybrid approach chosen.

---

## Decision 11: Testing Strategy — Vitest + React Testing Library

**Decision**: Use Vitest (not Jest) for unit tests — faster, native ES modules, compatible with Next.js App Router. React Testing Library for component tests. Playwright for E2E tests (separate config). Test files co-located with source (`component.test.tsx` next to `component.tsx`). MSW (Mock Service Worker) for API mocking in integration tests.

**Rationale**: The spec states "Test coverage ≥95% (if applicable)" — so tests are optional but highly recommended for shared utilities and critical components. Vitest is faster than Jest with the same API. React Testing Library aligns with testing behavior over implementation. MSW provides realistic API mocking without coupling tests to fetch internals.

**Alternatives considered**:
- Jest: Slower with App Router; Vitest has better ES module support. Rejected.
- Cypress for component tests: Heavier setup; React Testing Library is lighter and faster. Rejected.
- Snapshot tests: Brittle for UI components; behavior tests are more maintainable. Rejected.
