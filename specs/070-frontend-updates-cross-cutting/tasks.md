# Tasks: Frontend Updates for All New Features

**Input**: Design documents from `specs/070-frontend-updates-cross-cutting/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ui-components.md ✅, contracts/websocket-channels.md ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story (US1–US10) to enable independent implementation and testing. No tests requested — implementation tasks only.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to
- All paths are relative to `apps/web/`

---

## Phase 1: Setup (Type Definitions & Shared Infrastructure)

**Purpose**: Create all new TypeScript type files, validators, and the WebSocketClient channel extension. These files have no dependencies on each other and all block downstream phases.

- [x] T001 [P] Create `types/fqn.ts`: export `FqnPattern`, `RoleType`, `AgentIdentity`, `CertificationStatus` per data-model.md
- [x] T002 [P] Create `types/goal.ts`: export `GoalState`, `WorkspaceGoal`, `DecisionRationale` per data-model.md
- [x] T003 [P] Create `types/alerts.ts`: export `AlertTransitionType`, `AlertDeliveryMethod`, `AlertRule`, `InteractionAlertMute`, `Alert` per data-model.md
- [x] T004 [P] Create `types/governance.ts`: export `GovernanceChain`, `VisibilityGrant`, `GovernanceVerdict` per data-model.md
- [x] T005 [P] Create `types/trajectory.ts`: export `EfficiencyScore`, `TrajectoryStep`, `Checkpoint`, `DebateTurn`, `ReactCycle` per data-model.md
- [x] T006 [P] Create `types/evaluation.ts`: export `RubricScaleType`, `RubricDimension`, `CalibrationScore`, `TrajectoryComparisonMethod` per data-model.md
- [x] T007 [P] Create `types/contracts.ts`: export `AgentContract`, `A2AAgentCard`, `McpServerRegistration` per data-model.md
- [x] T008 [P] Create `types/operator.ts`: export `WarmPoolProfile`, `DecommissionPlan`, `ReliabilityGauge`, `ThirdPartyCertifier`, `SurveillanceSignal` per data-model.md
- [x] T009 [P] Create `lib/validators/fqn-pattern.ts`: FQN regex validator + `describeAudience(pattern: FqnPattern): string` for live preview (e.g. "All workspaces, agents starting with 'compliance-'")
- [x] T010 [P] Create `lib/validators/rubric-weights.ts`: `validateWeightSum(dimensions: RubricDimension[]): { sum: number; isValid: boolean }` with 50 ms debounce export
- [x] T011 Extend `lib/ws.ts`: add `"alerts" | "governance-verdicts" | "warm-pool"` to the existing channel-type string-literal union (no signature changes to `subscribe`/`unsubscribe`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared UI primitives and state used by multiple user stories. MUST complete before any user story phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T012 Create `store/alert-store.ts`: Zustand store with `unreadCount: number`, `isDropdownOpen: boolean`, `increment()`, `setUnreadCount(n)`, `markAllAsRead()` — per research.md D-005
- [x] T013 Extend `components/shared/ConfirmDialog.tsx`: add optional `requireTypedConfirmation?: string` prop; when present, disable confirm button until typed input matches exact value — backward-compatible per D-007
- [x] T014 Extend `lib/hooks/use-alert-feed.ts`: subscribe to `alerts` WS channel on mount; call `alertStore.increment()` on `alert.created`; call `alertStore.setUnreadCount()` on `alert.read`; invalidate `["alert-feed", userId]` query on both events per websocket-channels.md

**Checkpoint**: Foundation ready — all user story phases can now begin.

---

## Phase 3: User Story 1 — Agent Authoring with FQN, Purpose, Role, Visibility (Priority: P1) 🎯 MVP

**Goal**: Agent create/edit forms accept namespace, localName, purpose (≥ 50 chars), approach, roleType, and visibility patterns; legacy agents show banner and block save until identity is complete.

**Independent Test**: Navigate to `/agents/create`, fill namespace="ops", localName="kyc-v2", purpose < 50 chars → Save disabled; fill ≥ 50 chars → Save enabled; add visibility pattern → preview renders; Save → POST includes all fields.

- [x] T015 [P] [US1] Create `lib/hooks/use-agent-identity-mutations.ts`: `useAgentIdentityMutations(agentId)` mutation hook; invalidates `["agent", id]` and `["marketplace-agents"]` on success
- [x] T016 [P] [US1] Create `components/features/agents/agent-form-identity-fields.tsx`: renders namespace `Select`, localName `Input`, purpose `Textarea` (char-counter, min 50, counter turns red below threshold), approach `Textarea`, roleType `Select`; accepts `{ form, mode, isLegacy }` props per ui-components.md; Zod schema validates all fields; legacy-agent banner when `isLegacy=true`
- [x] T017 [US1] Create `components/features/agents/agent-form-visibility-editor.tsx`: repeatable FQN pattern input rows; each row shows `Input` + live audience preview via `describeAudience()` from `lib/validators/fqn-pattern.ts`; Add/Remove buttons; max 20 patterns; `workspace_admin` RBAC gate on workspace-wide patterns
- [x] T018 [US1] Modify `app/(main)/agents/create/page.tsx`: integrate `AgentFormIdentityFields` and `AgentFormVisibilityEditor` into the existing agent creation form; wire `useAgentIdentityMutations`; redirect to agent detail showing FQN on success
- [x] T019 [US1] Modify `app/(main)/agents/[id]/edit/page.tsx`: same form integration as T018; pre-populate existing values; when `agent.namespace === null` render `isLegacy=true` to show banner; Save blocked until both namespace and localName provided

**Checkpoint**: US1 fully functional — agent create/edit with FQN identity works independently.

---

## Phase 4: User Story 2 — Marketplace Discovery via FQN + Certification (Priority: P1)

**Goal**: Marketplace cards show FQN, purpose excerpt, role badge, and certification-expiry pill; FQN-prefix search with 300 ms debounce segregates legacy agents into a collapsible bucket.

**Independent Test**: Navigate to `/marketplace`; type `ops:` in search → URL updates to `?q=ops%3A`; only FQN-prefixed agents appear; legacy bucket appears collapsed; one card shows amber "Expires in N days"; expired card's Invoke button is disabled with tooltip.

- [x] T020 [P] [US2] Create `components/features/marketplace/agent-card-fqn.tsx`: renders FQN (or "Legacy agent" neutral-gray pill when `fqn=null`), purpose excerpt (first 120 chars), role badge (color + text label per D-012), certification-expiry pill (green/amber/red + text label), Invoke button (disabled with tooltip when `status ∈ {expired, revoked}`); props: `{ agent: AgentIdentity & { reviewSummary? }, onInvoke?, onAddToCompare? }`
- [x] T021 [P] [US2] Modify `components/features/marketplace/marketplace-search-fqn.tsx`: implement 300 ms debounce; update `?q=` URL param on change; case-insensitive FQN-prefix matching; emit `onQueryChange`; when query non-empty segregate results with legacy agents into "Legacy (uncategorized)" bucket
- [x] T022 [US2] Modify `app/(main)/marketplace/page.tsx`: replace existing card internals with `AgentCardFqn`; wire `MarketplaceSearchFqn` for FQN search; render "Legacy (uncategorized)" collapsible `Collapsible` bucket beneath main results; preserve existing `useInfiniteQuery` pagination and `useComparisonStore` selection
- [x] T023 [US2] Modify `app/(main)/marketplace/[namespace]/[name]/page.tsx`: add certification status section showing certifier name, issued/expires dates, status chip with text label, and "Agent not currently certified" warning banner when `status ∈ {expired, revoked}`

**Checkpoint**: US2 fully functional — FQN marketplace search and certification status work independently.

---

## Phase 5: User Story 3 — Workspace Goal Lifecycle, Goal-Scoped Filter, Decision Rationale (Priority: P1)

**Goal**: Workspace conversation view shows goal chip + "Complete Goal" button; goal-scoped filter toggles GID-tagged message view; agent response debug panel exposes decision rationale.

**Independent Test**: Open `/conversations/<id>` with active goal → chip shows `in_progress`; toggle goal-scoped → URL updates `?goal-scoped=true`, banner appears; click agent response → debug panel → Decision Rationale shows 4 sections; click "Complete Goal" → confirm → chip changes to `completed`.

- [x] T024 [P] [US3] Create `lib/hooks/use-goal-lifecycle.ts`: `useGoalLifecycle(workspaceId)` query (key `["goal", workspaceId]`, staleTime 30s) + `useGoalLifecycleMutations(workspaceId)` mutation (invalidates `["goal", wsId]` and `["conversation-messages", wsId]`)
- [x] T025 [P] [US3] Create `components/features/conversations/workspace-goal-header.tsx`: reads via `useGoalLifecycle`; renders shadcn status chip + goal title + "Complete Goal" button; button disabled unless `state ∈ {open, in_progress}`; mutation via `useGoalLifecycleMutations`; RBAC `workspace_member`
- [x] T026 [P] [US3] Create `components/features/conversations/goal-scoped-message-filter.tsx`: URL-param driven (`?goal-scoped=true`); renders shadcn `Toggle` + dismissible banner "Filtered to goal: {title}"; dismiss clears `goal-scoped` param; props: `{ workspaceId, activeGoalId }`
- [x] T027 [P] [US3] Create `components/features/conversations/decision-rationale-panel.tsx`: renders 4 shadcn `Collapsible` sections (Tool Choices, Retrieved Memories, Risk Flags, Policy Checks) populated from `DecisionRationale` type; empty state when `rationale === null`; props: `{ rationale: DecisionRationale | null }`
- [x] T028 [US3] Modify `app/(main)/conversations/[id]/page.tsx`: mount `WorkspaceGoalHeader` at top; mount `GoalScopedMessageFilter` below header; wire `DecisionRationalePanel` into existing debug panel on agent-response click

**Checkpoint**: US3 fully functional — workspace goal lifecycle and decision rationale work independently.

---

## Phase 6: User Story 4 — Alert Settings + Notification Bell (Priority: P2)

**Goal**: `/settings/alerts` page for configuring transition rules and delivery; notification bell in global header with real-time unread count via WebSocket; per-interaction mute toggle.

**Independent Test**: Open `/settings/alerts`; defaults show critical transitions ON; toggle `interaction.idle` OFF, save; simulate WS `alert.created` → bell increments within 3s; navigate to conversation → mute toggle → simulate event → bell does NOT increment.

- [x] T029 [P] [US4] Create `lib/hooks/use-alert-rules.ts`: `useAlertRules(userId, workspaceId)` query (key `["alert-rules", userId, wsId]`, staleTime 60s) + `useAlertRulesMutations(userId)` mutation (invalidates `["alert-rules", userId]`)
- [x] T030 [P] [US4] Create `components/features/alerts/notification-bell.tsx`: bell icon + unread count badge (from `alert-store`); dropdown with latest 20 alerts (via `useAlertFeed`); `aria-live="polite"` region; subscribes to `alerts` WS channel on mount; reconciles unread count on WS reconnect by calling `GET /api/v1/alerts/unread-count`; disconnected indicator when WS offline; RBAC: any authenticated user
- [x] T031 [P] [US4] Create `components/features/alerts/alert-settings-page.tsx`: per-transition toggle list grouped by category (critical/informational defaults from FR-018); delivery-method radio (`in-app`/`email`/`both`); per-interaction mute list with search and remove buttons; "Recommended defaults" banner; reads from `useAlertRules`; saves via `useAlertRulesMutations`
- [x] T032 [P] [US4] Create `components/features/alerts/per-interaction-mute-toggle.tsx`: small shadcn `Toggle`; props: `{ interactionId: string }`; mutes/unmutes alerts for the interaction; RBAC: workspace_member
- [x] T033 [US4] Create `app/(main)/settings/alerts/page.tsx`: render `AlertSettingsPage`; route guard `workspace_member` or higher; support `?scope=` URL param for global vs workspace-scoped view
- [x] T034 [US4] Add `NotificationBell` to the global header component (locate existing header in `components/shared/` or `app/(main)/layout.tsx`); position in top-right nav
- [x] T035 [US4] Add `PerInteractionMuteToggle` to `app/(main)/conversations/[id]/page.tsx` interaction detail header section

**Checkpoint**: US4 fully functional — alert settings, notification bell, and mute toggle work independently.

---

## Phase 7: User Story 5 — Governance Chain Editor + Visibility Grants (Priority: P2)

**Goal**: `/settings/governance` editor with Observer/Judge/Enforcer drag-and-drop slots; `/settings/visibility` for FQN visibility grants; fleet settings embed the governance editor.

**Independent Test**: Open `/settings/governance`; three empty slots render; drag `ops:verdict-authority` card into Judge slot; Save → ConfirmDialog summarizes change; confirm → PATCH fires; open `/settings/visibility`; add grant pattern → preview lists matching agents; Save.

- [x] T036 [P] [US5] Create `lib/hooks/use-governance-chain.ts`: `useGovernanceChain(workspaceId)` query (key `["governance-chain", wsId]`, staleTime 5min) + `useGovernanceChainMutations(workspaceId)` mutation (invalidates `["governance-chain", wsId]`)
- [x] T037 [P] [US5] Create `lib/hooks/use-visibility-grants.ts`: `useVisibilityGrants(workspaceId)` query (key `["visibility-grants", wsId]`) + `useVisibilityGrantMutations(workspaceId)` mutation (invalidates `["visibility-grants", wsId]`)
- [x] T038 [P] [US5] Create `components/features/governance/governance-chain-editor.tsx`: three shadcn `Card` drop zones (Observer/Judge/Enforcer); HTML5 native `draggable`/`onDragStart`/`onDragOver`/`onDrop` (D-002 — same pattern as feature 043 `PolicyAttachmentPanel`); each zone shows current FQN or "No {role} assigned — fleet default applies"; keyboard fallback: `role="button"` + `tabIndex=0` + Space/Enter opens picker dialog; Save goes through `ConfirmDialog` summarizing change; RBAC `workspace_admin` (workspace) / `platform_admin` (fleet)
- [x] T039 [P] [US5] Create `components/features/governance/visibility-grants-editor.tsx`: repeatable FQN pattern input with live preview of matching agents (via `useAgents({fqnPattern})`); Add/Remove buttons; legacy-agent warning icon when FQN missing; props: `{ workspaceId }`; RBAC `workspace_admin`
- [x] T040 [US5] Create `app/(main)/settings/governance/page.tsx`: render `GovernanceChainEditor` with `scope={{ kind: "workspace", workspaceId }}`; route guard `workspace_admin`
- [x] T041 [US5] Create `app/(main)/settings/visibility/page.tsx`: render `VisibilityGrantsEditor`; route guard `workspace_admin`
- [x] T042 [US5] Modify `app/(main)/fleet/[id]/settings/page.tsx`: embed `GovernanceChainEditor` with `scope={{ kind: "fleet", fleetId }}`; route guard `platform_admin`

**Checkpoint**: US5 fully functional — governance chain and visibility grants editors work independently.

---

## Phase 8: User Story 6 — Execution Detail: Trajectory, Checkpoints, Debate, ReAct (Priority: P2)

**Goal**: Execution detail page gains four tabs (Trajectory/Checkpoints/Debate/ReAct) via `?tab=` routing; trajectory virtualizes at > 100 steps; rollback opens typed-confirmation dialog.

**Independent Test**: Open `/operator/executions/<id>?tab=trajectory`; 150-step execution renders virtualized list (~30 in DOM); `?step=75` scrolls step 75 into view; Checkpoints sidebar "Roll back" → ConfirmDialog requires typed ID; Debate tab shows participant bubbles; ReAct tab shows Thought/Action/Observation cycles.

- [x] T043 [P] [US6] Create `lib/hooks/use-execution-trajectory.ts`: `useExecutionTrajectory(executionId)` query (key `["trajectory", executionId]`, staleTime Infinity — executions are immutable)
- [x] T044 [P] [US6] Create `lib/hooks/use-execution-checkpoints.ts`: `useExecutionCheckpoints(executionId)` query (key `["checkpoints", executionId]`) + `useCheckpointRollback(executionId)` mutation (invalidates `["execution", executionId]`, `["trajectory", eid]`)
- [x] T045 [P] [US6] Create `lib/hooks/use-debate-transcript.ts`: `useDebateTranscript(executionId)` query (key `["debate", executionId]`)
- [x] T046 [P] [US6] Create `lib/hooks/use-react-cycles.ts`: `useReactCycles(executionId)` query (key `["react-cycles", executionId]`)
- [x] T047 [P] [US6] Create `components/features/execution/trajectory-viz.tsx`: TanStack Virtual vertical list (virtual when `steps.length > 100`, plain list otherwise per D-003); each step card: index + FQN + duration + tokens + efficiency badge (green/amber/red text label per D-012); `?step=<n>` deep-link scrolls anchor into view and highlights it; props: `{ executionId, anchorStepIndex? }`
- [x] T048 [P] [US6] Create `components/features/execution/checkpoint-list.tsx`: side-panel list; each row has "Roll back" button wired to `useCheckpointRollback`; opens `ConfirmDialog` with `requireTypedConfirmation={checkpoint.id}` (D-007); RBAC `workspace_admin`
- [x] T049 [P] [US6] Create `components/features/execution/debate-transcript.tsx`: chat-feed layout with participant-colored bubbles; deleted participants render tombstone badge "Agent no longer exists"; reasoning traces collapsible per turn; props: `{ executionId }`
- [x] T050 [P] [US6] Create `components/features/execution/react-cycle-viewer.tsx`: one shadcn `Card` per ReAct cycle; three `Collapsible` sub-sections (Thought/Action/Observation); props: `{ executionId }`
- [x] T051 [US6] Modify `app/(main)/operator/executions/[id]/page.tsx`: add shadcn `Tabs` with `?tab=` URL routing (trajectory/checkpoints/debate/react); mount respective components in each tab; pass `anchorStepIndex` from `?step=` param to `TrajectoryViz`

**Checkpoint**: US6 fully functional — execution trajectory, checkpoints, debate, and ReAct tabs work independently.

---

## Phase 9: User Story 7 — Evaluation Suite Editor: Rubric, Calibration, Comparison (Priority: P2)

**Goal**: Evaluation suite editor gains `?section=` routing for rubric configuration (weight sum validator), calibration box plots (Recharts), and trajectory comparison method selector.

**Independent Test**: Open `/evaluation-testing/suites/<id>?section=rubric`; add 3 dimensions summing to 1.0 → sum shows green, Save enabled; change one weight → sum shows red within 100ms, Save disabled; switch to `?section=calibration` → box plot renders per dimension; switch to `?section=comparison` → Select shows 4 methods.

- [x] T052 [P] [US7] Create `lib/hooks/use-rubric-editor.ts`: `useRubricEditor(suiteId)` combined query + mutation (key `["rubric", suiteId]`; mutation invalidates `["rubric", suiteId]`)
- [x] T053 [P] [US7] Create `lib/hooks/use-calibration-scores.ts`: `useCalibrationScores(suiteId)` query (key `["calibration", suiteId]`)
- [x] T054 [P] [US7] Create `components/features/evaluation/rubric-editor.tsx`: dimension list with add/remove/edit inline; each row: name `Input` + description `Input` + weight `Input` (numeric); live sum indicator below list (50 ms debounce, green when `sum === 1.0`, red otherwise); Save disabled unless valid; uses `validateWeightSum()` from `lib/validators/rubric-weights.ts`; `React.memo` weight rows to prevent re-render churn; RBAC `workspace_admin`
- [x] T055 [P] [US7] Create `components/features/evaluation/calibration-boxplot.tsx`: Recharts `ComposedChart` with custom box-plot rendering (one box per dimension: min/Q1/median/Q3/max whisker); outlier dot annotation when `kappa < 0.6` with label "κ = {value}"; `<ResponsiveContainer>` for responsive sizing; props: `{ suiteId }`
- [x] T056 [P] [US7] Create `components/features/evaluation/trajectory-comparison-selector.tsx`: shadcn `Select` with 4 options (exact_match, semantic_similarity, edit_distance, trajectory_judge); 1-sentence description rendered below select on change; props: `{ value, onChange }`
- [x] T057 [US7] Modify `app/(main)/evaluation-testing/suites/[id]/page.tsx`: add `?section=` URL routing (rubric/calibration/comparison); mount `RubricEditor`, `CalibrationBoxplot`, `TrajectoryComparisonSelector` in respective sections

**Checkpoint**: US7 fully functional — rubric editor, calibration box plots, and comparison selector work independently.

---

## Phase 10: User Story 8 — Agent Profile: Contracts, A2A, MCP (Priority: P3)

**Goal**: Agent profile gains Contracts/A2A/MCP tabs via `?tab=` routing; contracts show diff dialog; A2A tab renders JSON with Copy; MCP tab lists servers with Disconnect.

**Independent Test**: Open `/agents/<id>?tab=contracts`; 3 contracts listed chronologically with badges; select 2 → Diff button enables → dialog opens; switch `?tab=a2a` → JSON block with Copy; switch `?tab=mcp` → server list; Disconnect → ConfirmDialog → confirm → server removed.

- [x] T058 [P] [US8] Create `lib/hooks/use-agent-contracts.ts`: `useAgentContracts(agentId)` query (key `["contracts", agentId]`) + `useContractMutations(agentId)` mutation (invalidates `["contracts", agentId]`)
- [x] T059 [P] [US8] Create `lib/hooks/use-a2a-agent-card.ts`: `useA2aAgentCard(agentId)` query (key `["a2a-card", agentId]`)
- [x] T060 [P] [US8] Create `lib/hooks/use-mcp-servers.ts`: `useMcpServers(agentId)` query (key `["mcp-servers", agentId]`) + `useMcpServerMutations(agentId)` mutation (invalidates `["mcp-servers", agentId]`)
- [x] T061 [P] [US8] Create `components/features/agents/agent-profile-contracts-tab.tsx`: chronological list with status badges (`active` / `superseded`); multi-select checkbox; "Diff" button enabled when exactly 2 selected; two-column diff shadcn `Dialog`; props: `{ agentId }`; RBAC view `workspace_member`, mutations `workspace_admin`
- [x] T062 [P] [US8] Create `components/features/agents/agent-profile-a2a-tab.tsx`: renders `A2AAgentCard.card` as syntax-highlighted JSON via existing `CodeBlock` component + Copy button; empty state with "Configure" CTA when `card === null`; props: `{ agentId }`
- [x] T063 [P] [US8] Create `components/features/agents/agent-profile-mcp-tab.tsx`: list of `McpServerRegistration` items; each row: name + capability counts + health status dot (green/amber/red with text label) + Disconnect button; Disconnect opens `ConfirmDialog`; wired to `useMcpServerMutations`; props: `{ agentId }`
- [x] T064 [US8] Modify `app/(main)/agents/[id]/page.tsx`: add shadcn `Tabs` with `?tab=` URL routing (overview/contracts/a2a/mcp); mount `AgentProfileContractsTab`, `AgentProfileA2aTab`, `AgentProfileMcpTab` in respective tabs; preserve existing overview content

**Checkpoint**: US8 fully functional — agent profile contract/A2A/MCP tabs work independently.

---

## Phase 11: User Story 9 — Trust Workbench: Certifiers, Expiry Dashboard, Surveillance (Priority: P3)

**Goal**: Trust workbench gains Certifiers/Expiries/Surveillance tabs; certifier form validates HTTPS endpoint and PEM key; expiry dashboard is sortable with URL-persisted sort; surveillance panel shows sparkline.

**Independent Test**: Open `/trust-workbench?tab=certifiers`; click "Add Certifier"; enter `http://` endpoint → validation error; enter valid HTTPS + PEM → Save → certifier appears; switch `?tab=expiries` → 47 certifications sorted by expiry; sort column → URL updates; switch `?tab=surveillance` → pick agent → sparkline renders with 20 signals.

