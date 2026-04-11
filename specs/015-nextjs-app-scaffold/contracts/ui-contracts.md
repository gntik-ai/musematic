# UI Contracts: Next.js Application Scaffold

**Feature**: 015-nextjs-app-scaffold  
**Date**: 2026-04-11  
**Phase**: 1 — Design

---

## Contract 1: AppShell Layout

**Description**: The persistent layout container wrapping all authenticated pages.

**Route**: `app/(main)/layout.tsx`

**Behavior Contract**:
- MUST render sidebar, header, and main content slot (`children`)
- MUST guard authentication — redirect to `/login` if `!isAuthenticated`
- MUST apply sidebar collapsed/expanded state from `workspace-store`
- Sidebar width: `260px` expanded, `64px` collapsed
- Header height: `64px` fixed
- Main content area occupies remaining viewport height (`calc(100vh - 64px)`)
- Sidebar collapse persists to `localStorage` via `workspace-store`

**Props**: None (layout receives `children: React.ReactNode` implicitly)

**Accessible behaviors**:
- Sidebar is a `<nav>` landmark
- Header is a `<header>` landmark
- Main content is a `<main>` landmark
- Focus is NOT trapped in the sidebar — keyboard navigation continues to main content

---

## Contract 2: Sidebar Navigation Component

**Description**: Collapsible sidebar with role-filtered navigation items.

**Component**: `components/layout/sidebar/Sidebar.tsx`

**Behavior Contract**:
- Reads `NAV_ITEMS` from `components/layout/sidebar/nav-config.ts`
- Filters items where `item.requiredRoles` intersects with `useAuthStore().user.roles`
- Superadmin role bypasses all filters (sees everything)
- Collapsed state: shows icons only (no labels), Tooltip on hover shows the label
- Active item highlighted with `bg-sidebar-accent` token
- Collapse toggle button at the bottom of the sidebar
- Animated collapse: CSS `transition` on `width`, duration ≤ 200ms

**Emits**: None (uses `router.push` directly)

**Keyboard navigation**:
- `Tab`: cycles through nav items
- `Enter`/`Space`: activates item
- Items have `aria-current="page"` when active

---

## Contract 3: Header Component

**Description**: Top header bar with workspace selector, notifications, and user menu.

**Component**: `components/layout/header/Header.tsx`

**Behavior Contract**:
- Left slot: Workspace selector dropdown (`WorkspaceSelector`)
- Center slot: Breadcrumb navigation (`Breadcrumb`)
- Right slot: Notifications icon button + User avatar menu (`UserMenu`)
- Workspace selector: opens shadcn `DropdownMenu` listing workspaces from `workspace-store.workspaceList`
- Selecting a workspace calls `workspace-store.setCurrentWorkspace()` → triggers query invalidation
- User menu: shows avatar (initials fallback), name, email, logout action

**Keyboard navigation**:
- `Tab`: cycles through header interactive elements
- `Enter`/`Space`: opens dropdowns
- `Escape`: closes open dropdown

---

## Contract 4: Command Palette Component

**Description**: Global search dialog for navigation and quick actions.

**Component**: `components/layout/command-palette/CommandPalette.tsx`

**Behavior Contract**:
- Opened via `Cmd+K` (macOS) / `Ctrl+K` (Windows/Linux) — global `keydown` listener in `CommandPaletteProvider`
- Also openable via a button in the header
- Searches `NAV_ITEMS` (filtered by user role) and a static `QUICK_ACTIONS` list
- Filtering is client-side fuzzy match (cmdk built-in)
- Navigation items: navigate to `item.href` on select
- Quick actions: execute `action.callback()` on select
- Opens within 100ms of keyboard shortcut
- `Escape` closes the palette
- No content search — platform content search is a separate feature

**Keyboard navigation**: Full `cmdk` keyboard support (arrows, enter, escape)

---

## Contract 5: DataTable Component

**Description**: Sortable, filterable, paginated data table.

**Component**: `components/shared/DataTable.tsx`

**Behavior Contract**:
- Uses TanStack Table v8 for column sort, filter, and pagination state
- wraps shadcn/ui `Table` for rendering
- Sort: click column header to cycle `asc` → `desc` → none
- Filter: per-column filter input (string match by default)
- Pagination: shows page controls, configurable page size (10/20/50 default options)
- Empty state: shows `EmptyState` component when `data.length === 0` and not loading
- Loading state: shows skeleton rows (5 by default) via shadcn `Skeleton`
- `totalCount` prop enables server-side pagination mode (disables client-side pagination)
- All columns sortable by default; individual columns opt out via `enableSorting: false`

**Keyboard navigation**:
- Column headers are `<button>` elements — focusable with `Tab`, activatable with `Enter`
- Pagination buttons are standard focusable buttons
- Row selection (if enabled): `Space` to toggle, `Shift+Click` for range

**Accessibility**:
- `<table>` with `<caption>` for screen reader context
- Sort state announced via `aria-sort` on `<th>` elements
- Loading state: `aria-busy="true"` on the table container

