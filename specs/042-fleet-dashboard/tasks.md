# Tasks: Fleet Dashboard

**Input**: Design documents from `/specs/042-fleet-dashboard/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story this task belongs to (US1–US6)

---

## Phase 1: Setup

**Purpose**: Install new dependency, create TypeScript types, dagre layout utility, and Zustand viewport store — shared foundation for all components and hooks.

- [X] T001 Install `dagre` and `@types/dagre` packages in `apps/web/` (`pnpm add dagre && pnpm add -D @types/dagre`)
- [X] T002 Create all TypeScript type definitions (`FleetListEntry`, `FleetDetail`, `FleetStatus`, `FleetTopologyType`, `FleetMember`, `FleetMemberRole`, `FleetMemberAvailability`, `FleetMemberStatus`, `FleetHealthProjection`, `FleetMemberHealthStatus`, `FleetTopologyVersion`, `TopologyConfig`, `TopologyNodeDef`, `TopologyEdgeDef`, `FleetPerformanceProfile`, `MemberMetric`, `ObserverFinding`, `ObserverFindingSeverity`, `FleetOrchestrationRules`, `FleetGovernanceChain`, `FleetPersonalityProfile`, `StressTestConfig`, `StressTestProgress`, `FleetListFilters`, `PerformanceTimeRange`) in `apps/web/lib/types/fleet.ts`
- [X] T003 Create dagre layout utility (maps `TopologyConfig` + `FleetMember[]` + `FleetTopologyType` → `@xyflow/react` `Node[]` + `Edge[]` with computed positions; hierarchical→`rankDir:'TB'`, peer_to_peer→`rankDir:'LR'`, hybrid→`rankDir:'TB'` compound) in `apps/web/lib/utils/fleet-topology-layout.ts`
- [X] T004 Create Zustand topology viewport store (`TopologyViewportState`: viewport, selectedNodeId, expandedGroups — NOT persisted, resets on fleet navigation change; actions: setViewport, selectNode, toggleGroup, reset) in `apps/web/lib/stores/use-topology-viewport-store.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All TanStack Query hooks powering the feature. Every user story depends on at least one of these hooks.

**⚠️ CRITICAL**: No user story component can be built until the relevant hooks in this phase are complete.

- [X] T005 [P] Create `useFleets(filters: FleetListFilters)` (useQuery, paginated GET /fleets with workspace_id) and `useFleet(fleetId)` (useQuery → `FleetDetail`) in `apps/web/lib/hooks/use-fleets.ts`
- [X] T006 [P] Create `useFleetHealth(fleetId)` (useQuery → `FleetHealthProjection`, `refetchInterval: 30_000` as WebSocket fallback) in `apps/web/lib/hooks/use-fleet-health.ts`
- [X] T007 [P] Create `useFleetMembers(fleetId)` (useQuery → `FleetMember[]`), `useAddFleetMember()`, `useRemoveFleetMember()`, `useUpdateMemberRole()` mutations in `apps/web/lib/hooks/use-fleet-members.ts`
- [X] T008 [P] Create `useFleetTopology(fleetId)` (useQuery → latest `FleetTopologyVersion` from topology history) in `apps/web/lib/hooks/use-fleet-topology.ts`
- [X] T009 [P] Create `useFleetPerformanceHistory(fleetId, range: PerformanceTimeRange)` (useQuery → `FleetPerformanceProfile[]`, passes period_start/period_end from TIME_RANGE_MAP) in `apps/web/lib/hooks/use-fleet-performance.ts`
- [X] T010 [P] Create `useFleetGovernance(fleetId)`, `useFleetOrchestration(fleetId)`, `useFleetPersonality(fleetId)` in `apps/web/lib/hooks/use-fleet-governance.ts`
- [X] T011 [P] Create `usePauseFleet()` (POST /fleets/{id}/pause) and `useResumeFleet()` (POST /fleets/{id}/resume) mutations with cache invalidation in `apps/web/lib/hooks/use-fleet-actions.ts`
- [X] T012 [P] Create `useObserverFindings(fleetId, filters)` (useQuery → paginated findings) and `useAcknowledgeFinding()` (useMutation + optimistic update) in `apps/web/lib/hooks/use-observer-findings.ts`
- [X] T013 [P] Create `useTriggerStressTest()` (POST /simulation/runs with fleet context), `useStressTestProgress(runId)` (useQuery, `refetchInterval: 3_000`), `useCancelStressTest()` in `apps/web/lib/hooks/use-stress-test.ts`