- [x] T065 [P] [US9] Create `lib/hooks/use-third-party-certifiers.ts`: `useThirdPartyCertifiers()` query (key `["certifiers"]`) + `useCertifierMutations()` mutation (invalidates `["certifiers"]`)
- [x] T066 [P] [US9] Create `lib/hooks/use-certification-expiries.ts`: `useCertificationExpiries(sort)` query (key `["expiries", sort]`, staleTime 5min); sort param maps to `"expires_at_asc" | "agent_fqn" | "certifier_name"`
- [x] T067 [P] [US9] Create `lib/hooks/use-surveillance-signals.ts`: `useSurveillanceSignals(agentId)` query (key `["surveillance", agentId]`); returns latest 20 signals
- [x] T068 [P] [US9] Create `components/features/trust/certifiers-tab.tsx`: certifier form with display name `Input`, endpoint `Input` (Zod validates HTTPS-only — reject `http://`), PEM public key `Textarea` (validates PEM header/footer format), scope `Select`; form via React Hook Form + Zod; list of existing certifiers with delete action; RBAC `platform_admin`
- [x] T069 [P] [US9] Create `components/features/trust/certification-expiry-dashboard.tsx`: sortable `DataTable` (existing shared component) with columns: agent FQN, certifier name, issued, expires, status chip (green/amber/red with text label per D-012); click column header toggles sort; sort state persisted to `?sort=` URL param; props: `{ defaultSort? }`
- [x] T070 [P] [US9] Create `components/features/trust/surveillance-panel.tsx`: agent picker `Select`; when agent selected renders latest 20 `SurveillanceSignal` items in list + Recharts `LineChart` sparkline over time; `<ResponsiveContainer>`; props: `{ agentId }`
- [x] T071 [US9] Modify `app/(main)/trust-workbench/page.tsx`: extend existing `?tab=` router to add `certifiers`, `expiries`, `surveillance` tabs; mount `CertifiersTab`, `CertificationExpiryDashboard`, `SurveillancePanel`; preserve existing queue and detail tabs

