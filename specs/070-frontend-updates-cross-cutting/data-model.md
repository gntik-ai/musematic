# Data Model: Frontend Updates for All New Features

**Feature**: 070-frontend-updates-cross-cutting
**Date**: 2026-04-20

## Overview

Frontend-only feature — no database or DDL changes. This document defines **TypeScript types** for UI entities, **hook contracts** for TanStack Query usage, and **URL-param schemas** for deep-linking.

All types live under `apps/web/types/`. Backend truth is still owned by Python/Go services; these types are the shape the frontend expects to receive.

---

## Type Definitions

### `types/fqn.ts`

```typescript
export type FqnPattern = string;           // e.g. "workspace:*/agent:*" or "ops:kyc-verifier"

export type RoleType =
  | "researcher"
  | "analyst"
  | "reviewer"
  | "operator"
  | "verdict_authority"
  | "tool_user"
  | "integrator";

export interface AgentIdentity {
  id: string;                              // UUID (stable legacy id)
  namespace: string | null;                // null = legacy agent
  localName: string | null;                // null = legacy agent
  fqn: string | null;                      // "namespace:localName" or null
  purpose: string | null;                  // ≥ 50 chars when present
  approach: string | null;
  roleType: RoleType | null;
  visibilityPatterns: FqnPattern[];
  certification: CertificationStatus | null;
}

export interface CertificationStatus {
  certifierId: string;
  certifierName: string;
  issuedAt: string;                        // ISO 8601
  expiresAt: string;                       // ISO 8601
  status: "valid" | "expiring_soon" | "expired" | "revoked";
  daysUntilExpiry: number;                 // negative if expired
}
```

### `types/goal.ts`

```typescript
export type GoalState = "open" | "in_progress" | "completed" | "cancelled";

export interface WorkspaceGoal {
  id: string;                              // GID
  workspaceId: string;
  title: string;
  description: string;
  state: GoalState;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
}

export interface DecisionRationale {
  toolChoices: Array<{ tool: string; reason: string }>;
  retrievedMemories: Array<{ memoryId: string; relevanceScore: number; excerpt: string }>;
  riskFlags: Array<{ category: string; severity: "low" | "medium" | "high"; note: string }>;
  policyChecks: Array<{ policyId: string; policyName: string; verdict: "allow" | "deny" | "warn" }>;
}
```

### `types/alerts.ts`

```typescript
export type AlertTransitionType =
  | "execution.failed"
  | "execution.completed"
  | "interaction.idle"
  | "trust.certification_expired"
  | "trust.certification_expiring_soon"
  | "governance.verdict_issued"
  | "fleet.member_unhealthy"
  | "warm_pool.below_target";

export type AlertDeliveryMethod = "in-app" | "email" | "both";

export interface AlertRule {
  id: string;
  userId: string;
  workspaceId: string | null;              // null = global user preference
  transitionType: AlertTransitionType;
  enabled: boolean;
  deliveryMethod: AlertDeliveryMethod;
}

export interface InteractionAlertMute {
  interactionId: string;
  userId: string;
  mutedAt: string;
}

export interface Alert {
  id: string;
  transitionType: AlertTransitionType;
  resourceRef: { kind: string; id: string; url: string };
  timestamp: string;
  read: boolean;
  title: string;
  summary: string;
}
```

### `types/governance.ts`

```typescript
export interface GovernanceChain {
  workspaceId: string;
  observerAgentFqn: string | null;         // null = fleet default
  judgeAgentFqn: string | null;
  enforcerAgentFqn: string | null;
  updatedAt: string;
  updatedBy: string;
}

export interface VisibilityGrant {
  id: string;
  workspaceId: string;
  pattern: FqnPattern;
  createdBy: string;
  createdAt: string;
}

export interface GovernanceVerdict {
  id: string;
  offendingAgentFqn: string;
  verdictType: "policy_violation" | "safety_violation" | "certification_invalid";
  enforcerAgentFqn: string;
  actionTaken: "quarantine" | "warn" | "block";
  issuedAt: string;
  rationaleExcerpt: string;
}
```

### `types/trajectory.ts`

```typescript
export type EfficiencyScore = "high" | "medium" | "low" | "unscored";

export interface TrajectoryStep {
  index: number;
  toolOrAgentFqn: string;
  startedAt: string;
  durationMs: number;
  tokenUsage: { prompt: number; completion: number };
  efficiencyScore: EfficiencyScore;
  summary: string;
}

export interface Checkpoint {
  id: string;
  executionId: string;
  stepIndex: number;
  createdAt: string;
  reason: string;
  isRollbackCandidate: boolean;
}

export interface DebateTurn {
  participantAgentFqn: string;
  participantDisplayName: string;
  participantIsDeleted: boolean;
  position: "support" | "oppose" | "neutral";
  content: string;
  reasoningTraceId: string | null;
  timestamp: string;
}

export interface ReactCycle {
  index: number;
  thought: string;
  action: { tool: string; args: Record<string, unknown> };
  observation: string;
  durationMs: number;
}
```

