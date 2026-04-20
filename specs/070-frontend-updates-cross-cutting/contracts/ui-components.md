# UI Component Contracts: Frontend Updates

**Feature**: 070-frontend-updates-cross-cutting
**Date**: 2026-04-20

Every new component signature, state ownership, and RBAC requirement.

---

## US1 — Agent Authoring

### `AgentFormIdentityFields`

`apps/web/components/features/agents/agent-form-identity-fields.tsx`

```typescript
interface AgentFormIdentityFieldsProps {
  form: UseFormReturn<AgentFormValues>;    // React Hook Form instance
  mode: "create" | "edit";
  isLegacy: boolean;                       // true when loading agent with namespace=null
}
```

- Renders: `Select` (namespace) + `Input` (local_name) + `Textarea` (purpose, with char-count) + `Textarea` (approach) + `Select` (role_type)
- Validation: Zod schema `{namespace: z.string().min(1), localName: z.string().regex(/^[a-zA-Z0-9_-]+$/), purpose: z.string().min(50), approach: z.string().optional(), roleType: z.enum(ROLE_TYPES)}`
- RBAC: embedded in agent form, which requires `workspace_member` or higher

### `AgentFormVisibilityEditor`

`apps/web/components/features/agents/agent-form-visibility-editor.tsx`

```typescript
interface AgentFormVisibilityEditorProps {
  value: FqnPattern[];
  onChange: (patterns: FqnPattern[]) => void;
  maxPatterns?: number;                    // default 20
}
```

- Renders: repeatable pattern input row with `Input` + live-preview (audience description from `lib/validators/fqn-pattern.ts::describeAudience()`) + "Add" and "Remove" buttons
- RBAC: embedded; `workspace_admin` required to edit workspace-wide patterns

---

## US2 — Marketplace Discovery

### `AgentCardFqn` (supersedes internals of existing `AgentCard`)

`apps/web/components/features/marketplace/agent-card-fqn.tsx`

```typescript
interface AgentCardFqnProps {
  agent: AgentIdentity & { reviewSummary?: ReviewSummary };
  onInvoke?: () => void;
  onAddToCompare?: () => void;
}
```

- Renders: FQN (or "Legacy agent" pill), purpose excerpt (first 120 chars), role badge (color + text label per D-012), certification-expiry pill (green/amber/red + "Expires in N days" label), invoke button (disabled when `certification.status ∈ {expired, revoked}` with tooltip)
- RBAC: `viewer` or higher

### `MarketplaceSearchFqn`

`apps/web/components/features/marketplace/marketplace-search-fqn.tsx`

```typescript
interface MarketplaceSearchFqnProps {
  initialQuery?: string;
  onQueryChange: (query: string) => void;
}
```

- 300 ms debounce; URL-param driven (`?q=`); case-insensitive FQN-prefix match; segregates legacy agents into a collapsible "Legacy (uncategorized)" bucket when a non-empty query runs

---

## US3 — Workspace Goals

### `WorkspaceGoalHeader`

`apps/web/components/features/conversations/workspace-goal-header.tsx`

```typescript
interface WorkspaceGoalHeaderProps {
  workspaceId: string;
}
```

- Reads via `useGoalLifecycle(workspaceId)`; renders chip + title + "Complete Goal" button (disabled unless state ∈ `{open, in_progress}`); mutation via `useGoalLifecycleMutations`
- RBAC: `workspace_member` or higher

### `GoalScopedMessageFilter`

`apps/web/components/features/conversations/goal-scoped-message-filter.tsx`

```typescript
interface GoalScopedMessageFilterProps {
  workspaceId: string;
  activeGoalId: string | null;
}
```

- URL-param driven (`?goal-scoped=true`); renders toggle + banner with active goal title and dismiss action

### `DecisionRationalePanel`

`apps/web/components/features/conversations/decision-rationale-panel.tsx`

```typescript
interface DecisionRationalePanelProps {
  rationale: DecisionRationale | null;
}
```