**Checkpoint**: US9 fully functional — certifier management, expiry dashboard, and surveillance panel work independently.

---

## Phase 12: User Story 10 — Operator Dashboard: Warm Pool, Verdicts, Decommission, Gauges (Priority: P3)

**Goal**: Operator dashboard gains warm-pool card grid (live via WS), verdict feed (`aria-live`), 3-stage decommission wizard with typed-FQN confirmation, and Recharts radial reliability gauges.

**Independent Test**: Open `/operator?panel=warm-pool`; 3 profile cards show target vs actual; simulate WS `warm-pool.updated` → card updates in place; simulate `below_target` → card flashes red; scroll to verdict feed → simulate `verdict.issued` → new entry flashes at top; click "Decommission Agent" → 3-stage wizard; type FQN → confirm → agent moves to `retiring`; reliability gauges show radial bars with color thresholds.

- [x] T072 [P] [US10] Create `lib/hooks/use-warm-pool-status.ts`: `useWarmPoolStatus()` query (key `["warm-pool"]`, staleTime 10s); WS `warm-pool` channel subscription in component (see T076)
- [x] T073 [P] [US10] Create `lib/hooks/use-verdict-feed.ts`: `useVerdictFeed()` infinite query (key `["verdicts"]`); WS `governance-verdicts` channel subscription in component (see T077)
- [x] T074 [P] [US10] Create `lib/hooks/use-decommission-wizard.ts`: stage state machine (`idle → warning → dry_run → submitting → done`; Cancel → `idle` from any stage); mutation fires only on `Confirm` in `dry_run` stage; invalidates `["agent", agentId]` and `["marketplace-agents"]`; returns `{ stage, plan, advance, cancel, confirmFqn, setConfirmFqn }`
- [x] T075 [P] [US10] Create `lib/hooks/use-reliability-gauges.ts`: `useReliabilityGauges(windowDays?)` query (key `["reliability"]`)
- [x] T076 [P] [US10] Create `components/features/operator/warm-pool-panel.tsx`: `md:grid-cols-3` shadcn `Card` grid; each card: profile name + targetReplicas vs actualReplicas + delta badge; amber badge when `deltaStatus === "within_20_percent"`; subscribes to `warm-pool` WS channel on mount; on `warm-pool.updated` event update matching profile card by `profile.name`; on `below_target` transition flash card red (Tailwind `animate-pulse` 500ms); click card opens shadcn `Sheet` drawer with 5 most recent scaling events
- [x] T077 [P] [US10] Create `components/features/operator/verdict-feed.tsx`: `aria-live="polite"` region; subscribes to `governance-verdicts` WS channel; on `verdict.issued` prepend entry with `animate-pulse` flash 500ms then settle; entry shows offending FQN + verdictType + enforcerFqn + actionTaken; on `verdict.superseded` strike-through superseded entry without removing; props: `{ workspaceId: string | null }`
- [x] T078 [P] [US10] Create `components/features/operator/decommission-wizard.tsx`: shadcn `Dialog` with 3-stage state machine from `useDecommissionWizard`; Stage 1: warning + downstream dependencies list + Next; Stage 2: dry-run diff + Next; Stage 3: typed-FQN `ConfirmDialog` with `requireTypedConfirmation={agentFqn}` (D-007); props: `{ agentFqn, isOpen, onClose }`; RBAC `platform_admin`
- [x] T079 [P] [US10] Create `components/features/operator/reliability-gauges.tsx`: three Recharts `RadialBarChart` gauges (api/execution/event_delivery); each shows `availabilityPercent` with color threshold (green ≥ 99.5%, amber ≥ 99%, red < 99%); text label + percentage in center; `<ResponsiveContainer>`; props: `{ windowDays? }`
- [x] T080 [US10] Modify `app/(main)/operator/page.tsx`: add `?panel=` URL routing (warm-pool/verdicts/reliability); mount `WarmPoolPanel`, `VerdictFeed`, `DecommissionWizard`, `ReliabilityGauges`; "Decommission Agent" button per agent row opens `DecommissionWizard` with that agent's FQN; preserve existing operator dashboard content