---

## Contract 6: StatusBadge Component

**Description**: Color-coded badge for entity status values.

**Component**: `components/shared/StatusBadge.tsx`

**Behavior Contract**:
- Maps `StatusSemantic` to shadcn `Badge` variant:
  - `healthy` → `default` (green)
  - `warning` → `warning` (yellow/amber)
  - `error` → `destructive` (red)
  - `inactive` → `secondary` (gray)
  - `pending` → `outline` (neutral)
  - `running` → `default` (blue — via custom CSS var `--badge-running`)
- Default label if `label` prop is omitted: capitalize the `status` value
- Icon: `CheckCircle2` (healthy), `AlertTriangle` (warning), `XCircle` (error), `MinusCircle` (inactive), `Clock` (pending), `Loader2` spinning (running)
- No interactive behavior — purely decorative/informational

---

## Contract 7: MetricCard Component

**Description**: KPI card with value, trend, and optional sparkline.

**Component**: `components/shared/MetricCard.tsx`

**Behavior Contract**:
- Built on shadcn `Card` with `CardHeader` + `CardContent`
- Value rendered in `text-2xl font-bold`
- Trend: `TrendingUp` icon (green) for `up`, `TrendingDown` icon (red) for `down`, `Minus` icon (gray) for `neutral`
- Sparkline: Recharts `AreaChart` with minimal styling (no axes, no grid), `80px` height
- Loading state: `Skeleton` for value, title, and sparkline areas
- Responsive: stacks to full-width on mobile

---

## Contract 8: ScoreGauge Component

**Description**: Circular gauge for 0–100 numeric scores.

**Component**: `components/shared/ScoreGauge.tsx`

**Behavior Contract**:
- Recharts `RadialBarChart` with a single `RadialBar` representing the score
- Color thresholds: `< warning` → red, `>= warning && < good` → amber, `>= good` → green
- Score value displayed in the center of the gauge
- Optional `label` shown below the center value
- No interactive behavior

---

## Contract 9: ConfirmDialog Component

**Description**: Destructive action confirmation dialog.

**Component**: `components/shared/ConfirmDialog.tsx`

**Behavior Contract**:
- Built on shadcn `AlertDialog` (`AlertDialogRoot`, `AlertDialogContent`, etc.)
- `variant="destructive"`: confirm button uses `destructive` variant
- `isLoading=true`: confirm button shows spinner and is disabled; cancel is also disabled
- Clicking the confirm button calls `onConfirm()` — dialog does NOT close automatically
- Caller is responsible for closing via `onOpenChange(false)` after async operation completes
- `Escape` key closes the dialog (shadcn default)

---

## Contract 10: CodeBlock Component

**Description**: Syntax-highlighted code display with copy button.

**Component**: `components/shared/CodeBlock.tsx`

**Behavior Contract**:
- Wraps shadcn `pre` tag
- `highlight.js` loaded lazily (dynamic import, only when component first renders)
- Languages loaded on demand (not all highlight.js languages bundled)
- Copy button copies `code` prop to clipboard; shows checkmark for 2s on success
- `maxHeight` prop wraps content in a scrollable container
- Line numbers: `counter-reset` CSS approach (no extra DOM elements per line)
- Falls back to plain `<pre>` rendering if highlight.js fails to load

---

## Contract 11: JsonViewer Component

**Description**: Interactive collapsible JSON tree renderer.

**Component**: `components/shared/JsonViewer.tsx`

**Behavior Contract**:
- Renders JSON as a tree using shadcn `Collapsible` for expandable nodes
- Root level: always expanded by default
- Nested objects/arrays: collapsed by default beyond `maxDepth`
- Key names: `text-blue-500` (light) / `text-blue-300` (dark)
- String values: `text-green-600` / `text-green-400`
- Number values: `text-amber-600` / `text-amber-300`
- Boolean values: `text-purple-600` / `text-purple-300`
- Null values: `text-muted-foreground italic`
- Copy button: copies full JSON stringified value to clipboard

---

## Contract 12: WebSocketProvider Context

**Description**: React context providing the shared `WebSocketClient` instance.

**Component**: `components/providers/WebSocketProvider.tsx`

**Behavior Contract**:
- Creates a single `WebSocketClient` instance on mount
- Connects to `process.env.NEXT_PUBLIC_WS_URL` on mount
- Disconnects on unmount
- Exposes instance via `useWebSocket()` hook
- `connectionState` changes cause a context re-render (subscriber components update)

---

## Contract 13: Connection State Indicator

**Description**: Visual indicator for WebSocket connection status.

**Component**: `components/layout/header/ConnectionIndicator.tsx`

**Behavior Contract**:
- `connected`: green dot (no label)
- `reconnecting`: amber dot with "Reconnecting..." label
- `disconnected`: red dot with "Disconnected" label + retry button
- `connecting`: pulsing gray dot
- Renders in the header right slot (before notifications icon)
- Tooltip shows detailed connection state info