- Renders four collapsible sub-sections (shadcn `Collapsible`); empty state when `rationale === null`
- RBAC: `workspace_member` or higher (shown in debug panel)

---

## US4 — Alerts & Bell

### `AlertSettingsPage`

`apps/web/components/features/alerts/alert-settings-page.tsx`

```typescript
// No props — page-level component reading user + workspace from auth/workspace stores
```

- Renders per-transition toggles grouped by category; delivery-method radio (`in-app` / `email` / `both`); per-interaction mute list with search and remove buttons
- RBAC: any authenticated user

### `NotificationBell`

`apps/web/components/features/alerts/notification-bell.tsx`

```typescript
interface NotificationBellProps {
  // no props — reads from alert-store + use-alert-feed
}
```

- Renders: bell icon + badge (unread count) + dropdown (latest 20 alerts) + `aria-live="polite"` region
- Subscribes to `alerts` channel on mount; reconciles on reconnect (D-005)
- RBAC: any authenticated user; rendered in global header

### `PerInteractionMuteToggle`

`apps/web/components/features/alerts/per-interaction-mute-toggle.tsx`

```typescript
interface PerInteractionMuteToggleProps {
  interactionId: string;
}
```

- Small shadcn `Toggle` embedded in interaction detail header

---

## US5 — Governance & Visibility

### `GovernanceChainEditor`

`apps/web/components/features/governance/governance-chain-editor.tsx`

```typescript
interface GovernanceChainEditorProps {
  scope: { kind: "workspace"; workspaceId: string } | { kind: "fleet"; fleetId: string };
}
```

- Three drop zones (Observer/Judge/Enforcer) rendered as shadcn `Card` with `role="button"`; HTML5 native drag-and-drop (D-002); keyboard fallback via picker dialog
- Save goes through `ConfirmDialog` summarizing the change
- RBAC: `workspace_admin` for workspace scope; `platform_admin` for fleet scope

### `VisibilityGrantsEditor`

`apps/web/components/features/governance/visibility-grants-editor.tsx`

```typescript
interface VisibilityGrantsEditorProps {
  workspaceId: string;
}
```

- Repeatable pattern input with live preview of matching agents (by FQN) using `useAgents({fqnPattern})`
- RBAC: `workspace_admin`

---

## US6 — Execution Detail

### `TrajectoryViz`

`apps/web/components/features/execution/trajectory-viz.tsx`

```typescript
interface TrajectoryVizProps {
  executionId: string;
  anchorStepIndex?: number;                // deep link target
}
```

- Virtualized list (TanStack Virtual) when `steps.length > 100`; each entry shows index + FQN + duration + tokens + efficiency badge
- URL-param: `?step=<n>` scrolls anchor into view
- RBAC: `viewer` or higher

### `CheckpointList`

`apps/web/components/features/execution/checkpoint-list.tsx`

```typescript
interface CheckpointListProps {
  executionId: string;
}
```

- Side panel list; each row has "Roll back" button opening `ConfirmDialog` with `requireTypedConfirmation={checkpoint.id}` (D-007)
- RBAC: `workspace_admin` or higher

### `DebateTranscript`

`apps/web/components/features/execution/debate-transcript.tsx`

```typescript
interface DebateTranscriptProps {
  executionId: string;
}
```

- Chat-feed rendering with participant-colored bubbles; deleted participants show tombstone badge; reasoning traces collapsible

### `ReactCycleViewer`

`apps/web/components/features/execution/react-cycle-viewer.tsx`

```typescript
interface ReactCycleViewerProps {
  executionId: string;
}
```

- One card per cycle with three collapsible sections (Thought/Action/Observation)

---

## US7 — Evaluation Suite Editor

### `RubricEditor`

`apps/web/components/features/evaluation/rubric-editor.tsx`

```typescript
interface RubricEditorProps {
  suiteId: string;
}
```

- Dimension list with add/remove/edit; weight inputs with live-sum indicator (50 ms debounce); Save disabled unless `sum === 1.0`
- RBAC: `workspace_admin` or higher

