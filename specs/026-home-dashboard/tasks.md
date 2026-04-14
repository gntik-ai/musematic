# Tasks: Home Dashboard

**Input**: Design documents from `specs/026-home-dashboard/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/home-ui.md ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story for independent implementation and testing. 7 phases (1 setup + 1 foundational + 5 user stories + 1 polish).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US5)
- Paths under `apps/web/`

---

## Phase 1: Setup

**Purpose**: TypeScript types, MSW handlers, directory structure

- [x] T001 Create `apps/web/lib/types/home.ts` — TypeScript interfaces: `MetricCardData`, `WorkspaceSummaryResponse`, `ActivityEntry`, `RecentActivityResponse`, `UrgencyLevel`, `PendingAction`, `PendingActionButton`, `PendingActionsResponse`, `QuickAction` per data-model.md
- [x] T002 [P] Create `apps/web/mocks/handlers/home.ts` — MSW handlers for `GET /api/v1/workspaces/:id/analytics/summary`, `GET /api/v1/workspaces/:id/dashboard/recent-activity`, `GET /api/v1/workspaces/:id/dashboard/pending-actions` with realistic fixture data
- [x] T003 [P] Create `apps/web/components/features/home/` directory with stub `index.ts` export file

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Custom hooks and query infrastructure that every user story depends on

**⚠️ CRITICAL**: No user story component work can begin until this phase is complete

- [x] T004 Create `apps/web/lib/hooks/use-home-data.ts` — `homeQueryKeys` factory (`all`, `summary`, `activity`, `pendingActions`); `useWorkspaceSummary(workspaceId)` with `staleTime: 30_000`, `enabled: !!workspaceId`; `useRecentActivity(workspaceId)` with same config; `usePendingActions(workspaceId)` with same config — all using `lib/api.ts` fetch wrapper per data-model.md
- [x] T005 [P] Add `useWebSocketStatus()` to `apps/web/lib/hooks/use-home-data.ts` — subscribes to `wsClient.onConnectionChange`, returns `{ isConnected: boolean }` using `useEffect` + `useState` (connection status is client-only state, not server state)
- [x] T006 [P] Add `useApproveMutation(workspaceId)` to `apps/web/lib/hooks/use-home-data.ts` — `useMutation` with optimistic update (remove card from `pendingActions` cache immediately), rollback on error, `onSettled` invalidates `pendingActions` + `summary` query keys

**Checkpoint**: All hooks defined — components can now use hooks without waiting for each other

---

## Phase 3: User Story 1 — Workspace Summary Overview (Priority: P1) 🎯 MVP

**Goal**: 4 MetricCard components showing active agents, running executions, pending approvals, and cost — each with change indicator. Independent loading, error, and empty states. Refreshes on workspace switch.

**Independent Test**: Navigate to `/home` as authenticated user → verify 4 metric cards load within 2 seconds. Switch workspace → verify cards update. Disable analytics API mock → verify SectionError appears while other sections (if any) remain unaffected.

- [x] T007 [US1] Create `apps/web/components/features/home/WorkspaceSummary.tsx` — calls `useWorkspaceSummary(workspaceId)` from `lib/hooks/use-home-data.ts`; renders 4 `MetricCard` components from existing shared components (feature 015) in `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4`; `isLoading` → 4 `animate-pulse` skeleton placeholder divs; `isError` → `SectionError` component with retry button calling `refetch()`; maps `WorkspaceSummaryResponse` to `MetricCardData` array (active_agents, running_executions, pending_approvals, cost formatted as "$X.XX")
- [x] T008 [US1] Create `apps/web/components/features/home/SectionError.tsx` — reusable error fallback component with error message, "Retry" button (`onClick: refetch`), and `AlertCircle` Lucide icon; styled with shadcn/ui `Alert` component
- [x] T009 [US1] Create `apps/web/app/(main)/home/page.tsx` — Next.js RSC shell that renders `<HomeDashboard>` client component; reads `workspaceId` from URL params or workspace store; sets page title metadata
- [x] T010 [US1] Create `apps/web/components/features/home/HomeDashboard.tsx` — `"use client"` component; reads `workspaceId` from `useWorkspaceStore()` (existing Zustand store); renders `WorkspaceSummary` wrapped in `<ErrorBoundary fallback={<SectionError />}>`; wires `useDashboardWebSocket(workspaceId)` (added later in US5)
- [x] T011 [US1] Write unit tests `apps/web/components/features/home/__tests__/WorkspaceSummary.test.tsx` — MSW mock returns fixture data → verify 4 MetricCard rendered with correct values; MSW returns 500 → verify SectionError rendered; `isLoading` state → verify skeleton rendered; workspace change → verify query refetched

**Checkpoint**: WorkspaceSummary fully functional and independently testable at `/home`.

---

## Phase 4: User Story 2 — Recent Activity Feed (Priority: P1)

**Goal**: Timeline component showing 10 most recent interactions and executions, each with description, relative timestamp, and status badge. Empty state. Clickable entries navigate to detail pages.

**Independent Test**: Navigate to `/home` with 10 activity items in fixture → verify Timeline renders 10 entries newest-first. Click an execution entry → verify navigation to `/executions/{id}`. Configure empty fixture → verify EmptyState appears. Disable activity API → verify SectionError while WorkspaceSummary remains visible.

- [x] T012 [US2] Create `apps/web/components/features/home/RecentActivity.tsx` — calls `useRecentActivity(workspaceId)`; renders existing shared `Timeline` component (feature 015) with `ActivityEntry[]` items; each entry: title, `StatusBadge` (from shared components) with status, relative timestamp using `date-fns formatDistanceToNow`; `isLoading` → 5 skeleton rows with `animate-pulse`; `isError` → `SectionError` with retry; empty items array → existing shared `EmptyState` component with message "No recent activity — start by creating an agent or running a workflow"; each entry wrapped in `next/link` to `entry.href`
- [x] T013 [US2] Add `RecentActivity` to `apps/web/components/features/home/HomeDashboard.tsx` — render below WorkspaceSummary in the left column of `grid grid-cols-1 lg:grid-cols-2 gap-6`; wrap in `<ErrorBoundary>`
- [x] T014 [US2] Write unit tests `apps/web/components/features/home/__tests__/RecentActivity.test.tsx` — fixture with 10 items → verify 10 Timeline entries rendered in order; empty fixture → verify EmptyState; error state → verify SectionError; click on entry → verify `next/link href` correct; verify `formatDistanceToNow` renders relative timestamps

**Checkpoint**: RecentActivity visible alongside WorkspaceSummary. Both independently testable.

---

## Phase 5: User Story 3 — Pending Actions (Priority: P2)

**Goal**: Card list showing urgency-sorted pending approvals, failed executions, and attention requests. Inline approve/reject with optimistic removal. Empty state. Error state independent from other sections.

**Independent Test**: Configure 2 pending approvals + 1 failed execution in MSW fixture → verify 3 cards rendered with failed execution first (high urgency, red border). Click "Approve" → verify card disappears immediately (optimistic), success toast shown. Re-enable fixture → verify card is gone. Configure empty fixture → verify "All clear" EmptyState.

- [x] T015 [US3] Create `apps/web/components/features/home/PendingActionCard.tsx` — accepts `PendingAction` prop and `workspaceId`; urgency border styling: `high` → `border-l-4 border-l-destructive`, `medium` → `border-l-4 border-l-amber-500`, `low` → no special border; renders shadcn/ui `Card` + `CardHeader` + `CardContent`; renders `StatusBadge` for urgency; renders action buttons per `action.actions` array: `approve`/`reject` → calls `useApproveMutation()` with `endpoint` + `method`; button shows loading spinner during mutation; `navigate` → `useRouter().push(action.href)`; on approve/reject success → shows shadcn/ui `toast` ("Action completed"); on 409 error → shows toast "This action has already been resolved"
- [x] T016 [US3] Create `apps/web/components/features/home/PendingActions.tsx` — calls `usePendingActions(workspaceId)`; renders list of `PendingActionCard` components; `isLoading` → 3 skeleton Card placeholders with `animate-pulse`; `isError` → `SectionError` with retry; empty items → `EmptyState` with message "All clear — no pending actions" + `CheckCircle` green icon (positive framing)
- [x] T017 [US3] Add `PendingActions` to `apps/web/components/features/home/HomeDashboard.tsx` — render in the right column alongside `RecentActivity` in the `lg:grid-cols-2` layout; wrap in `<ErrorBoundary>`
- [x] T018 [US3] Write unit tests `apps/web/components/features/home/__tests__/PendingActions.test.tsx` — fixture with mixed urgency items → verify sort order (high first); approve button click → verify optimistic removal + mutation called; 409 response → verify rollback + toast; empty fixture → verify EmptyState; error → verify SectionError

**Checkpoint**: PendingActions functional alongside activity + summary. Inline approve/reject works.

---

## Phase 6: User Story 4 — Quick Actions (Priority: P2)

**Goal**: 4 navigation buttons (New Conversation, Upload Agent, Create Workflow, Browse Marketplace) using static config. Write-permission buttons disabled for viewer-role users with tooltip.

**Independent Test**: Navigate to `/home` as owner → verify all 4 buttons enabled and Tab-focusable. Click each → verify correct navigation. Log in as viewer → verify Upload Agent + Create Workflow are disabled. Hover disabled button → verify Tooltip appears with "Requires write access".

- [x] T019 [P] [US4] Create `apps/web/components/features/home/QuickActions.tsx` — renders `QUICK_ACTIONS` config array (defined inline: New Conversation, Upload Agent, Create Workflow, Browse Marketplace with Lucide icons + href + optional `requiredPermission`); reads user workspace role from existing auth store via `useAuthStore()`; for each action: if `requiredPermission` defined and user lacks permission → render disabled shadcn/ui `Button` wrapped in `Tooltip` ("Requires write access"); otherwise render `Button` as `next/link`; all buttons Tab-focusable with Tailwind `focus-visible:ring-2` visible focus ring; flex row with `flex flex-wrap gap-3`
- [x] T020 [US4] Add `QuickActions` to `apps/web/components/features/home/HomeDashboard.tsx` — render as first row above the 2-column grid (above WorkspaceSummary for immediate access); wrap in shadcn/ui `Card` for visual grouping
- [x] T021 [US4] Write unit tests `apps/web/components/features/home/__tests__/QuickActions.test.tsx` — owner role → all 4 buttons enabled; viewer role → Upload Agent + Create Workflow disabled; disabled button tooltip renders "Requires write access"; each enabled button has correct `href`

**Checkpoint**: All 4 sections functional. P1 + P2 user stories complete. Dashboard is fully usable.

---

## Phase 7: User Story 5 — Real-Time Dashboard Updates (Priority: P3)

**Goal**: WebSocket subscriptions on `execution`, `interaction`, `workspace` channels trigger TanStack Query invalidations. `ConnectionStatusBanner` appears on connection loss and disappears on reconnection. Polling fallback activates when disconnected.

**Independent Test**: Open dashboard → mock WebSocket event `execution.completed` → verify activity query invalidated (feed updates). Mock connection loss via `wsClient.onConnectionChange(false)` → verify ConnectionStatusBanner appears. Restore connection → verify banner disappears.

- [x] T022 [US5] Add `useDashboardWebSocket(workspaceId)` to `apps/web/lib/hooks/use-home-data.ts` — subscribes to `execution`, `interaction`, `workspace` channels via existing `lib/ws.ts` `wsClient.subscribe()`; on `execution.*` events → `queryClient.invalidateQueries({ queryKey: homeQueryKeys.activity(workspaceId) })` + `homeQueryKeys.summary`; on `execution.failed` or `execution.requires_approval` → also invalidate `homeQueryKeys.pendingActions`; on `interaction.*` events → invalidate `homeQueryKeys.activity`; on `workspace.approval.*` or `interaction.attention.requested` → invalidate `homeQueryKeys.pendingActions` + `homeQueryKeys.summary`; returns cleanup function unsubscribing all channels
- [x] T023 [US5] Create `apps/web/components/features/home/ConnectionStatusBanner.tsx` — accepts `isConnected: boolean` prop; renders `null` when `isConnected === true`; when `isConnected === false`: renders fixed banner below page header with `role="status"` + `aria-live="polite"`; content: `Loader2` spinning icon + "Live updates paused — reconnecting…"; Tailwind `transition-all duration-300` for smooth appear/disappear; amber background (`bg-amber-50 dark:bg-amber-950 border-amber-200`)
- [x] T024 [US5] Wire real-time in `apps/web/components/features/home/HomeDashboard.tsx` — call `useDashboardWebSocket(workspaceId)` at component top level; call `useWebSocketStatus()` for `isConnected`; render `<ConnectionStatusBanner isConnected={isConnected} />` as first child; update all `useQuery` hooks to add `refetchInterval: isConnected ? false : 30_000` fallback
- [x] T025 [US5] Write unit tests `apps/web/components/features/home/__tests__/ConnectionStatusBanner.test.tsx` — `isConnected=true` → renders null; `isConnected=false` → renders banner with correct text + role="status"; `aria-live="polite"` present
- [x] T026 [US5] Write integration tests `apps/web/components/features/home/__tests__/HomeDashboard.test.tsx` — mock WebSocket event → verify correct query invalidated; mock `isConnected=false` → verify banner renders + polling enabled; mock `isConnected=true` → verify banner gone + polling disabled

**Checkpoint**: Dashboard updates in real-time. Connection loss handled gracefully.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final assembly, accessibility, dark mode, coverage audit

- [x] T027 Finalize `apps/web/components/features/home/HomeDashboard.tsx` — ensure layout matches contracts/home-ui.md: ConnectionStatusBanner → QuickActions (Card) → WorkspaceSummary grid → 2-column [RecentActivity | PendingActions] at `lg:` breakpoint → stacked on `< lg`; verify all sections in independent `<ErrorBoundary>` wrappers
- [X] T028 [P] Accessibility audit on all home components — add `aria-label` to each MetricCard including change direction ("Active Agents: 12, increased by 3"); add `role="status"` + `aria-live` to ConnectionStatusBanner; verify all interactive elements have visible `focus-visible:ring-2` focus ring; run `pnpm test:a11y` targeting `/home` route
- [X] T029 [P] Dark mode verification — open dashboard in dark mode (`dark` class on `<html>`); verify all color classes use CSS custom properties (`text-foreground`, `bg-background`, `border-border`) not hardcoded Tailwind palette colors; spot-check ConnectionStatusBanner uses `dark:bg-amber-950`
- [X] T030 [P] Responsive layout verification — resize browser to 320px, 640px, 768px, 1024px, 1280px; verify no horizontal scroll; verify MetricCard grid: 1→2→4 columns at sm/lg breakpoints; verify activity/pending stack on `< lg`; verify quick actions wrap without overflow
- [x] T031 [P] Register MSW handlers in `apps/web/mocks/handlers/index.ts` — add `home` handlers to the MSW handler array for use in `NEXT_PUBLIC_MSW_ENABLED=true` dev mode
- [X] T032 [P] Run `pnpm test:coverage` and verify ≥ 95% coverage for all files under `components/features/home/` and `lib/hooks/use-home-data.ts`
- [X] T033 [P] Run `pnpm type-check` (TypeScript strict compilation) and fix any type errors in home feature files
- [X] T034 [P] Run `pnpm lint` (ESLint) on home feature files and fix any lint warnings

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; T002 and T003 parallel with T001
- **Phase 2 (Foundational)**: Depends on Phase 1 (types file must exist) — T005 and T006 parallel with T004
- **Phases 3–7 (User Stories)**: All depend on Phase 2 (hooks must be defined)
  - US1 (Phase 3) → must complete before US2 (needs HomeDashboard shell)
  - US2 (Phase 4) → depends on US1 (adds to HomeDashboard)
  - US3 (Phase 5) → depends on US1 (adds to HomeDashboard); can parallel with US2
  - US4 (Phase 6) → independent after Phase 2; can parallel with US2/US3
  - US5 (Phase 7) → depends on US1+US2+US3 (real-time updates all sections); T022 can start earlier
- **Phase 8 (Polish)**: Depends on all user stories complete; all polish tasks are [P]

### User Story Dependencies

| User Story | Depends On | Can Parallelize With |
|------------|------------|----------------------|
| US1 — Workspace Summary (P1) | Phase 2 | — |
| US2 — Recent Activity (P1) | US1 (HomeDashboard shell) | US3, US4 |
| US3 — Pending Actions (P2) | US1 (HomeDashboard shell) | US2, US4 |
| US4 — Quick Actions (P2) | Phase 2 | US2, US3 |
| US5 — Real-Time Updates (P3) | US1+US2+US3 | Phase 8 |

### Within Each User Story

- Component implementation → integration into HomeDashboard → unit tests
- Hooks (Phase 2) are shared — completed once, used by all story components

### Parallel Opportunities

- **Phase 1**: T002, T003 parallel with T001
- **Phase 2**: T005, T006 parallel with T004
- **Phase 3**: T007, T008, T009 can start in parallel; T010, T011 after T007+T009
- **Phase 5 + Phase 6**: US3 (T015-T018) parallel with US4 (T019-T021) after US1 complete
- **Phase 8**: All polish tasks (T027-T034) parallel

---

## Parallel Example: After Phase 2 Complete

```bash
# Developer A: US1 (WorkspaceSummary + page shell)
Task: "T007 — WorkspaceSummary.tsx component"
Task: "T008 — SectionError.tsx component"
Task: "T009 — home/page.tsx RSC shell"