**Checkpoint**: US10 fully functional — warm pool, verdict feed, decommission wizard, and reliability gauges work independently.

---

## Phase 13: Polish & Cross-Cutting Concerns

**Purpose**: MSW mocks, E2E Playwright scenarios, backward-compatibility verification, and accessibility/responsive checks across all user stories.

- [x] T081 [P] Add MSW handlers for all new API endpoints in `mocks/handlers/`: agents FQN (namespace, localName, purpose, roleType, visibility), goals lifecycle, alert rules + unread-count, governance chain + visibility grants, execution trajectory + checkpoints + debate + react-cycles, rubric + calibration scores, agent contracts + A2A card + MCP servers, certifiers + certification expiries + surveillance signals, warm-pool status + decommission plan + reliability gauges, verdicts feed
- [X] T082 [P] Create `e2e/agent-fqn-authoring.spec.ts`: implements Q1 scenario from quickstart.md (char-counter gating Save, visibility pattern live preview, legacy-agent banner, POST payload assertion)
- [X] T083 [P] Create `e2e/marketplace-fqn-discovery.spec.ts`: implements Q2 scenario (FQN-prefix search, legacy bucket, certification pills, disabled Invoke button)
- [X] T084 [P] Create `e2e/workspace-goal-lifecycle.spec.ts`: implements Q3 scenario (goal chip states, goal-scoped filter URL param, Decision Rationale 4 sections, "Complete Goal" confirmation)
- [X] T085 [P] Create `e2e/alert-settings-and-bell.spec.ts`: implements Q4 scenario (defaults, toggle save, WS-driven bell increment, mute toggle, WS disconnect/reconnect reconciliation)
- [X] T086 [P] Create `e2e/governance-chain-editor.spec.ts`: implements Q5 scenario (drag to Judge slot, ConfirmDialog, PATCH call, visibility grant save; keyboard-only path)
- [X] T087 [P] Create `e2e/execution-trajectory.spec.ts`: implements Q6 scenario (virtualized list DOM count, `?step=75` scroll, rollback typed confirmation, Debate tombstone, ReAct collapsible)
- [X] T088 [P] Create `e2e/evaluation-rubric-editor.spec.ts`: implements Q7 scenario (sum indicator green/red within 100ms, Save gate, calibration box plot, comparison dropdown)
- [X] T089 [P] Create `e2e/agent-profile-a2a-mcp.spec.ts`: implements Q8 scenario (contracts diff dialog, A2A JSON + Copy, MCP Disconnect confirmation)
- [X] T090 [P] Create `e2e/trust-workbench-certifiers.spec.ts`: implements Q9 scenario (HTTPS/PEM validation, certifier appears in list, expiry sort URL param, surveillance sparkline)
- [X] T091 [P] Create `e2e/operator-dashboard-expansions.spec.ts`: implements Q10 scenario (warm-pool WS update, below_target flash, verdict feed aria-live, decommission wizard 3-stage typed-FQN, reliability gauges)
- [X] T092 Verify existing Playwright suite passes without regressions (`npx playwright test` on pre-existing scenarios) — backward-compatibility gate per SC-007
- [x] T093 Verify Vitest coverage ≥ 80% statements on all new components under `components/features/` (SC-010); fix any coverage gaps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T001–T010 fully parallel
- **Foundational (Phase 2)**: Depends on T001 (types/alerts.ts for T012), T011 (ws.ts for T014); T012–T014 can run in parallel with each other
- **User Stories (Phase 3–12)**: All depend on Phase 2 completion; stories can proceed in priority order or in parallel by team member
- **Polish (Phase 13)**: T081–T091 depend on all component tasks completing; T092–T093 depend on T081–T091

