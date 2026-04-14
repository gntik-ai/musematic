# Quickstart: Workflow Editor and Execution Monitor

## Prerequisites

- Node.js 20+ and pnpm 9+
- The backend control plane running (or MSW mocks active)
- The WebSocket gateway running on `ws://localhost:8001` (or MSW WS mocks)

## Running the Frontend (development)

```bash
cd apps/web
pnpm dev
```

Navigate to `http://localhost:3000/workflow-editor-monitor` to see the workflow list.

## New Dependencies to Install

```bash
cd apps/web
pnpm add monaco-yaml @dagrejs/dagre
pnpm add -D @types/dagre
```

- `monaco-yaml` — YAML language service for Monaco with JSON Schema support
- `@dagrejs/dagre` — DAG layout algorithm for `@xyflow/react` graph preview

Note: `@monaco-editor/react`, `@xyflow/react`, and `recharts` are already in the workspace.

## Running Tests

```bash
cd apps/web
pnpm test              # Vitest unit + component tests
pnpm test:e2e          # Playwright E2E tests
```

## MSW Mock Setup

During development without a live backend, MSW handlers provide realistic data.  
Handlers for this feature live in:
```
apps/web/src/mocks/handlers/
  workflows.ts          # Workflow CRUD handlers
  executions.ts         # Execution state + journal + control handlers
  task-plan.ts          # TaskPlanFullResponse per step
  analytics.ts          # Cost data handlers
```

WebSocket mock events are dispatched via the test utility:
```typescript
import { mockWsEvent } from '@/test-utils/ws-mock';
mockWsEvent(`execution:${id}`, { event_type: 'step.state_changed', ... });
```

## Key Routes

| URL | Page |
|-----|------|
| `/workflow-editor-monitor` | Workflow list |
| `/workflow-editor-monitor/new` | Create new workflow |
| `/workflow-editor-monitor/[id]` | Workflow editor (YAML + graph) |
| `/workflow-editor-monitor/[id]/executions` | Execution history list |
| `/workflow-editor-monitor/[id]/executions/[executionId]` | Live execution monitor |

## Architecture Summary

```
app/(main)/workflow-editor-monitor/
├── page.tsx                          ← Workflow list (useInfiniteQuery)
├── new/page.tsx                      ← Create workflow (empty editor)
├── [id]/
│   ├── page.tsx                      ← Workflow editor
│   └── executions/
│       ├── page.tsx                  ← Execution history
│       └── [executionId]/page.tsx   ← Execution monitor (WebSocket)

components/features/workflows/
├── WorkflowList.tsx
├── editor/
│   ├── WorkflowEditorShell.tsx       ← Split: Monaco + Graph
│   ├── MonacoYamlEditor.tsx          ← Monaco + monaco-yaml + schema
│   ├── WorkflowGraphPreview.tsx      ← @xyflow/react + dagre layout
│   └── EditorToolbar.tsx             ← Save button, version badge
└── monitor/
    ├── ExecutionMonitorShell.tsx     ← Split: Graph + Timeline + Detail
    ├── ExecutionGraph.tsx            ← @xyflow/react + status colors
    ├── ExecutionTimeline.tsx         ← Virtual-scroll journal events
    ├── StepDetailPanel.tsx           ← Tabs: Overview/Reasoning/Self-Correction/Task Plan
    ├── ReasoningTraceViewer.tsx      ← Expandable branch tree
    ├── SelfCorrectionChart.tsx       ← Recharts LineChart convergence
    ├── TaskPlanViewer.tsx            ← Expandable candidate tree
    ├── CostTracker.tsx               ← Real-time cost + expandable breakdown
    └── ExecutionControls.tsx         ← Pause/Resume/Cancel/Retry/Skip/Inject

lib/hooks/
├── use-workflow-list.ts              ← useInfiniteQuery
├── use-workflow-editor.ts            ← YAML content + save mutation
├── use-workflow-graph.ts             ← YAML → dagre nodes/edges (memo)
├── use-execution-monitor.ts          ← State + WS subscription + reconnect
├── use-execution-journal.ts          ← Journal events (infinite scroll)
├── use-step-detail.ts                ← Per-step inputs/outputs/timing
├── use-reasoning-trace.ts            ← Journal events filtered by step
├── use-task-plan.ts                  ← Lazy task plan query
├── use-execution-controls.ts         ← All control action mutations
└── use-cost-tracker.ts               ← Real-time token accumulation

lib/stores/
├── workflow-editor-store.ts          ← YAML + validation + graph state
└── execution-monitor-store.ts        ← Step statuses + selected step + cost

types/
├── workflows.ts                      ← WorkflowDefinition, WorkflowIR, etc.
├── execution.ts                      ← Execution, ExecutionEvent, etc.
├── reasoning.ts                      ← ReasoningTrace, SelfCorrectionLoop
└── task-plan.ts                      ← TaskPlanRecord, candidates
```
