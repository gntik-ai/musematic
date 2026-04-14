# Data Model: Workflow Editor and Execution Monitor

**Phase 1 — Design Output**  
**Date**: 2026-04-13  
**Feature**: 036-workflow-editor-monitor

This document defines the TypeScript types for the frontend. These types mirror the backend API response shapes (see `contracts/api-types.ts` for the full typed interfaces).

---

## Core Entities

### Workflow Definition

```typescript
interface WorkflowDefinition {
  id: string;                      // UUID
  workspaceId: string;
  name: string;
  description: string | null;
  currentVersionId: string;
  currentVersionNumber: number;
  status: 'active' | 'archived' | 'draft';
  createdAt: string;               // ISO 8601
  updatedAt: string;
}

interface WorkflowVersion {
  id: string;
  workflowId: string;
  versionNumber: number;
  yamlContent: string;             // raw YAML text
  compiledIr: WorkflowIR;          // parsed DAG
  createdAt: string;
  createdBy: string;               // user ID
}
```

### Workflow IR (compiled DAG)

```typescript
interface WorkflowIR {
  steps: WorkflowIRStep[];
  triggers: WorkflowTrigger[];
  metadata: {
    name: string;
    description: string | null;
    version: string;
    defaultReasoningMode?: ReasoningMode;
    defaultContextBudget?: ContextBudget;
  };
}

interface WorkflowIRStep {
  id: string;                      // step identifier (from YAML key)
  name: string;
  type: WorkflowStepType;
  agentFqn?: string;               // agent fully qualified name
  reasoningMode?: ReasoningMode;
  contextBudget?: ContextBudget;
  timeout?: number;                // seconds
  dependencies: string[];          // step ids this step depends on
  retryConfig?: {
    maxAttempts: number;
    backoffSeconds: number;
  };
  approvalConfig?: {
    approverRole: string;
    timeoutSeconds: number;
  };
}

type WorkflowStepType =
  | 'agent_task'
  | 'parallel_fan_out'
  | 'parallel_fan_in'
  | 'conditional'
  | 'approval_gate'
  | 'webhook_trigger'
  | 'delay'
  | 'compensation';

type ReasoningMode =
  | 'chain_of_thought'
  | 'tree_of_thought'
  | 'self_correction'
  | 'direct'
  | 'iterative'
  | 'exploratory';

interface ContextBudget {
  maxTokens: number;
  maxRounds: number;
  maxCostUsd: number;
}

interface WorkflowTrigger {
  type: 'manual' | 'scheduled' | 'webhook' | 'kafka_event' | 'goal_created' | 'completion';
  config: Record<string, unknown>;
}
```

---

## Execution Entities

### Execution

```typescript
interface Execution {
  id: string;
  workflowId: string;
  workflowVersionId: string;
  workflowVersionNumber: number;
  status: ExecutionStatus;
  triggeredBy: string;             // user ID or 'system'
  correlationContext: CorrelationContext;
  startedAt: string;
  completedAt: string | null;
  failureReason: string | null;
}

type ExecutionStatus =
  | 'queued'
  | 'running'
  | 'paused'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'canceled'
  | 'compensating';

interface CorrelationContext {
  workspaceId: string;
  executionId: string;
  workflowId: string;
  goalId?: string;
  conversationId?: string;
}
```

### Execution State (live projected state)

```typescript
interface ExecutionState {
  executionId: string;
  status: ExecutionStatus;
  completedStepIds: string[];
  activeStepIds: string[];
  pendingStepIds: string[];
  failedStepIds: string[];
  skippedStepIds: string[];
  waitingForApprovalStepIds: string[];
  stepResults: Record<string, StepResult>;  // stepId → result
  lastEventSequence: number;
  updatedAt: string;
}

interface StepResult {
  stepId: string;
  status: StepStatus;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  error: StepError | null;
  retryCount: number;
}

type StepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'waiting_for_approval'
  | 'canceled';

interface StepError {
  code: string;
  message: string;
  details: Record<string, unknown> | null;
}
```

### Execution Event (journal entry)

