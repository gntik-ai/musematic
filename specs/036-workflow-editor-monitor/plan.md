# Implementation Plan: Workflow Editor and Execution Monitor

**Branch**: `036-workflow-editor-monitor` | **Date**: 2026-04-13 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/036-workflow-editor-monitor/spec.md`

## Summary

Build a YAML workflow authoring UI with Monaco Editor (schema validation + autocomplete), a `@xyflow/react` DAG graph preview, a live execution monitor with WebSocket-driven step status coloring, a timeline panel of journal events, per-step detail panels (inputs/outputs/timing/context quality), reasoning trace viewer (expandable branch tree), self-correction convergence chart (Recharts), task plan viewer (candidate/selection/provenance tree), operator controls (pause/resume/cancel/retry/skip/inject variable with confirmation dialogs), and a real-time cost tracker.

## Technical Context

**Language/Version**: TypeScript 5.x (strict)  
**Primary Dependencies**: Next.js 14+ (App Router), React 18+, shadcn/ui, TanStack Query v5, Zustand 5.x, `@monaco-editor/react` (Monaco 0.50+), `monaco-yaml`, `@xyflow/react 12+`, `@dagrejs/dagre`, Recharts 2.x, React Hook Form 7.x + Zod 3.x, date-fns 4.x  
**Storage**: N/A (frontend; reads from backend API + WebSocket)  
**Testing**: Vitest + React Testing Library + Playwright + MSW; ≥95% line coverage  
**Target Platform**: Web browser (Next.js App Router, SSR-safe dynamic imports for Monaco)  
**Project Type**: Web application (frontend feature within existing Next.js app)  
**Performance Goals**: Graph interactive at ≤100 nodes within 300ms; step color update within 2s of WS event; editor debounce 500ms  
**Constraints**: Dark mode (CSS custom property tokens); accessible (ARIA roles, keyboard navigation); responsive (mobile Sheet for controls; desktop split-pane layout)  
**Scale/Scope**: ≤100-step workflows; real-time updates for concurrent executions per operator session

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Notes |
|-----------|-------|-------|
| Function components only | ✅ | All components will use function components |
| `shadcn/ui` for ALL UI primitives | ✅ | Monaco and @xyflow/react are domain-specific (code editor / graph), not UI replacements |
| No custom CSS (Tailwind only) | ✅ | Monaco and @xyflow/react have their own style systems managed via props/className; globals.css design tokens only |
| TanStack Query for server state | ✅ | All API data via `useAppQuery` / `useAppMutation` / `useAppInfiniteQuery` |
| Zustand for client state | ✅ | `workflow-editor-store` + `execution-monitor-store` |
| React Hook Form + Zod for forms | ✅ | Used for "inject variable" dialog |
| `date-fns` for dates | ✅ | All timestamp formatting |
| `@xyflow/react` for graphs | ✅ | Already in constitution tech stack |
| Monaco 0.50+ for code editor | ✅ | Already in constitution tech stack |
| Recharts 2.x for charts | ✅ | Already in constitution tech stack |

**Constitution Compliance**: PASS — no violations, no complexity justification required.

**Post-Phase 1 re-check**: All Phase 1 design decisions (dagre layout, monaco-yaml integration, journal pagination, lazy task plan loading) are consistent with the constitution. No new store cross-dependencies introduced.

## Project Structure

### Documentation (this feature)

```text
specs/036-workflow-editor-monitor/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── api-endpoints.md # REST endpoint contracts
│   ├── ws-channels.md   # WebSocket channel + event contracts
│   └── ts-types.ts      # TypeScript type definitions
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code