# Developer B: US4 (QuickActions — completely independent)
Task: "T019 — QuickActions.tsx component"
```

## Parallel Example: After US1 Complete

```bash
# Developer A: US2 (RecentActivity)
Task: "T012 — RecentActivity.tsx component"
Task: "T013 — Add to HomeDashboard"
Task: "T014 — RecentActivity tests"

# Developer B: US3 (PendingActions)
Task: "T015 — PendingActionCard.tsx component"
Task: "T016 — PendingActions.tsx component"
Task: "T017 — Add to HomeDashboard"
Task: "T018 — PendingActions tests"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete **Phase 1** (Setup — types + MSW handlers)
2. Complete **Phase 2** (Foundational — hooks)
3. Complete **Phase 3** (US1 — WorkspaceSummary + page shell)
4. **STOP AND VALIDATE**: Navigate to `/home`, verify 4 metric cards load. Baseline dashboard usable.

### Core Dashboard (P1 Stories)

5. Complete **Phase 4** (US2 — RecentActivity)
6. **VALIDATE**: Activity feed visible with clickable entries
7. Core informational dashboard complete — shows workspace state at a glance

### Full Feature (All Stories)

8. Complete **Phase 5** (US3 — PendingActions) + **Phase 6** (US4 — QuickActions) in parallel
9. Complete **Phase 7** (US5 — Real-Time Updates)
10. Complete **Phase 8** (Polish)

### Parallel Team Strategy (3 developers post-Foundational)

- **Developer A**: US1 → US2
- **Developer B**: US3
- **Developer C**: US4 → US5

---

## Summary

| Phase | User Story | Tasks | Priority |
|-------|------------|-------|----------|
| 1 | Setup | T001–T003 | — |
| 2 | Foundational | T004–T006 | — |
| 3 | US1: Workspace Summary | T007–T011 | P1 🎯 |
| 4 | US2: Recent Activity | T012–T014 | P1 |
| 5 | US3: Pending Actions | T015–T018 | P2 |
| 6 | US4: Quick Actions | T019–T021 | P2 |
| 7 | US5: Real-Time Updates | T022–T026 | P3 |
| 8 | Polish | T027–T034 | — |

**Total tasks**: 34
**MVP tasks (US1 only)**: T001–T011 (11 tasks)
**P1 tasks**: T001–T014 (14 tasks)
**Parallel opportunities**: 16 tasks marked [P]