### `types/evaluation.ts`

```typescript
export type RubricScaleType = "numeric_1_5" | "categorical_enum";

export interface RubricDimension {
  id: string;
  name: string;
  description: string;
  weight: number;                          // 0.0–1.0; sum must be 1.0
  scaleType: RubricScaleType;
  categoricalValues: string[] | null;      // required when scaleType = categorical_enum
}

export interface CalibrationScore {
  dimensionId: string;
  dimensionName: string;
  distribution: { min: number; q1: number; median: number; q3: number; max: number };
  kappa: number;                           // inter-rater agreement
  isOutlier: boolean;                      // true when kappa < 0.6
}

export type TrajectoryComparisonMethod =
  | "exact_match"
  | "semantic_similarity"
  | "edit_distance"
  | "trajectory_judge";
```

### `types/contracts.ts`

```typescript
export interface AgentContract {
  id: string;
  version: string;                         // semver
  status: "active" | "superseded";
  publishedAt: string;
  supersededAt: string | null;
  signatories: string[];                   // FQNs
  documentExcerpt: string;
}

export interface A2AAgentCard {
  // A2A protocol JSON document
  card: Record<string, unknown>;
  lastPublishedAt: string | null;
}

export interface McpServerRegistration {
  id: string;
  name: string;
  endpoint: string;
  capabilityCounts: { tools: number; resources: number };
  healthStatus: "healthy" | "unhealthy" | "unknown";
  lastHealthCheckAt: string | null;
}
```

### `types/operator.ts`

```typescript
export interface WarmPoolProfile {
  name: "small" | "medium" | "large";
  targetReplicas: number;
  actualReplicas: number;
  deltaStatus: "on_target" | "within_20_percent" | "below_target";
  lastScalingEvents: Array<{
    at: string;
    from: number;
    to: number;
    reason: string;
  }>;
}

export interface DecommissionPlan {
  agentFqn: string;
  downstreamDependencies: Array<{ kind: string; id: string; displayName: string }>;
  dryRunDiff: Array<{ resourceKind: string; change: string }>;
}

export interface ReliabilityGauge {
  category: "api" | "execution" | "event_delivery";
  availabilityPercent: number;             // 0–100
  windowDays: number;                      // 30
  status: "green" | "amber" | "red";
}

export interface ThirdPartyCertifier {
  id: string;
  displayName: string;
  endpoint: string;                        // HTTPS only
  publicKeyPem: string;
  authorizedRoleTypes: RoleType[];
  createdAt: string;
}

export interface SurveillanceSignal {
  timestamp: string;
  category: "behavior_drift" | "policy_violation_attempt" | "performance_anomaly";
  value: number;
  note: string;
}
```

---

## Hook Contracts (TanStack Query)

All hooks follow the `lib/hooks/use-api.ts` factory pattern:
- **Query hooks**: return `{ data, isLoading, isError, error, refetch }`
- **Mutation hooks**: return `{ mutate, mutateAsync, isPending, isError, error }`
- All hooks invalidate relevant query keys on related mutations

| Hook | Kind | Query key | Invalidates |
|---|---|---|---|
| `useAgentIdentityMutations(agentId)` | mutation | — | `["agent", id]`, `["marketplace-agents"]` |
| `useGoalLifecycle(workspaceId)` | query | `["goal", workspaceId]` | — |
| `useGoalLifecycleMutations(workspaceId)` | mutation | — | `["goal", workspaceId]`, `["conversation-messages", wsId]` |
| `useAlertRules(userId, workspaceId)` | query | `["alert-rules", userId, wsId]` | — |
| `useAlertRulesMutations(userId)` | mutation | — | `["alert-rules", userId]` |
| `useAlertFeed()` (existing — extended) | infinite query | `["alert-feed", userId]` | — |
| `useGovernanceChain(workspaceId)` | query | `["governance-chain", wsId]` | — |
| `useGovernanceChainMutations(workspaceId)` | mutation | — | `["governance-chain", wsId]` |
| `useVisibilityGrants(workspaceId)` | query | `["visibility-grants", wsId]` | — |
| `useVisibilityGrantMutations(workspaceId)` | mutation | — | `["visibility-grants", wsId]` |
| `useExecutionTrajectory(executionId)` | query | `["trajectory", executionId]` | — |
| `useExecutionCheckpoints(executionId)` | query | `["checkpoints", executionId]` | — |
| `useCheckpointRollback(executionId)` | mutation | — | `["execution", executionId]`, `["trajectory", eid]` |
| `useDebateTranscript(executionId)` | query | `["debate", executionId]` | — |
| `useReactCycles(executionId)` | query | `["react-cycles", executionId]` | — |
| `useRubricEditor(suiteId)` | query + mutation | `["rubric", suiteId]` | `["rubric", suiteId]` |
| `useCalibrationScores(suiteId)` | query | `["calibration", suiteId]` | — |
| `useAgentContracts(agentId)` | query | `["contracts", agentId]` | — |
| `useContractMutations(agentId)` | mutation | — | `["contracts", agentId]` |
| `useA2aAgentCard(agentId)` | query | `["a2a-card", agentId]` | — |
| `useMcpServers(agentId)` | query | `["mcp-servers", agentId]` | — |
| `useMcpServerMutations(agentId)` | mutation | — | `["mcp-servers", agentId]` |
| `useThirdPartyCertifiers()` | query | `["certifiers"]` | — |
| `useCertifierMutations()` | mutation | — | `["certifiers"]` |
| `useCertificationExpiries(sort)` | query | `["expiries", sort]` | — |
| `useSurveillanceSignals(agentId)` | query | `["surveillance", agentId]` | — |
| `useWarmPoolStatus()` | query | `["warm-pool"]` | — |
| `useVerdictFeed()` | infinite query | `["verdicts"]` | — |
| `useDecommissionWizard(agentId)` | mutation + stages | — | `["agent", agentId]`, `["marketplace-agents"]` |
| `useReliabilityGauges()` | query | `["reliability"]` | — |