```text
apps/web/
├── app/
│   └── (main)/
│       └── workflow-editor-monitor/
│           ├── page.tsx                          # Workflow list
│           ├── new/
│           │   └── page.tsx                      # Create new workflow (empty editor)
│           └── [id]/
│               ├── page.tsx                      # Workflow editor (YAML + graph)
│               └── executions/
│                   ├── page.tsx                  # Execution history list
│                   └── [executionId]/
│                       └── page.tsx              # Live execution monitor
│
├── components/
│   └── features/
│       └── workflows/
│           ├── WorkflowList.tsx                  # Infinite-scroll workflow cards
│           ├── WorkflowCard.tsx                  # Summary card (name/status/version)
│           ├── editor/
│           │   ├── WorkflowEditorShell.tsx        # ResizablePanelGroup: Monaco + Graph
│           │   ├── MonacoYamlEditor.tsx           # Monaco + monaco-yaml + schema
│           │   ├── WorkflowGraphPreview.tsx       # @xyflow/react + dagre (preview only)
│           │   └── EditorToolbar.tsx              # Save, version badge, validation summary
│           └── monitor/
│               ├── ExecutionMonitorShell.tsx      # Three-panel: Graph | Timeline | Detail
│               ├── ExecutionGraph.tsx             # @xyflow/react + WS-driven colors
│               ├── ExecutionTimeline.tsx          # Virtual-scroll journal event list
│               ├── StepDetailPanel.tsx            # Tab container: Overview / Reasoning / Self-Correction / Task Plan
│               ├── StepOverviewTab.tsx            # Inputs, outputs, timing, errors, quality score
│               ├── ReasoningTraceViewer.tsx       # Expandable branch tree (lazy pagination)
│               ├── SelfCorrectionChart.tsx        # Recharts LineChart (quality per iteration)
│               ├── TaskPlanViewer.tsx             # Expandable candidates → selection → parameters
│               ├── CostTracker.tsx                # Real-time totals + expandable per-step
│               └── ExecutionControls.tsx          # Pause/Resume/Cancel/Retry/Skip/Inject actions
│
├── lib/
│   ├── hooks/
│   │   ├── use-workflow-list.ts                   # useInfiniteQuery for workflow list
│   │   ├── use-workflow.ts                        # useQuery for single workflow + version
│   │   ├── use-workflow-save.ts                   # useMutation: create / PATCH workflow
│   │   ├── use-workflow-graph.ts                  # YAML → dagre nodes/edges (memoized)
│   │   ├── use-workflow-schema.ts                 # useQuery: fetch + cache JSON Schema
│   │   ├── use-execution-list.ts                  # useInfiniteQuery for execution history
│   │   ├── use-execution-monitor.ts               # State + WS subscription + reconnect
│   │   ├── use-execution-journal.ts               # Infinite scroll journal query
│   │   ├── use-step-detail.ts                     # Lazy query: step inputs/outputs/timing
│   │   ├── use-reasoning-trace.ts                 # Journal events filtered by step_id + type
│   │   ├── use-task-plan.ts                       # Lazy query: TaskPlanFullResponse
│   │   ├── use-execution-controls.ts              # All 7 control action mutations
│   │   └── use-cost-tracker.ts                    # Accumulate WS budget events
│   └── stores/
│       ├── workflow-editor-store.ts               # YAML content, validation, graph derived state
│       └── execution-monitor-store.ts             # Step statuses, selected step, WS status, costs
│
└── types/
    ├── workflows.ts                               # WorkflowDefinition, WorkflowVersion, WorkflowIR, etc.
    ├── execution.ts                               # Execution, ExecutionState, ExecutionEvent, etc.
    ├── reasoning.ts                               # ReasoningTrace, SelfCorrectionLoop, etc.
    └── task-plan.ts                               # TaskPlanRecord, Candidate, ParameterProvenance
```

**Structure Decision**: Extends the existing Next.js App Router convention (route groups, feature-grouped components, lib/hooks, lib/stores). New route group: `workflow-editor-monitor/`. New component domain: `components/features/workflows/`. New store files follow the existing pattern from `lib/stores/conversation-store.ts`.

## Implementation Phases

### Phase 1 — Foundation (Types, Stores, API Hooks)

**Goal**: Type-safe API integration and stores before any UI.

1. Add `monaco-yaml` and `@dagrejs/dagre` to `apps/web` package.json
2. Create TypeScript types: `types/workflows.ts`, `types/execution.ts`, `types/reasoning.ts`, `types/task-plan.ts` (from `contracts/ts-types.ts`)
3. Create Zustand stores: `workflow-editor-store.ts`, `execution-monitor-store.ts`
4. Create API hooks: `use-workflow-list.ts`, `use-workflow.ts`, `use-workflow-save.ts`, `use-workflow-schema.ts`
5. Create API hooks: `use-execution-list.ts`, `use-execution-monitor.ts`, `use-execution-journal.ts`
6. Create API hooks: `use-step-detail.ts`, `use-reasoning-trace.ts`, `use-task-plan.ts`, `use-execution-controls.ts`, `use-cost-tracker.ts`
7. Create MSW handlers for all endpoints
8. Add routes: skeleton pages for all 5 routes (list, new, editor, history, monitor)

**Deliverable**: All API hooks work against MSW, stores hold correct state shape, pages load without errors.

---

### Phase 2 — Workflow Editor

**Goal**: Functional YAML editor with graph preview.

1. `MonacoYamlEditor.tsx`: Dynamic import Monaco, configure `monaco-yaml` with schema from `use-workflow-schema`, wire debounced onChange to `workflow-editor-store`
2. `use-workflow-graph.ts`: Parse `compiled_ir` from WorkflowVersion into dagre-positioned `@xyflow/react` nodes and edges; memoize on YAML change (500ms debounce)
3. `WorkflowGraphPreview.tsx`: `<ReactFlow>` with `<MiniMap>`, `<Controls>`, `<Background>`; nodes colored by `hasValidationError`; fit-to-view on initial load
4. `WorkflowEditorShell.tsx`: shadcn `ResizablePanelGroup` (horizontal split: 60% editor / 40% preview); collapsible preview panel
5. `EditorToolbar.tsx`: Save button (calls `use-workflow-save`), version badge, validation error count badge
6. Wire `app/(main)/workflow-editor-monitor/[id]/page.tsx` and `new/page.tsx`

**Deliverable**: Authors can write YAML, see live graph preview, fix errors inline, and save.

---

### Phase 3 — Execution Monitor (Graph + Timeline)

**Goal**: Live execution monitoring with real-time updates.