**Checkpoint**: All hooks and layout utility ready — user story phases can now begin.

---

## Phase 3: User Story 1 — Browse and Search Fleet List (Priority: P1) 🎯 MVP

**Goal**: Searchable, filterable, sortable data table of all fleets with status and topology badges. Navigation entry point to fleet detail.

**Independent Test**: Open `/fleet`. Confirm table renders with columns: name, topology badge, member count, health score (with color), status badge. Type "fraud" — confirm filtering within 300ms. Filter by status "degraded" — confirm only matching fleets shown. Sort by health score — confirm ordering changes. Click the fleet name link — confirm navigation to `/fleet/{fleetId}`.

- [X] T014 [P] [US1] Create `FleetStatusBadge` (shadcn `Badge`: active=green, degraded=yellow, paused=blue, archived=gray) in `apps/web/components/features/fleet/FleetStatusBadge.tsx`
- [X] T015 [P] [US1] Create `FleetTopologyBadge` (shadcn `Badge` outline: hierarchical="Hierarchical", peer_to_peer="Mesh", hybrid="Hybrid") in `apps/web/components/features/fleet/FleetTopologyBadge.tsx`
- [X] T016 [US1] Create `FleetDataTable` (shared `DataTable` with columns: name, `FleetTopologyBadge`, member count, inline health color bar, `FleetStatusBadge`, updated_at via date-fns; `SearchInput` 300ms debounce; `FilterBar` for topology_type/status/health_min; pagination; fleet name detail link → `/fleet/${fleet.id}`) in `apps/web/components/features/fleet/FleetDataTable.tsx`
- [X] T017 [US1] Create fleet list page (renders `FleetDataTable` with `workspace_id` from auth store) in `apps/web/app/(main)/fleet/page.tsx`

**Checkpoint**: User Story 1 functional — browse, search, filter, navigate to detail.

---

## Phase 4: User Story 2 — View Fleet Topology Visualization (Priority: P1)

**Goal**: Interactive @xyflow/react topology graph with health-colored nodes, custom edges, member side panel, and WebSocket real-time health updates.

**Independent Test**: Navigate to `/fleet/{fleetId}`. Confirm topology graph renders with correct node count and color-coded health. Confirm layout matches topology type (hierarchical = tree, peer_to_peer = mesh). Zoom/pan works. Click a node — confirm member detail side panel opens. Confirm `?tab=topology` URL routing.

- [X] T018 [P] [US2] Create `FleetMemberNode` (custom `@xyflow/react` node component: agent name, `FleetMemberRole` badge, health-colored border — green >70 / yellow 40–70 / red <40, "selected" size variant) in `apps/web/components/features/fleet/FleetMemberNode.tsx`
- [X] T019 [P] [US2] Create `CommunicationEdge` (custom `@xyflow/react` edge: communication=solid animated, delegation=dashed with arrow, observation=dotted lighter color) in `apps/web/components/features/fleet/CommunicationEdge.tsx`
- [X] T020 [P] [US2] Create `FleetMemberDetailPanel` (shadcn `Sheet` slide-in: member name, FQN, role, `FleetHealthGauge` sm, availability, joined date via date-fns, last_error tooltip; "Remove" → `useRemoveFleetMember`; "Change Role" → shadcn `Select` → `useUpdateMemberRole`; `onClose` callback) in `apps/web/components/features/fleet/FleetMemberDetailPanel.tsx`
- [X] T021 [US2] Create `FleetTopologyGraph` (ReactFlow + `Background` + `Controls` + `MiniMap`; loads `useFleetTopology` + `useFleetMembers` + `useFleetHealth` → `fleet-topology-layout.ts`; registers `FleetMemberNode` + `CommunicationEdge`; node click → `store.selectNode` + `onNodeSelect`; group nodes by role when count > 50 via parent-child; WebSocket `fleet:{fleetId}` updates → node health color re-render without re-layout; viewport sync with `useTopologyViewportStore`) in `apps/web/components/features/fleet/FleetTopologyGraph.tsx`
- [X] T022 [US2] Create `FleetDetailView` (shadcn `Tabs` + URL query param routing `?tab=topology|members|performance|controls|observers` via `useSearchParams` + `router.replace`; default tab: topology; header: fleet name, `FleetStatusBadge`, `FleetTopologyBadge`, `FleetHealthGauge` sm; topology tab: `FleetTopologyGraph` + `FleetMemberDetailPanel` when node selected) in `apps/web/components/features/fleet/FleetDetailView.tsx`
- [X] T023 [US2] Create fleet detail page (renders `FleetDetailView` with `fleetId` from `params`, 404 redirect on not-found) in `apps/web/app/(main)/fleet/[fleetId]/page.tsx`

