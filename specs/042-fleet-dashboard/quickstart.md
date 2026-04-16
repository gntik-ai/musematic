# Quickstart: Fleet Dashboard

## Prerequisites

- Node.js 20+, pnpm 9+
- Backend APIs operational: fleet management (033), simulation (040), registry (021)
- Development server for `apps/web` running

## New Dependencies

One new npm package required:

```bash
cd apps/web
pnpm add dagre
pnpm add -D @types/dagre
```

All other dependencies already in the frontend stack (from features 015, 035, 041):
- `shadcn/ui` — DataTable, Tabs, Dialog, Badge, Tooltip, Progress, Alert, AlertDialog, Sheet, Select, ToggleGroup
- `@xyflow/react v12+` — topology graph (ReactFlow, Background, Controls, MiniMap)
- `Recharts 2.x` — performance charts (LineChart, Area, Tooltip, ResponsiveContainer)
- `TanStack Query v5` — all server state
- `Zustand 5.x` — topology viewport state
- `date-fns 4.x` — timestamp formatting
- `Lucide React` — icons
- `Tailwind CSS 3.4+` — all styling, dark mode via CSS custom properties

## Running the Dev Server

```bash
cd apps/web
pnpm dev
```

Navigate to:
- `http://localhost:3000/fleet` — Fleet list
- `http://localhost:3000/fleet/{fleetId}` — Fleet detail (default: topology tab)
- `http://localhost:3000/fleet/{fleetId}?tab=members` — Members panel
- `http://localhost:3000/fleet/{fleetId}?tab=performance` — Performance charts
- `http://localhost:3000/fleet/{fleetId}?tab=controls` — Fleet controls
- `http://localhost:3000/fleet/{fleetId}?tab=observers` — Observer findings

## Running Tests

```bash
cd apps/web
pnpm test                  # Vitest unit tests
pnpm test:e2e              # Playwright E2E tests
```

Test setup:
- Vitest + RTL for component tests
- MSW (Mock Service Worker) for API mocking
- Playwright for E2E flows (fleet browse, topology interaction, controls)

## Project Structure

```text
apps/web/
├── app/(main)/fleet/
│   ├── page.tsx                               # Fleet list (US1)
│   └── [fleetId]/
│       └── page.tsx                           # Fleet detail (US2–US6, tabbed)
│
├── components/features/fleet/
│   ├── FleetDataTable.tsx                     # DataTable with search/filter (US1)
│   ├── FleetStatusBadge.tsx                   # Status indicator
│   ├── FleetTopologyBadge.tsx                 # Topology type badge
│   ├── FleetDetailView.tsx                    # Tabbed detail layout (US2–US6)
│   ├── FleetTopologyGraph.tsx                 # @xyflow/react topology (US2)
│   ├── FleetMemberNode.tsx                    # Custom node component (US2)
│   ├── CommunicationEdge.tsx                  # Custom edge component (US2)
│   ├── FleetMemberDetailPanel.tsx             # Side panel for selected node (US2)
│   ├── FleetHealthGauge.tsx                   # Composite health gauge (US3)
│   ├── FleetPerformanceCharts.tsx             # Recharts success/latency/cost (US3)
│   ├── FleetMemberPanel.tsx                   # Member list + management (US4)
│   ├── AddMemberDialog.tsx                    # Agent search + add dialog (US4)
│   ├── FleetControlsPanel.tsx                 # Pause/resume/scale/stress (US5)
│   ├── ScaleDialog.tsx                        # Scale target + preview (US5)
│   ├── StressTestDialog.tsx                   # Stress test config + progress (US5)
│   └── FleetObserverPanel.tsx                 # Observer findings list (US6)
│
├── lib/
│   ├── hooks/
│   │   ├── use-fleets.ts                      # useFleets, useFleet
│   │   ├── use-fleet-health.ts                # useFleetHealth
│   │   ├── use-fleet-members.ts               # useFleetMembers + mutations
│   │   ├── use-fleet-topology.ts              # useFleetTopology
│   │   ├── use-fleet-performance.ts           # useFleetPerformanceHistory
│   │   ├── use-fleet-governance.ts            # useFleetGovernance, useFleetOrchestration, useFleetPersonality
│   │   ├── use-fleet-actions.ts               # usePauseFleet, useResumeFleet
│   │   ├── use-observer-findings.ts           # useObserverFindings, useAcknowledgeFinding
│   │   └── use-stress-test.ts                 # useTriggerStressTest, useStressTestProgress, useCancelStressTest
│   ├── stores/
│   │   └── use-topology-viewport-store.ts     # Zustand viewport/selection state
│   └── utils/
│       └── fleet-topology-layout.ts           # dagre layout computation per topology type
│
├── __tests__/
│   └── features/fleet/
│       ├── FleetDataTable.test.tsx
│       ├── FleetTopologyGraph.test.tsx
│       ├── FleetPerformanceCharts.test.tsx
│       ├── FleetMemberPanel.test.tsx
│       ├── FleetControlsPanel.test.tsx
│       └── FleetObserverPanel.test.tsx
│
└── e2e/
    ├── fleet-browse.spec.ts
    ├── fleet-topology.spec.ts
    └── fleet-controls.spec.ts
```

## Key Configuration

No new environment variables required. The feature uses the existing `NEXT_PUBLIC_API_BASE_URL` and auth token from the existing auth store.

WebSocket subscription: uses existing `lib/ws.ts` WebSocketClient with `fleet:{fleetId}` topic.