### User Story Dependencies

| Story | Depends on | Notes |
|-------|-----------|-------|
| US1 (P1) | Phase 2 complete | Independent |
| US2 (P1) | Phase 2 complete; T001 (types/fqn.ts) | Independent |
| US3 (P1) | Phase 2 complete; T002 (types/goal.ts) | Independent |
| US4 (P2) | Phase 2 complete; T003 (types/alerts.ts), T012 (alert-store), T014 (use-alert-feed) | Bell real-time — highest risk |
| US5 (P2) | Phase 2 complete; T004 (types/governance.ts), T013 (ConfirmDialog) | HTML5 DnD — medium risk |
| US6 (P2) | Phase 2 complete; T005 (types/trajectory.ts), T013 (ConfirmDialog), T010 (validators) | Virtualization — medium risk |
| US7 (P2) | Phase 2 complete; T006 (types/evaluation.ts), T010 (rubric-weights validator) | Weight validator — medium risk |
| US8 (P3) | Phase 2 complete; T007 (types/contracts.ts), T013 (ConfirmDialog) | Independent |
| US9 (P3) | Phase 2 complete; T001 (types/fqn.ts), T008 (types/operator.ts) | Independent |
| US10 (P3) | Phase 2 complete; T008 (types/operator.ts), T011 (ws.ts), T013 (ConfirmDialog) | WS channels — medium risk |