**Checkpoint**: User Story 2 functional — topology graph with interactive nodes, member panel, tab navigation.

---

## Phase 5: User Story 3 — Monitor Fleet Health and Performance (Priority: P1)

**Goal**: Composite health gauge and three synchronized performance charts with time range selection and real-time WebSocket updates.

**Independent Test**: Open fleet detail, switch to performance tab. Confirm health gauge renders with composite score, color coding, and breakdown tooltip (quorum_met, available/total, per-member). Confirm 3 charts render: success rate, latency, cost. Change time range to 7d — confirm charts update. Confirm real-time data appears without refresh.

- [X] T024 [P] [US3] Create `FleetHealthGauge` (extends shared `ScoreGauge`, `showBreakdown` prop → shadcn `Tooltip` with quorum_met, available_count/total_count, top-3 member health from `useFleetHealth(fleetId)`; color: <40=destructive, 40–70=warning, >70=success; `size="sm"|"lg"`) in `apps/web/components/features/fleet/FleetHealthGauge.tsx`
- [X] T025 [US3] Create `FleetPerformanceCharts` (3 Recharts `ResponsiveContainer` + `LineChart` with `syncId="fleet-perf"` for synchronized tooltip: success_rate as %, avg_completion_time_ms, cost_per_task; `ToggleGroup` time range selector: 1h/6h/24h/7d/30d, default 24h; x-axis: period_start formatted by date-fns; WebSocket updates append new data points to Recharts data array) in `apps/web/components/features/fleet/FleetPerformanceCharts.tsx`

**Checkpoint**: User Story 3 functional — health gauge with breakdown, 3 synchronized performance charts with time range selection.

---

## Phase 6: User Story 4 — Manage Fleet Members (Priority: P2)

**Goal**: Member list with health indicators, add member via agent search dialog, and remove with confirmation.

**Independent Test**: Open fleet members tab. Confirm member list shows name, FQN, role, health, status. Click "Add Member" — confirm agent search dialog. Select agent, set role — confirm member added. Click "Remove" on member — confirm AlertDialog with active execution warning. Confirm removal.

- [X] T026 [P] [US4] Create `AddMemberDialog` (shadcn `Dialog`; `SearchInput` drives `useAgents` from registry API 021; agent results list; role selector shadcn `Select` (lead/worker/observer); "Add" → `useAddFleetMember()` → `onMemberAdded()`; `workspace_id` from auth store) in `apps/web/components/features/fleet/AddMemberDialog.tsx`
- [X] T027 [US4] Create `FleetMemberPanel` (uses `useFleetMembers(fleetId)`; member list rows: name, FQN, role badge, inline health dot (green/yellow/red), availability status, joined date; errored members highlighted + last_error in `Tooltip`; "Add Member" button → `AddMemberDialog`; "Remove" per row → shadcn `AlertDialog` — 409 response shows active execution count warning → `useRemoveFleetMember()`) in `apps/web/components/features/fleet/FleetMemberPanel.tsx`

**Checkpoint**: User Story 4 functional — member list with health, add via registry search, remove with conflict awareness.

---

## Phase 7: User Story 5 — Control Fleet Operations (Priority: P2)

**Goal**: Pause/resume with real-time status transitions, scale with preview, stress test with live progress and cancel.

