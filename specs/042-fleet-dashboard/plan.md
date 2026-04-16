# Implementation Plan: Fleet Dashboard

**Branch**: `042-fleet-dashboard` | **Date**: 2026-04-16 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/042-fleet-dashboard/spec.md`

## Summary

Frontend feature providing a fleet list DataTable, fleet detail page with interactive @xyflow/react topology graph, member management panel, Recharts performance charts (success rate, latency, cost), fleet controls (pause/resume/scale/stress test), and observer findings panel. WebSocket real-time updates for health and performance. One new dependency: `dagre` for graph layout.

## Technical Context

**Language/Version**: TypeScript 5.x, React 18+, Next.js 14+ App Router
**Primary Dependencies**: shadcn/ui, @xyflow/react 12+, dagre (NEW), Recharts 2.x, TanStack Query v5, Zustand 5.x, date-fns 4.x, Lucide React, Tailwind CSS 3.4+
**Storage**: N/A (frontend only — data sourced from fleet management API 033, fleet learning API 033, simulation API 040, registry API 021)
**Testing**: Vitest + RTL (unit/component), Playwright + MSW (E2E)
**Target Platform**: Web browser (Chrome/Firefox/Safari/Edge), responsive (mobile + desktop)
**Project Type**: Frontend feature module within existing Next.js App Router application
**Performance Goals**: Topology graph interactive within 3s for 30 nodes, charts load < 2s, real-time updates < 5s lag
**Constraints**: One new npm package (dagre); dark mode via existing CSS custom properties; all UI via shadcn/ui
**Scale/Scope**: 6 user stories, 17 components, 19 hooks, 1 Zustand store, 1 layout utility, 6 component tests + 3 E2E specs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Frontend feature — applicable constitution principles (Section 7: Frontend Conventions):

| Principle | Status | Notes |
|-----------|--------|-------|
| Function components only | PASS | All components use function component syntax |
| shadcn/ui for ALL UI primitives | PASS | No alternative component libraries |
| Tailwind CSS for ALL styling | PASS | No custom CSS files |
| TanStack Query v5 for server state | PASS | All API calls via useQuery/useMutation |
| Zustand for client state | PASS | Topology viewport state uses Zustand |
| No new npm packages without justification | PASS | dagre justified: official @xyflow/react recommended layout engine (~15KB) |
| @xyflow/react for graph viz | PASS | Already in constitution tech stack |
| Recharts for charts | PASS | Already in constitution tech stack |
| Accessible (keyboard + screen reader) | PASS | shadcn/ui WAI-ARIA + @xyflow/react keyboard controls |
| Responsive (mobile + desktop) | PASS | Tailwind responsive utilities, simplified graph on mobile |

No violations — no Complexity Tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/042-fleet-dashboard/
├── plan.md                    # This file
├── research.md                # Phase 0: 8 decisions
├── data-model.md              # Phase 1: TypeScript types + state models
├── quickstart.md              # Phase 1: project structure + routes + test commands
├── contracts/
│   ├── api-consumed.md        # Phase 1: API endpoints + TanStack Query hook map
│   └── component-contracts.md # Phase 1: component prop interfaces
└── tasks.md                   # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/web/
├── app/(main)/
│   └── fleet/
│       ├── page.tsx                               # US1: Fleet list (DataTable)
│       └── [fleetId]/
│           └── page.tsx                           # US2–US6: Fleet detail (tabbed)
│
├── components/features/fleet/
│   ├── FleetDataTable.tsx                         # US1: DataTable + search + filter + pagination
│   ├── FleetStatusBadge.tsx                       # US1: Status color badge
│   ├── FleetTopologyBadge.tsx                     # US1: Topology type badge
│   ├── FleetDetailView.tsx                        # US2: Tabbed detail (topology|members|performance|controls|observers)
│   ├── FleetTopologyGraph.tsx                     # US2: @xyflow/react + dagre layout + WebSocket updates
│   ├── FleetMemberNode.tsx                        # US2: Custom node (name, role, health color)
│   ├── CommunicationEdge.tsx                      # US2: Custom edge (solid/dashed/dotted by type)
│   ├── FleetMemberDetailPanel.tsx                 # US2: Side panel for selected node (shadcn Sheet)
│   ├── FleetHealthGauge.tsx                       # US3: Extends ScoreGauge with fleet breakdown
│   ├── FleetPerformanceCharts.tsx                 # US3: 3 Recharts LineCharts with time range selector
│   ├── FleetMemberPanel.tsx                       # US4: Member list + add/remove
│   ├── AddMemberDialog.tsx                        # US4: Agent search + role selector + add
│   ├── FleetControlsPanel.tsx                     # US5: Pause/resume/scale/stress controls
│   ├── ScaleDialog.tsx                            # US5: Scale target input + preview
│   ├── StressTestDialog.tsx                       # US5: Config + live progress
│   └── FleetObserverPanel.tsx                     # US6: Findings list + severity filter + acknowledge
│
├── lib/
│   ├── hooks/
│   │   ├── use-fleets.ts                          # useFleets (paginated), useFleet
│   │   ├── use-fleet-health.ts                    # useFleetHealth (30s fallback refetch)
│   │   ├── use-fleet-members.ts                   # useFleetMembers, useAddFleetMember, useRemoveFleetMember, useUpdateMemberRole
│   │   ├── use-fleet-topology.ts                  # useFleetTopology
│   │   ├── use-fleet-performance.ts               # useFleetPerformanceHistory
│   │   ├── use-fleet-governance.ts                # useFleetGovernance, useFleetOrchestration, useFleetPersonality
│   │   ├── use-fleet-actions.ts                   # usePauseFleet, useResumeFleet
│   │   ├── use-observer-findings.ts               # useObserverFindings, useAcknowledgeFinding
│   │   └── use-stress-test.ts                     # useTriggerStressTest, useStressTestProgress, useCancelStressTest
│   ├── stores/
│   │   └── use-topology-viewport-store.ts         # Zustand: viewport, selectedNodeId, expandedGroups
│   └── utils/
│       └── fleet-topology-layout.ts               # dagre layout computation per topology type
│
└── __tests__/
    ├── features/fleet/
    │   ├── FleetDataTable.test.tsx
    │   ├── FleetTopologyGraph.test.tsx
    │   ├── FleetPerformanceCharts.test.tsx
    │   ├── FleetMemberPanel.test.tsx
    │   ├── FleetControlsPanel.test.tsx
    │   └── FleetObserverPanel.test.tsx
    └── e2e/
        ├── fleet-browse.spec.ts
        ├── fleet-topology.spec.ts
        └── fleet-controls.spec.ts
```