```typescript
interface ExecutionEvent {
  id: string;
  executionId: string;
  sequence: number;
  eventType: ExecutionEventType;
  stepId: string | null;
  agentFqn: string | null;
  payload: Record<string, unknown>;  // type-specific JSONB
  createdAt: string;
}

type ExecutionEventType =
  | 'EXECUTION_CREATED'
  | 'EXECUTION_STARTED'
  | 'EXECUTION_PAUSED'
  | 'EXECUTION_RESUMED'
  | 'EXECUTION_COMPLETED'
  | 'EXECUTION_FAILED'
  | 'EXECUTION_CANCELED'
  | 'STEP_DISPATCHED'
  | 'STEP_RUNTIME_STARTED'
  | 'STEP_COMPLETED'
  | 'STEP_FAILED'
  | 'STEP_SKIPPED'
  | 'STEP_RETRIED'
  | 'STEP_WAITING_FOR_APPROVAL'
  | 'STEP_APPROVED'
  | 'STEP_REJECTED'
  | 'HOT_CHANGED'
  | 'REASONING_TRACE_EMITTED'
  | 'SELF_CORRECTION_STARTED'
  | 'SELF_CORRECTION_ITERATION'
  | 'SELF_CORRECTION_CONVERGED'
  | 'SELF_CORRECTION_BUDGET_EXCEEDED'
  | 'BUDGET_THRESHOLD_80'
  | 'BUDGET_THRESHOLD_90'
  | 'BUDGET_THRESHOLD_100';
```

### Step Detail (enriched per-step view)

```typescript
interface StepDetail {
  stepId: string;
  executionId: string;
  status: StepStatus;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown> | null;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  contextQualityScore: number | null;  // 0.0–1.0
  error: StepError | null;
  tokenUsage: TokenUsage | null;
}

interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  estimatedCostUsd: number;
}
```

---

## Reasoning Entities

### Reasoning Trace

```typescript
interface ReasoningTrace {
  executionId: string;
  stepId: string;
  treeId: string;
  rootBranchId: string;
  branches: ReasoningBranch[];
  totalBranches: number;           // for pagination display
  budgetSummary: BudgetSummary;
}

interface ReasoningBranch {
  id: string;
  parentId: string | null;
  depth: number;
  status: 'active' | 'completed' | 'pruned' | 'failed';
  chainOfThought: ChainOfThoughtStep[];
  tokenUsage: TokenUsage;
  budgetRemainingAtCompletion: number | null;
  createdAt: string;
  completedAt: string | null;
}

interface ChainOfThoughtStep {
  index: number;
  thought: string;
  confidence: number | null;       // 0.0–1.0
  tokenCost: number;
}

interface BudgetSummary {
  mode: ReasoningMode;
  maxTokens: number;
  usedTokens: number;
  maxRounds: number;
  usedRounds: number;
  maxCostUsd: number;
  usedCostUsd: number;
  status: 'active' | 'exhausted' | 'completed';
}
```

### Self-Correction Loop

```typescript
interface SelfCorrectionLoop {
  loopId: string;
  executionId: string;
  stepId: string;
  iterations: SelfCorrectionIteration[];
  finalStatus: 'converged' | 'budget_exceeded' | 'escalated' | 'running';
  startedAt: string;
  completedAt: string | null;
  budgetConsumed: {
    tokens: number;
    costUsd: number;
    rounds: number;
  };
}

interface SelfCorrectionIteration {
  iterationNumber: number;        // 1-based
  qualityScore: number;           // 0.0–1.0
  delta: number;                  // change from previous iteration
  status: 'continue' | 'converged' | 'budget_exceeded' | 'escalated';
  tokenCost: number;
  durationMs: number;
  thoughts: string | null;        // brief reasoning summary
}
```

---

## Task Plan Entities