**Independent Test**: Open controls tab. Click "Pause" on active fleet — confirm AlertDialog, confirm → status shows "pausing" → "paused". Click "Resume" — confirm returns to "active". Click "Scale" → dialog → set target 8 → preview shows proposed additions → confirm → live progress. Click "Stress Test" → dialog → set duration/load → confirm → live progress with executions/success/latency, cancel button works.

- [X] T028 [P] [US5] Create `ScaleDialog` (shadcn `Dialog`; number input for target member count; preview list of agents to add (fetched from registry by fleet requirements); "Confirm" → sequential `useAddFleetMember()` calls with shadcn `Progress` indicator; `onOpenChange` prop) in `apps/web/components/features/fleet/ScaleDialog.tsx`
- [X] T029 [P] [US5] Create `StressTestDialog` (shadcn `Dialog`; Step 1 config: duration shadcn `Select` (5min/15min/30min/1h), load level `Select` (low/medium/high); "Start" → `useTriggerStressTest()` → Step 2 progress view: `Progress` bar, elapsed/total seconds, simulated_executions, current_success_rate %, current_avg_latency_ms, "Cancel" → `useCancelStressTest()`; `useStressTestProgress` with 3s refetch) in `apps/web/components/features/fleet/StressTestDialog.tsx`
- [X] T030 [US5] Create `FleetControlsPanel` (status-aware button visibility: "Pause" visible when active/degraded → `usePauseFleet()` → AlertDialog with active execution count; "Resume" visible when paused → `useResumeFleet()` → AlertDialog; "Scale" always visible → `ScaleDialog`; "Stress Test" → `StressTestDialog`, disabled with tooltip if stress test already running; real-time status transition feedback during pause/resume) in `apps/web/components/features/fleet/FleetControlsPanel.tsx`

**Checkpoint**: User Story 5 functional — pause/resume/scale/stress test with confirmations and live progress.

---

## Phase 8: User Story 6 — View Observer Agent Findings (Priority: P3)

**Goal**: Observer findings panel with severity filtering, severity icons, and acknowledgment with optimistic update.

**Independent Test**: Open observers tab. Confirm findings listed with severity icon/color, timestamp, observer name, description, suggested actions. Filter by "critical" — confirm only critical shown. Acknowledge a finding — confirm optimistic update to acknowledged section with audit trail.

- [X] T031 [US6] Create `FleetObserverPanel` (uses `useObserverFindings(fleetId, { severity, acknowledged })`; filter bar: severity `Select` (all/info/warning/critical), acknowledged `Switch`; findings list: severity icon + color (info=blue/warning=yellow/critical=red), timestamp via date-fns, observer_name, description, `Accordion` for suggested_actions; "Acknowledge" → `useAcknowledgeFinding()` → optimistic move to acknowledged section) in `apps/web/components/features/fleet/FleetObserverPanel.tsx`

**Checkpoint**: User Story 6 functional — observer findings with filtering and acknowledgment.

---

## Phase 9: Tests

**Purpose**: Component tests (Vitest + RTL + MSW) and E2E tests (Playwright) covering all user stories per plan.md Phase 8.