### `CalibrationBoxplot`

`apps/web/components/features/evaluation/calibration-boxplot.tsx`

```typescript
interface CalibrationBoxplotProps {
  suiteId: string;
}
```

- Recharts `ComposedChart` + custom box-plot rendering (min/Q1/median/Q3/max); outlier dot annotation when κ < 0.6

### `TrajectoryComparisonSelector`

`apps/web/components/features/evaluation/trajectory-comparison-selector.tsx`

```typescript
interface TrajectoryComparisonSelectorProps {
  value: TrajectoryComparisonMethod;
  onChange: (method: TrajectoryComparisonMethod) => void;
}
```

- shadcn `Select` with 4 options + 1-sentence description below

---

## US8 — Agent Profile Tabs

### `AgentProfileContractsTab` / `AgentProfileA2aTab` / `AgentProfileMcpTab`

`apps/web/components/features/agents/agent-profile-{contracts,a2a,mcp}-tab.tsx`

```typescript
interface AgentProfileTabProps {
  agentId: string;
}
```

- Contracts tab: chronological list with status badges; two-column diff dialog (shadcn `Dialog`)
- A2A tab: syntax-highlighted JSON via existing `CodeBlock` + Copy button; empty state with "Configure" CTA
- MCP tab: list of MCP servers with health dot + Disconnect action (uses `ConfirmDialog`)
- RBAC: `workspace_member` or higher (view); `workspace_admin` (mutations)

---

## US9 — Trust Workbench Expansions

### `CertifiersTab`, `CertificationExpiryDashboard`, `SurveillancePanel`

All under `apps/web/components/features/trust/`.

```typescript
interface CertifiersTabProps {
  // page-level; no props
}

interface CertificationExpiryDashboardProps {
  defaultSort?: "expires_at_asc" | "agent_fqn" | "certifier_name";
}

interface SurveillancePanelProps {
  agentId: string;
}
```

- Certifiers tab: form + list; validates HTTPS endpoint + PEM key
- Expiries dashboard: sortable `DataTable` with color-coded status chips (D-012)
- Surveillance panel: latest 20 signals + Recharts sparkline
- RBAC: `platform_admin` for certifier CRUD and fleet-wide expiries; `workspace_admin` for workspace-scoped surveillance

---

## US10 — Operator Dashboard Panels

### `WarmPoolPanel`, `VerdictFeed`, `DecommissionWizard`, `ReliabilityGauges`

All under `apps/web/components/features/operator/`.

```typescript
interface WarmPoolPanelProps {
  // subscribes to `warm-pool` channel globally
}

interface VerdictFeedProps {
  workspaceId: string | null;              // null = all workspaces (admin)
}

interface DecommissionWizardProps {
  agentFqn: string;
  isOpen: boolean;
  onClose: () => void;
}

interface ReliabilityGaugesProps {
  windowDays?: number;                     // default 30
}
```

- Warm-pool: shadcn `Card` grid + drawer for recent scaling events
- Verdict feed: `aria-live="polite"`; new entries flash via Tailwind `animate-pulse` for 500 ms then settle
- Decommission wizard: `Dialog` with 3-stage state machine (D-007); typed-FQN confirmation
- Reliability gauges: Recharts `RadialBarChart` per category with color thresholds
- RBAC: all `platform_admin`

---

## Shared Component Extensions

### `ConfirmDialog` extension (one-line signature change)

`apps/web/components/shared/ConfirmDialog.tsx`

```typescript
// Existing props...
interface ConfirmDialogProps {
  // ...existing...
  requireTypedConfirmation?: string;       // NEW: when present, user must type this exact value
}
```

- Backward compatible: absent prop behaves as today. Present prop disables confirm button until typed input matches.

### `WebSocketClient` extension

`apps/web/lib/ws.ts`

- Add three new channel-type string literals to the existing union: `"alerts" | "governance-verdicts" | "warm-pool"`
- No signature changes to `subscribe` / `unsubscribe` methods