```typescript
interface TaskPlanRecord {
  executionId: string;
  stepId: string;
  selectedAgentFqn: string | null;
  selectedToolFqn: string | null;
  rationaleText: string;
  candidateAgents: TaskPlanCandidate[];
  candidateTools: TaskPlanCandidate[];
  parameters: ParameterProvenance[];
  rejectedAlternatives: RejectedAlternative[];
  persistedAt: string;
}

interface TaskPlanCandidate {
  fqn: string;
  displayName: string;
  suitabilityScore: number;        // 0.0–1.0
  isSelected: boolean;
  tags: string[];
}

interface ParameterProvenance {
  parameterName: string;
  value: unknown;
  source: ParameterSource;
  sourceDescription: string;       // human-readable provenance label
}

type ParameterSource =
  | 'workflow_definition'
  | 'step_dependency_output'
  | 'operator_injection'
  | 'execution_context'
  | 'default_value';

interface RejectedAlternative {
  fqn: string;
  rejectionReason: string;
}
```

---

## Cost Entities

```typescript
interface ExecutionCostSummary {
  executionId: string;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalTokens: number;
  totalCostUsd: number;
  stepBreakdown: StepCostEntry[];
  lastUpdatedAt: string;
}

interface StepCostEntry {
  stepId: string;
  stepName: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  costUsd: number;
  percentageOfTotal: number;       // derived client-side
}
```

---

## Frontend Store Shapes

### WorkflowEditorStore (Zustand)

```typescript
interface WorkflowEditorStore {
  // Editor state
  yamlContent: string;
  validationErrors: ValidationError[];
  isDirty: boolean;
  isSaving: boolean;
  lastSavedVersionId: string | null;

  // Graph preview
  graphNodes: WorkflowGraphNode[];   // derived from yamlContent
  graphEdges: WorkflowGraphEdge[];   // derived from yamlContent
  parseError: string | null;         // YAML parse failure (distinct from schema errors)

  // Actions
  setYamlContent: (yaml: string) => void;
  setValidationErrors: (errors: ValidationError[]) => void;
  markSaved: (versionId: string) => void;
}

interface ValidationError {
  line: number;
  column: number;
  message: string;
  severity: 'error' | 'warning';
  path: string;                      // JSON pointer into the YAML
}

interface WorkflowGraphNode {
  id: string;
  type: 'step';
  position: { x: number; y: number };
  data: {
    stepId: string;
    label: string;
    stepType: WorkflowStepType;
    agentFqn?: string;
    hasValidationError: boolean;
  };
}

interface WorkflowGraphEdge {
  id: string;
  source: string;
  target: string;
  type: 'smoothstep';
}
```

### ExecutionMonitorStore (Zustand)

```typescript
interface ExecutionMonitorStore {
  // Execution state
  executionId: string | null;
  executionStatus: ExecutionStatus | null;
  stepStatuses: Record<string, StepStatus>;   // stepId → status
  lastEventSequence: number;

  // UI state
  selectedStepId: string | null;
  activeDetailTab: 'overview' | 'reasoning' | 'self-correction' | 'task-plan';

  // Cost accumulation (real-time from WS)
  totalTokens: number;
  totalCostUsd: number;

  // Connection
  wsConnectionStatus: 'connected' | 'connecting' | 'reconnecting' | 'disconnected';

  // Actions
  setExecutionState: (state: ExecutionState) => void;
  applyEvent: (event: ExecutionEvent) => void;
  selectStep: (stepId: string | null) => void;
  setDetailTab: (tab: ExecutionMonitorStore['activeDetailTab']) => void;
  setWsStatus: (status: ExecutionMonitorStore['wsConnectionStatus']) => void;
  accumulateCost: (tokens: number, costUsd: number) => void;
}
```

---

## State Transitions

### Step Status → Graph Node Color

| Status | Color | Tailwind class |
|--------|-------|----------------|
| `pending` | Gray | `fill-muted-foreground` |
| `running` | Blue | `fill-blue-500` |
| `completed` | Green | `fill-green-500` |
| `failed` | Red | `fill-red-500` |
| `waiting_for_approval` | Yellow | `fill-yellow-400` |
| `skipped` | Gray (light) | `fill-muted` |
| `canceled` | Gray (dark) | `fill-gray-600` |

### Self-Correction Loop Final Status

| Status | Chart annotation |
|--------|-----------------|
| `converged` | Green dashed line at convergence point |
| `budget_exceeded` | Red dashed line at budget limit |
| `escalated` | Orange annotation at last iteration |
| `running` | No annotation (chart ends at latest iteration) |
