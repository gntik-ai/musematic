# Data Model: Operator Dashboard and Diagnostics

**Phase**: Phase 1 — Design  
**Feature**: [spec.md](spec.md)

## TypeScript Types

### Enumerations

```typescript
// Service availability status — from GET /health dependency entries
export type ServiceStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

// Service type classification
export type ServiceType = 'data_store' | 'satellite'

// Execution active status (subset of full ExecutionStatus for operator table)
export type ActiveExecutionStatus = 'running' | 'paused' | 'waiting_for_approval' | 'compensating'

// Alert severity — maps to monitor.alerts event payload
export type AlertSeverity = 'info' | 'warning' | 'error' | 'critical'

// Attention urgency — maps to backend AttentionUrgency enum
export type AttentionUrgency = 'low' | 'medium' | 'high' | 'critical'

// Attention target context — for navigation on click
export type AttentionTargetType = 'execution' | 'interaction' | 'goal'

// Reasoning mode for trace steps
export type ReasoningMode = 'chain_of_thought' | 'tree_of_thought' | 'react' | 'reflection' | 'direct' | 'code_as_reasoning'

// Budget resource dimensions
export type BudgetDimension = 'tokens' | 'tool_invocations' | 'memory_writes' | 'elapsed_time'

// Context data source types for quality provenance
export type ContextSourceType = 'memory' | 'knowledge_graph' | 'evaluation' | 'workspace_context' | 'system_prompt'
```

---

### Operator Overview Entities

```typescript
// OperatorMetrics — consumed from GET /api/v1/dashboard/metrics (US1)
export interface OperatorMetrics {
  activeExecutions: number
  queuedSteps: number
  pendingApprovals: number
  recentFailures: number              // last 1 hour window
  avgLatencyMs: number                // p50 across active executions
  fleetHealthScore: number            // 0–100 composite
  computedAt: string                  // ISO 8601 — used to detect stale
}

// ServiceHealthEntry — single service status (US1)
export interface ServiceHealthEntry {
  serviceKey: string                  // e.g., 'postgresql', 'redis', 'runtime_controller'
  displayName: string                 // Human-readable label
  serviceType: ServiceType
  status: ServiceStatus
  latencyMs: number | null
}

// ServiceHealthSnapshot — consumed from GET /health (US1)
export interface ServiceHealthSnapshot {
  overallStatus: ServiceStatus
  uptimeSeconds: number
  services: ServiceHealthEntry[]      // 12 entries (8 stores + 4 satellite services)
  checkedAt: string
}

// SERVICE_DISPLAY_NAMES — static mapping for health panel labels
export const SERVICE_DISPLAY_NAMES: Record<string, { label: string; type: ServiceType }> = {
  postgresql: { label: 'PostgreSQL', type: 'data_store' },
  redis: { label: 'Redis', type: 'data_store' },
  kafka: { label: 'Kafka', type: 'data_store' },
  qdrant: { label: 'Qdrant', type: 'data_store' },
  neo4j: { label: 'Neo4j', type: 'data_store' },
  clickhouse: { label: 'ClickHouse', type: 'data_store' },
  opensearch: { label: 'OpenSearch', type: 'data_store' },
  minio: { label: 'MinIO', type: 'data_store' },
  runtime_controller: { label: 'Runtime Controller', type: 'satellite' },
  reasoning_engine: { label: 'Reasoning Engine', type: 'satellite' },
  sandbox_manager: { label: 'Sandbox Manager', type: 'satellite' },
  simulation_controller: { label: 'Simulation Controller', type: 'satellite' },
}
```

---

### Active Executions Entities

```typescript
// ActiveExecution — row in the real-time executions table (US2)
export interface ActiveExecution {
  id: string                          // UUID
  workflowName: string                // from workflow definition
  agentFqn: string                    // namespace:local_name
  currentStepLabel: string | null
  status: ActiveExecutionStatus
  startedAt: string                   // ISO 8601
  // Derived client-side
  elapsedMs: number                   // computed as Date.now() - startedAt; updated every second
}

// ActiveExecutionsFilters — for the status filter control (US2)
export interface ActiveExecutionsFilters {
  status: ActiveExecutionStatus | 'all'
  sortBy: 'started_at' | 'elapsed'
}
```

---

### Alert Feed Entities

```typescript
// OperatorAlert — a single alert from monitor.alerts WebSocket channel (US3)
export interface OperatorAlert {
  id: string                          // generated client-side (Date.now() + Math.random())
  severity: AlertSeverity
  sourceService: string
  timestamp: string                   // ISO 8601
  message: string                     // summary (one line)
  description: string | null          // full details
  suggestedAction: string | null
}

// AlertFeedState — Zustand store shape (US3)
export interface AlertFeedState {
  alerts: OperatorAlert[]             // ring buffer, max 200 entries (newest first)
  isConnected: boolean
  severityFilter: AlertSeverity | 'all'
  // Actions
  addAlert: (alert: Omit<OperatorAlert, 'id'>) => void
  setConnected: (connected: boolean) => void
  setSeverityFilter: (filter: AlertSeverity | 'all') => void
  clearAlerts: () => void
}
```

---

### Attention Feed Entities