- [X] T032 [P] Write `FleetDataTable` component test (MSW mock GET /fleets, renders columns, search input triggers debounced filter, status/topology filter updates query, health color indicator, detail link points to `/fleet/{id}`) in `apps/web/__tests__/features/fleet/FleetDataTable.test.tsx`
- [X] T033 [P] Write `FleetTopologyGraph` component test (@xyflow/react mock via `vi.mock`, dagre layout utility mock, node count matches members, node colors match health thresholds, node click triggers selectNode, WebSocket mock updates node color without re-layout) in `apps/web/__tests__/features/fleet/FleetTopologyGraph.test.tsx`
- [X] T034 [P] Write `FleetPerformanceCharts` component test (MSW mock GET /performance-profile/history, 3 chart containers render, time range selector triggers re-fetch with different period_start/end params, syncId set on all three LineCharts) in `apps/web/__tests__/features/fleet/FleetPerformanceCharts.test.tsx`
- [X] T035 [P] Write `FleetMemberPanel` component test (MSW mock GET /members, list renders with role/health/status, Add Member dialog opens on button click, errored member shows highlight + tooltip, Remove → AlertDialog → mutation called, 409 response shows active execution count) in `apps/web/__tests__/features/fleet/FleetMemberPanel.test.tsx`
- [X] T036 [P] Write `FleetControlsPanel` component test (Pause visible when active, hidden when paused; Resume visible when paused; Stress Test disabled when test running; pause confirms → usePauseFleet mutation called; stress test dialog opens with config, transitions to progress view after submit) in `apps/web/__tests__/features/fleet/FleetControlsPanel.test.tsx`
- [X] T037 [P] Write `FleetObserverPanel` component test (MSW mock GET /observer-findings, severity filter updates query, Acknowledge → optimistic update → finding moves to acknowledged section, critical findings show red icon) in `apps/web/__tests__/features/fleet/FleetObserverPanel.test.tsx`
- [X] T038 [P] Write fleet-browse E2E test (navigate /fleet, table renders, search filters, status filter, click fleet name link navigates to /fleet/{id}) in `apps/web/e2e/fleet-browse.spec.ts`
- [X] T039 [P] Write fleet-topology E2E test (navigate fleet detail, topology graph renders, click node opens member detail panel, tab switch to members tab and back preserves viewport, ?tab= routing persists on refresh) in `apps/web/e2e/fleet-topology.spec.ts`
- [X] T040 [P] Write fleet-controls E2E test (open controls tab, pause fleet → confirm dialog → status changes, resume fleet, open stress test dialog → configure → start → progress visible → cancel) in `apps/web/e2e/fleet-controls.spec.ts`

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Accessibility, dark mode, responsive layout, and integration validation.

- [X] T041 Add keyboard navigation and ARIA attributes across all fleet components (keyboard zoom/pan on topology graph via @xyflow/react built-in keyboard controls; aria-label on control buttons; role on status indicators; focus management in dialogs and side panel)
- [X] T042 Verify dark mode rendering for all fleet pages (CSS custom property tokens resolve correctly on nodes/edges, chart colors, health gauge — no hardcoded colors)
- [X] T043 Verify responsive layout at 768px breakpoint (topology graph uses simplified list view fallback on mobile, charts resize via ResponsiveContainer, controls panel stacks vertically)
- [X] T044 Run quickstart.md validation (install dagre, start dev server, navigate `/fleet`, `/fleet/{fleetId}`, all 5 tabs — verify no console errors, topology graph renders, charts render)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001 (dagre install) must complete before any hook or component using @xyflow/react layout
- **Foundational (Phase 2)**: Depends on Phase 1 (types must exist before hooks) — **BLOCKS all user story phases**
- **US1 (Phase 3)**: Requires T005 (useFleets, useFleet)
- **US2 (Phase 4)**: Requires T003 (layout util) + T004 (viewport store) + T006 (useFleetHealth) + T007 (useFleetMembers) + T008 (useFleetTopology) + US1 detail page route (T023 depends on T022 which depends on T021)
- **US3 (Phase 5)**: Requires T006 (useFleetHealth) + T009 (useFleetPerformanceHistory) + US2 detail page with tabs (T022)
- **US4 (Phase 6)**: Requires T007 (useFleetMembers + mutations) + US2 tabs (T022)
- **US5 (Phase 7)**: Requires T011 (usePauseFleet/useResumeFleet) + T013 (useStressTest) + US2 tabs
- **US6 (Phase 8)**: Requires T012 (useObserverFindings) + US2 tabs
- **Tests (Phase 9)**: All US phases complete
- **Polish (Phase 10)**: All US phases and Tests complete

### User Story Dependencies

- **US1 (P1)**: Independent after Phase 2 — ✅ MVP target (fleet list only)
- **US2 (P1)**: Independent after Phase 2 — can develop in parallel with US1; creates the detail page shell for US3–US6
- **US3 (P1)**: Depends on US2 detail page + tab system; health gauge and performance charts wired into tabs
- **US4 (P2)**: Depends on US2 detail page — members tab slot
- **US5 (P2)**: Depends on US2 detail page — controls tab slot
- **US6 (P3)**: Depends on US2 detail page — observers tab slot

### Parallel Opportunities