---

## URL-Param Schemas

| Page | Query params | Example |
|---|---|---|
| Marketplace | `?q=<fqn-prefix>&role=<RoleType>&cert=<valid|expiring|expired>` | `/marketplace?q=ops:&role=reviewer&cert=valid` |
| Workspace conversation | `?goal-scoped=true` | `/conversations/abc?goal-scoped=true` |
| Alert settings | `?scope=<global|workspace:<id>>` | `/settings/alerts?scope=workspace:ws-123` |
| Execution detail | `?tab=<trajectory|checkpoints|debate|react>&step=<n>` | `/operator/executions/exec-1?tab=trajectory&step=17` |
| Evaluation suite | `?section=<rubric|calibration|comparison>` | `/evaluation-testing/suites/s-1?section=calibration` |
| Agent profile | `?tab=<overview|contracts|a2a|mcp>` | `/agents/agent-1?tab=a2a` |
| Trust workbench | `?tab=<queue|certifiers|expiries|surveillance>` | `/trust-workbench?tab=certifiers` |
| Operator dashboard | `?panel=<warm-pool|verdicts|reliability>` | `/operator?panel=warm-pool` |

---

## WebSocket Subscription Envelopes

All envelopes follow the existing `WebSocketClient` message shape. See [`contracts/websocket-channels.md`](contracts/websocket-channels.md) for full payload schemas.

```typescript
interface WsEnvelope<Channel extends string, Payload> {
  channel: Channel;
  topic: string;                           // channel-specific topic key
  event: string;                           // event name (e.g. "alert.created")
  payload: Payload;
  timestamp: string;
}
```

**New channels**:
- `alerts` with topic `user:<userId>` — payload: `Alert`
- `governance-verdicts` with topic `workspace:<workspaceId>` — payload: `GovernanceVerdict`
- `warm-pool` with topic `global` — payload: `WarmPoolProfile` (delta update)

---

## State Transitions

### Goal lifecycle (US3)

```
open ──user marks in progress──▶ in_progress ──"Complete Goal" click──▶ completed
  │                                  │
  ├──user cancels──▶ cancelled       └──user cancels──▶ cancelled
```

Backend owns the transition; UI reads state from `WorkspaceGoal.state` and offers the "Complete Goal" button only when `state in {open, in_progress}`.

### Alert read state (US4)

```
unread ──user opens bell dropdown and views alert──▶ read
       ──"Mark all as read"──▶ read
```

Unread count decrements as reads persist. On WebSocket reconnect, bell reconciles against server truth (D-005).

### Decommission wizard stages (US10)

```
idle ──Start──▶ warning ──Next──▶ dry_run ──Confirm(typed-fqn)──▶ submitting ──success──▶ done
                    │                          │
                    └──Cancel──▶ idle         └──Cancel──▶ idle
```

Each stage is a local React state; no server call until `Confirm`.

---

## Retention / Caching Policies

| Data | Cache duration | Reason |
|---|---|---|
| Marketplace FQN search results | TanStack Query default (5 min stale, 1 h cache) | Existing feature 035 convention |
| Goal lifecycle | `staleTime: 30s` | Conversation view updates frequently |
| Alert rules | `staleTime: 60s` | User-modified sparsely |
| Alert feed | `staleTime: 0` + WS-driven invalidation | Real-time |
| Governance chain | `staleTime: 5min` | Rarely changed |
| Execution trajectory | `staleTime: Infinity` (executions are immutable once complete) | Immutable data |
| Certification expiries | `staleTime: 5min` | Background scan feeds them |
| Warm-pool status | `staleTime: 10s` + WS-driven invalidation | Near real-time |
| Verdict feed | WS-driven; no polling | Real-time |