### Within Each User Story

- Hooks (marked [P]) → Components (marked [P]) → Page modifications (sequential, depends on components)
- Hooks and components for the same story can be written in parallel

### Parallel Opportunities

All Phase 1 type files (T001–T010) run fully in parallel — one developer can write all 8 type files + 2 validators simultaneously. Within each user story phase, all [P]-marked hook and component tasks run in parallel. The 10 E2E Playwright files (T082–T091) are all independent and fully parallelizable.

---

## Parallel Example: User Story 6 (Execution Detail)

```bash
# Start all in parallel after Phase 2 complete:
Task: "Create lib/hooks/use-execution-trajectory.ts"      # T043 [P]
Task: "Create lib/hooks/use-execution-checkpoints.ts"     # T044 [P]
Task: "Create lib/hooks/use-debate-transcript.ts"         # T045 [P]
Task: "Create lib/hooks/use-react-cycles.ts"              # T046 [P]
Task: "Create components/.../trajectory-viz.tsx"          # T047 [P]
Task: "Create components/.../checkpoint-list.tsx"         # T048 [P]
Task: "Create components/.../debate-transcript.tsx"       # T049 [P]
Task: "Create components/.../react-cycle-viewer.tsx"      # T050 [P]

# After T043–T050 complete:
Task: "Modify operator/executions/[id]/page.tsx"          # T051 (sequential)
```