**Structure Decision**: Single Next.js App Router frontend feature module. Routes under `app/(main)/fleet/`. Fleet detail is a single page with tabbed sections (topology graph state preserved across tab switches via Zustand store). Components grouped under `components/features/fleet/`. Layout utility in `lib/utils/` encapsulates dagre-specific logic.

## Implementation Phases

### Phase 1: TypeScript Types, Hook Infrastructure, and Layout Utility

Create all TypeScript types, TanStack Query hooks, the Zustand topology viewport store, and the dagre layout utility.

**Files**:
- `apps/web/lib/types/fleet.ts` — all TypeScript interfaces from data-model.md
- `apps/web/lib/utils/fleet-topology-layout.ts` — dagre layout per topology type (hierarchical→TB tree, peer_to_peer→LR, hybrid→TB compound)
- `apps/web/lib/stores/use-topology-viewport-store.ts` — Zustand store (viewport, selectedNodeId, expandedGroups, NOT persisted)
- `apps/web/lib/hooks/use-fleets.ts` — `useFleets`, `useFleet`
- `apps/web/lib/hooks/use-fleet-health.ts` — `useFleetHealth` (refetchInterval 30s fallback)
- `apps/web/lib/hooks/use-fleet-members.ts` — `useFleetMembers`, `useAddFleetMember`, `useRemoveFleetMember`, `useUpdateMemberRole`
- `apps/web/lib/hooks/use-fleet-topology.ts` — `useFleetTopology`
- `apps/web/lib/hooks/use-fleet-performance.ts` — `useFleetPerformanceHistory`
- `apps/web/lib/hooks/use-fleet-governance.ts` — `useFleetGovernance`, `useFleetOrchestration`, `useFleetPersonality`
- `apps/web/lib/hooks/use-fleet-actions.ts` — `usePauseFleet`, `useResumeFleet`
- `apps/web/lib/hooks/use-observer-findings.ts` — `useObserverFindings`, `useAcknowledgeFinding`
- `apps/web/lib/hooks/use-stress-test.ts` — `useTriggerStressTest`, `useStressTestProgress`, `useCancelStressTest`

### Phase 2: Fleet List Page (US1)

Fleet list DataTable with search, filter, and navigation.

**Files**:
- `apps/web/components/features/fleet/FleetStatusBadge.tsx` — status color badge
- `apps/web/components/features/fleet/FleetTopologyBadge.tsx` — topology type badge
- `apps/web/components/features/fleet/FleetDataTable.tsx` — DataTable + SearchInput + FilterBar + pagination
- `apps/web/app/(main)/fleet/page.tsx` — fleet list page

### Phase 3: Fleet Detail — Topology Graph (US2)

Interactive topology visualization with custom nodes, edges, and member detail panel.

**Files**:
- `apps/web/components/features/fleet/FleetMemberNode.tsx` — custom @xyflow/react node (name, role badge, health border color)
- `apps/web/components/features/fleet/CommunicationEdge.tsx` — custom edge (solid/dashed/dotted by type, animated active)
- `apps/web/components/features/fleet/FleetMemberDetailPanel.tsx` — shadcn Sheet side panel on node click
- `apps/web/components/features/fleet/FleetTopologyGraph.tsx` — ReactFlow + dagre layout + zoom/pan/minimap + WebSocket health updates + 50+ node clustering
- `apps/web/components/features/fleet/FleetDetailView.tsx` — tabbed layout with URL ?tab= routing
- `apps/web/app/(main)/fleet/[fleetId]/page.tsx` — fleet detail page