1. `ExecutionGraph.tsx`: Extend `WorkflowGraphPreview` with step status coloring (see `data-model.md` color mapping); subscribes to `execution-monitor-store.stepStatuses`
2. `use-execution-monitor.ts`: Subscribe `wsClient.subscribe('execution:{id}', handler)`; on `step.state_changed` dispatch to store; on disconnect reconnect + re-fetch state + journal since lastSeen
3. `ExecutionTimeline.tsx`: Infinite scroll (react-virtual or native CSS) over journal events; color-coded by event category; most recent at top
4. `ExecutionMonitorShell.tsx`: Three-panel layout — left: `ExecutionGraph`, center: `ExecutionTimeline`, right: `StepDetailPanel` (hidden until step selected); responsive collapse
5. `ConnectionStatusBanner`: Reuse existing pattern from 026; show when `wsConnectionStatus !== 'connected'`
6. Wire `app/(main)/workflow-editor-monitor/[id]/executions/[executionId]/page.tsx`

**Deliverable**: Operators see real-time step color changes and streaming timeline events.

---

### Phase 4 — Step Detail (Overview + Reasoning + Self-Correction)

**Goal**: Deep-dive inspection of individual steps.

1. `StepDetailPanel.tsx`: shadcn `Tabs` — Overview / Reasoning Trace / Self-Correction / Task Plan; opens when node clicked; shows skeleton while loading
2. `StepOverviewTab.tsx`: Display inputs (JSON viewer), outputs (JSON viewer), timing, context quality score (ScoreGauge from shared components), error with stack trace
3. `ReasoningTraceViewer.tsx`: Recursive tree view of `ReasoningBranch`; expand/collapse; status icon + token badge per branch; "Load more branches" trigger at page boundary
4. `SelfCorrectionChart.tsx`: Recharts `LineChart`; Y-axis: quality score (0–1); X-axis: iteration number; reference line for convergence/budget threshold; click data point → iteration detail popover
5. Test: all tabs render correct data, empty states for steps without reasoning, error states for failed loads

**Deliverable**: Step detail shows all four tabs with correct data for any execution step.

---

### Phase 5 — Task Plan Viewer

**Goal**: Agent selection transparency per step.

1. `TaskPlanViewer.tsx`: Expandable tree: step root → "Candidates" section → each candidate (FQN, suitability score, selected badge) → "Selected Agent" section (rationale text) → "Parameters" section → each parameter (name, value, provenance badge)
2. Lazy load via `use-task-plan`: only fetches when "Task Plan" tab is opened for a step
3. Empty state: "No task plan available — this step was not dispatched to an agent"
4. Verify tab is distinct from Reasoning Trace tab (separate tab trigger, separate data source)

**Deliverable**: Task Plan tab shows full planning decision tree for any agent-dispatched step.

---

### Phase 6 — Execution Controls

**Goal**: Operator control actions with confirmation dialogs.

1. `ExecutionControls.tsx`: Toolbar with action buttons gated by execution status and user role; buttons: Pause (running only), Resume (paused only), Cancel (running/paused), Retry (failed step), Skip (blocked step), Inject Variable
2. Confirmation dialog for each action: shadcn `AlertDialog` with action name, target, and consequence text
3. Inject Variable dialog: shadcn `Dialog` with React Hook Form + Zod (variable name: string, value: JSON textarea); validation rejects empty name or invalid JSON
4. All actions via `use-execution-controls` mutations; optimistic status update on submit; rollback on error
5. RBAC gate: check `requiredRoles` against auth store; disable buttons (with tooltip) if insufficient permissions

**Deliverable**: Operators can perform all 7 control actions with confirmation; invalid actions are disabled.

---

### Phase 7 — Cost Tracker

**Goal**: Real-time cost visibility.

1. `CostTracker.tsx`: Sticky bottom panel showing total tokens + total cost USD; updates from `execution-monitor-store.totalCostUsd`; expand to show per-step breakdown sorted by cost desc; highest-cost step highlighted
2. `use-cost-tracker.ts`: Accumulates `budget.threshold` WS events into store; on step completion, fetches final step token usage; persists to store for per-step breakdown
3. Per-step breakdown fetched lazily from analytics endpoint when panel is expanded

**Deliverable**: Cost tracker shows live totals and accurate per-step breakdown when expanded.

---

### Phase 8 — Tests and Polish

**Goal**: ≥95% coverage, accessible, dark mode, responsive.

1. Unit tests for all hooks (MSW + Vitest)
2. Component tests for each panel (RTL + MSW)
3. Playwright E2E: author workflow → start execution → monitor step transitions → open step detail → view reasoning → use controls
4. Accessibility audit: keyboard navigation through graph nodes (arrow keys), screen reader labels on step nodes, focus trap in dialogs
5. Dark mode verification: Monaco theme set to `vs-dark` when `document.documentElement.classList.has('dark')`; @xyflow node styles use CSS custom properties
6. Responsive layout: mobile — controls in Sheet drawer; graph collapses to step list with status badges; detail panel full-screen

**Deliverable**: All acceptance criteria from spec met; ≥95% coverage; accessibility and dark mode pass.