- **Phase 1**: T002, T003, T004 parallel (after T001 dagre install)
- **Phase 2**: T005–T013 all parallel (separate files, no cross-dependencies)
- **Phase 3**: T014, T015 parallel; T016 after T014+T015; T017 after T016
- **Phase 4**: T018, T019, T020 parallel; T021 after T018+T019+T003+T004; T022 after T021+T020; T023 after T022
- **Phase 5**: T024 parallel with T025; T025 after T009
- **Phase 6**: T026 parallel with T027; T027 after T026 logic (dialog is a dependency)
- **Phase 7**: T028, T029 parallel; T030 after T028+T029
- **Phase 9**: T032–T040 all parallel (separate test files)
- **Phase 10**: T041, T042, T043 parallel; T044 after all three

---

## Parallel Example: Phase 2 (Hooks — all independent)

```bash
# Launch all 9 hook implementations simultaneously:
Task: "Create use-fleets.ts (useFleets + useFleet)"
Task: "Create use-fleet-health.ts (30s refetch)"
Task: "Create use-fleet-members.ts (4 operations)"
Task: "Create use-fleet-topology.ts"
Task: "Create use-fleet-performance.ts"
Task: "Create use-fleet-governance.ts (3 hooks)"
Task: "Create use-fleet-actions.ts (pause/resume)"
Task: "Create use-observer-findings.ts (+ acknowledge)"
Task: "Create use-stress-test.ts (trigger/progress/cancel)"
```

## Parallel Example: Phase 9 (Tests — all independent)

```bash
# Launch all 9 test files simultaneously:
Task: "FleetDataTable.test.tsx"
Task: "FleetTopologyGraph.test.tsx"
Task: "FleetPerformanceCharts.test.tsx"
Task: "FleetMemberPanel.test.tsx"
Task: "FleetControlsPanel.test.tsx"
Task: "FleetObserverPanel.test.tsx"
Task: "fleet-browse.spec.ts"
Task: "fleet-topology.spec.ts"
Task: "fleet-controls.spec.ts"
```

---

## Implementation Strategy

### MVP First (US1 + US2 — P1 catalog and topology)

1. Complete Phase 1: Setup (T001–T004, install dagre first)
2. Complete Phase 2: Foundational hooks (T005–T013)
3. Complete Phase 3: US1 Fleet List (T014–T017)
4. **STOP and VALIDATE**: Browse fleets, search, filter, navigate
5. Complete Phase 4: US2 Topology (T018–T023)
6. **STOP and VALIDATE**: Topology graph, node click, tab routing

### Incremental Delivery

1. Setup + Foundational → types, layout utility, all hooks ready
2. US1 (P1) → searchable fleet list
3. US2 (P1) → topology visualization with member detail
4. US3 (P1) → health gauge + performance charts (all P1 complete)
5. US4 (P2) → member management
6. US5 (P2) → fleet controls
7. US6 (P3) → observer findings
8. Tests → coverage
9. Polish → accessibility, dark mode, responsive

### Parallel Team Strategy

After Phase 1+2 complete:
- Developer A: US1 → US3 (list → topology → health/performance)
- Developer B: US4 → US5 (members → controls)
- Developer C: US6 + Tests

---

## Notes

- [P] = different files, no blocking dependencies
- [USN] maps task to user story for traceability
- **T001 (dagre install) MUST complete before T003 and T021** — layout utility imports dagre
- **Topology viewport state (T004) MUST be complete before T021** — graph reads from store
- @xyflow/react requires SSR handling: load topology graph with `dynamic(..., { ssr: false })` to avoid hydration issues with canvas
- WebSocket subscription in `FleetTopologyGraph` (T021): subscribe to `fleet:{fleetId}` topic on mount, unsubscribe on unmount — same `lib/ws.ts` WebSocketClient pattern as feature 026
- `syncId="fleet-perf"` on all 3 Recharts `LineChart` in T025 enables synchronized crosshair tooltip across charts
- Stress test progress (T029) uses `refetchInterval: 3_000` in `useStressTestProgress` — stops refetching when status is "completed", "cancelled", or "failed"
- 50+ node clustering in `FleetTopologyGraph` (T021): use @xyflow/react parent-child `parentNode` field set during layout computation — one group node per FleetMemberRole