### Phase 4: Fleet Health and Performance (US3)

Health gauge and three performance charts with time range selection and real-time updates.

**Files**:
- `apps/web/components/features/fleet/FleetHealthGauge.tsx` — extends ScoreGauge with fleet breakdown tooltip
- `apps/web/components/features/fleet/FleetPerformanceCharts.tsx` — 3 Recharts LineCharts (success rate, latency, cost) + ToggleGroup time range selector + syncId tooltip

### Phase 5: Fleet Members Management (US4)

Member panel with list, add/remove members, and role management.

**Files**:
- `apps/web/components/features/fleet/AddMemberDialog.tsx` — agent search + role selector + add
- `apps/web/components/features/fleet/FleetMemberPanel.tsx` — member list + add button + remove with AlertDialog

### Phase 6: Fleet Controls (US5)

Pause/resume/scale/stress test controls with dialogs and real-time feedback.

**Files**:
- `apps/web/components/features/fleet/ScaleDialog.tsx` — target member count + preview + progress
- `apps/web/components/features/fleet/StressTestDialog.tsx` — config (duration, load) + live progress (3s refetch) + cancel
- `apps/web/components/features/fleet/FleetControlsPanel.tsx` — control buttons with status-aware visibility

### Phase 7: Observer Findings (US6)

Observer panel with severity filtering and acknowledgment.

**Files**:
- `apps/web/components/features/fleet/FleetObserverPanel.tsx` — findings list + severity filter + acknowledge button + optimistic update

### Phase 8: Tests

**Component tests (Vitest + RTL + MSW)**:
- `apps/web/__tests__/features/fleet/FleetDataTable.test.tsx`
- `apps/web/__tests__/features/fleet/FleetTopologyGraph.test.tsx`
- `apps/web/__tests__/features/fleet/FleetPerformanceCharts.test.tsx`
- `apps/web/__tests__/features/fleet/FleetMemberPanel.test.tsx`
- `apps/web/__tests__/features/fleet/FleetControlsPanel.test.tsx`
- `apps/web/__tests__/features/fleet/FleetObserverPanel.test.tsx`

**E2E tests (Playwright)**:
- `apps/web/__tests__/e2e/fleet-browse.spec.ts`
- `apps/web/__tests__/e2e/fleet-topology.spec.ts`
- `apps/web/__tests__/e2e/fleet-controls.spec.ts`

## Key Design Decisions

1. **Fleet ID as URL param**: `[fleetId]` dynamic segment — UUIDs are URL-safe, no encoding needed (unlike FQN in feature 041).
2. **Tab routing**: `?tab=topology` query param via `useSearchParams` + `router.replace` — same pattern as features 027 and 041.
3. **Topology viewport preservation**: Zustand store persists zoom/pan/selection across tab switches within the same session. Resets on fleet navigation change.
4. **dagre layout utility**: Encapsulated in `lib/utils/fleet-topology-layout.ts` — maps `TopologyConfig` + `FleetMember[]` → `@xyflow/react` `Node[]` + `Edge[]` with computed positions.
5. **WebSocket subscription**: Detail page subscribes to `fleet:{fleetId}` topic on mount, unsubs on unmount. Health and member status updates received as events, used to update node colors in real-time without re-layout.
6. **Performance chart syncId**: Three Recharts `LineChart` share `syncId="fleet-perf"` for synchronized crosshair tooltip — hovering one chart highlights the same timestamp on all three.
7. **Stress test delegation**: Stress tests use the simulation API (feature 040) — the fleet dashboard only triggers and monitors, the actual simulation runs in the `platform-simulation` namespace.

## Dependencies

- **FEAT-FE-001** (App scaffold / feature 015) — route groups, `lib/api.ts`, `lib/ws.ts`, shared components (DataTable, ScoreGauge, EmptyState, SearchInput, FilterBar, ConfirmDialog, StatusBadge, Timeline), Zustand auth store
- **FEAT-INFRA-033** (Fleet Management) — all fleet CRUD, membership, topology, governance, learning APIs
- **FEAT-INFRA-040** (Simulation) — stress test trigger and progress APIs
- **FEAT-INFRA-021** (Agent Registry) — agent search for "Add Member" dialog
- **FEAT-FE-026** (Home Dashboard) — ConnectionStatusBanner component for WebSocket fallback
- **FEAT-INFRA-019** (WebSocket Hub) — `fleet` channel type for real-time updates

## New Package

```bash
pnpm add dagre && pnpm add -D @types/dagre
```

Justification: dagre is the officially recommended layout engine for @xyflow/react (per @xyflow documentation). At ~15KB gzipped, it adds negligible bundle weight. Computing graph layouts manually would require re-implementing well-established algorithms.