---

## Implementation Strategy

### MVP First (User Stories 1–3 Only)

1. Complete Phase 1: Setup (T001–T011)
2. Complete Phase 2: Foundational (T012–T014)
3. Complete Phase 3: US1 Agent Authoring (T015–T019)
4. Complete Phase 4: US2 Marketplace FQN (T020–T023)
5. Complete Phase 5: US3 Workspace Goals (T024–T028)
6. **STOP and VALIDATE**: Test Q1–Q3 scenarios from quickstart.md
7. Deploy/demo — all P1 user stories complete

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1+US2+US3 (P1) → Test independently → Deploy (MVP)
3. Add US4+US5+US6+US7 (P2) → Test independently → Deploy
4. Add US8+US9+US10 (P3) → Test independently → Deploy
5. Polish → E2E coverage → Final release

### Parallel Team Strategy

With 3+ developers after Phase 2 completes:
- Developer A: US1 (T015–T019) + US2 (T020–T023)
- Developer B: US3 (T024–T028) + US4 (T029–T035)
- Developer C: US5 (T036–T042) + US6 (T043–T051)
- Developer D: US7 (T052–T057) + US8 (T058–T064)
- Developer E: US9 (T065–T071) + US10 (T072–T080)

---

## Notes

- **[P]** tasks operate on different files with no competing dependencies — safe to run in parallel
- **[USn]** label maps task to specific user story for traceability
- `requireTypedConfirmation` (T013) is used by US6 rollback (T048), US10 decommission (T078) — verify extension before those stories start
- `describeAudience()` (T009) is used by US1 visibility editor (T017) and US5 visibility grants (T039) — verify before those stories start
- `validateWeightSum()` (T010) is used by US7 rubric editor (T054) — verify before that story starts
- Legacy-agent tolerance (D-006): `AgentCardFqn` (T020) renders "Legacy agent" pill; `AgentFormIdentityFields` (T016) renders legacy banner; `VisibilityGrantsEditor` (T039) shows warning icon — three independent surfaces, same null-FQN pattern
- Backward-compat (T092): run before closing the feature branch — no existing page behavior may change for non-FQN agents