```typescript
// AttentionEvent — a single attention request (US6)
export interface AttentionEvent {
  id: string                          // UUID from backend
  sourceAgentFqn: string
  urgency: AttentionUrgency
  contextSummary: string              // brief message from agent
  targetType: AttentionTargetType | null   // derived from which related_*_id is set
  targetId: string | null             // execution, interaction, or goal ID for navigation
  status: 'pending' | 'acknowledged' | 'resolved' | 'dismissed'
  createdAt: string
}

// AttentionFeedState — Zustand store shape (US6)
export interface AttentionFeedState {
  events: AttentionEvent[]            // pending attention requests, newest first
  // Actions
  setEvents: (events: AttentionEvent[]) => void
  addEvent: (event: AttentionEvent) => void
  acknowledgeEvent: (id: string) => void
}

// Navigation helper — given an AttentionEvent, returns the app route
// export function getAttentionNavTarget(event: AttentionEvent): string
```

---

### Queue Backlog + Reasoning Budget Entities

```typescript
// QueueTopicLag — single topic lag entry (US5)
export interface QueueTopicLag {
  topic: string                       // Kafka topic name
  lag: number                         // unconsumed message count
  warning: boolean                    // lag > 10,000 threshold
}

// QueueLagSnapshot — consumed from GET /api/v1/dashboard/queue-lag (US5)
export interface QueueLagSnapshot {
  topics: QueueTopicLag[]
  computedAt: string
}

// ReasoningBudgetUtilization — consumed from GET /api/v1/dashboard/reasoning-budget-utilization (US5)
export interface ReasoningBudgetUtilization {
  totalCapacityTokens: number
  usedTokens: number
  utilizationPct: number              // 0–100
  activeExecutionCount: number
  criticalPressure: boolean           // utilizationPct > 90
  computedAt: string
}

// Recharts BarChart data shape for queue backlog
// [{ topic: string, lag: number, warning: boolean }, ...]
export type QueueLagChartDataPoint = QueueTopicLag
```

---

### Execution Drill-Down Entities

```typescript
// SelfCorrectionIteration — a single correction cycle within a reasoning step (US4)
export interface SelfCorrectionIteration {
  iterationIndex: number
  originalOutputSummary: string
  correctionReason: string
  correctedOutputSummary: string
  tokenDelta: number                  // additional tokens used for correction
}

// ReasoningTraceStep — a single step in the reasoning trace (US4)
export interface ReasoningTraceStep {
  stepIndex: number
  stepId: string
  mode: ReasoningMode
  inputSummary: string                // truncated at 500 chars
  outputSummary: string               // truncated at 500 chars; full output via storageRef
  tokenCount: number
  durationMs: number
  selfCorrectionIterations: SelfCorrectionIteration[]
  // Full output expansion
  fullOutputRef: string | null        // MinIO ref if available
}

// ReasoningTrace — full trace for an execution (US4)
export interface ReasoningTrace {
  executionId: string
  steps: ReasoningTraceStep[]
  totalTokens: number
  totalDurationMs: number
  totalCorrectionIterations: number
}

// ContextSource — a single contributing data source (US4)
export interface ContextSource {
  sourceType: ContextSourceType
  displayLabel: string                // e.g., "Memory (episodic)", "Knowledge Graph"
  qualityScore: number                // 0–100
  contributionWeight: number          // 0–1, fraction of context
  provenanceRef: string | null        // reference to the specific memory/knowledge node
}

// ContextQualityView — full context provenance for an execution (US4)
export interface ContextQualityView {
  executionId: string
  assemblyRecordId: string
  overallQualityScore: number         // 0–100 composite
  sources: ContextSource[]
  assembledAt: string
}

// BudgetDimensionUsage — single resource dimension (US4)
export interface BudgetDimensionUsage {
  dimension: BudgetDimension
  label: string                       // "Tokens", "Tool Invocations", "Memory Writes", "Elapsed Time"
  used: number
  limit: number
  unit: string                        // "tokens", "calls", "writes", "seconds"
  utilizationPct: number              // (used / limit) * 100
  nearLimit: boolean                  // utilizationPct > 90
}

// BudgetStatus — full budget consumption for an execution (US4)
export interface BudgetStatus {
  executionId: string
  dimensions: BudgetDimensionUsage[]  // always 4 dimensions
  isActive: boolean                   // false if execution completed
  computedAt: string
}
```

---

### Connection State

```typescript
// ConnectionStatus — tracks WebSocket health for the status banner
export interface ConnectionStatus {
  isConnected: boolean
  lastConnectedAt: string | null
  isPollingFallback: boolean          // true when using 30s polling after disconnect
}
```

---

## Entity Relationships

```text
OperatorMetrics + ServiceHealthSnapshot
  └─ rendered on /operator page (US1)

ActiveExecution
  └─ rendered in active executions table (US2)
  └─ row click → navigate to /operator/executions/{executionId}

OperatorAlert
  └─ stored in AlertFeedState (US3)
  └─ pushed from WebSocket 'alerts' channel

AttentionEvent
  └─ stored in AttentionFeedState (US6)
  └─ initial load from GET /interactions/attention
  └─ updates from WebSocket 'attention' channel (auto-subscribed)
  └─ click → navigate to targetId context

QueueLagSnapshot + ReasoningBudgetUtilization
  └─ rendered in queue/budget section (US5)

ReasoningTrace + ContextQualityView + BudgetStatus
  └─ rendered on /operator/executions/[executionId] page (US4)
  └─ belong to an execution
```

---

## Zustand Stores

```typescript
// AlertFeedStore — lib/stores/use-alert-feed-store.ts
// Ring buffer for real-time alerts, NOT persisted
interface AlertFeedStore extends AlertFeedState {}

// AttentionFeedStore — lib/stores/use-attention-feed-store.ts
// Current user's attention requests, NOT persisted
interface AttentionFeedStore extends AttentionFeedState {}
```
