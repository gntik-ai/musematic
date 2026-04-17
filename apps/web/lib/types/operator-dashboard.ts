"use client";

export type ServiceStatus = "healthy" | "degraded" | "unhealthy" | "unknown";
export type ServiceType = "data_store" | "satellite";
export type ActiveExecutionStatus =
  | "running"
  | "paused"
  | "waiting_for_approval"
  | "compensating";
export type AlertSeverity = "info" | "warning" | "error" | "critical";
export type AttentionUrgency = "low" | "medium" | "high" | "critical";
export type AttentionTargetType = "execution" | "interaction" | "goal";
export type ReasoningMode =
  | "chain_of_thought"
  | "tree_of_thought"
  | "react"
  | "reflection"
  | "direct"
  | "code_as_reasoning";
export type BudgetDimension =
  | "tokens"
  | "tool_invocations"
  | "memory_writes"
  | "elapsed_time";
export type ContextSourceType =
  | "memory"
  | "knowledge_graph"
  | "evaluation"
  | "workspace_context"
  | "system_prompt";
export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "disconnected"
  | "reconnecting";

export interface OperatorMetrics {
  activeExecutions: number;
  queuedSteps: number;
  pendingApprovals: number;
  recentFailures: number;
  avgLatencyMs: number;
  fleetHealthScore: number;
  computedAt: string;
}

export interface ServiceHealthEntry {
  serviceKey: string;
  displayName: string;
  serviceType: ServiceType;
  status: ServiceStatus;
  latencyMs: number | null;
  checkedAt?: string | undefined;
}

export interface ServiceHealthSnapshot {
  overallStatus: ServiceStatus;
  uptimeSeconds: number;
  services: ServiceHealthEntry[];
  checkedAt: string;
}

export const SERVICE_DISPLAY_NAMES: Record<
  string,
  { label: string; type: ServiceType }
> = {
  postgresql: { label: "PostgreSQL", type: "data_store" },
  redis: { label: "Redis", type: "data_store" },
  kafka: { label: "Kafka", type: "data_store" },
  qdrant: { label: "Qdrant", type: "data_store" },
  neo4j: { label: "Neo4j", type: "data_store" },
  clickhouse: { label: "ClickHouse", type: "data_store" },
  opensearch: { label: "OpenSearch", type: "data_store" },
  minio: { label: "MinIO", type: "data_store" },
  runtime_controller: {
    label: "Runtime Controller",
    type: "satellite",
  },
  reasoning_engine: { label: "Reasoning Engine", type: "satellite" },
  sandbox_manager: { label: "Sandbox Manager", type: "satellite" },
  simulation_controller: {
    label: "Simulation Controller",
    type: "satellite",
  },
};

export const SERVICE_GROUP_ORDER: Record<ServiceType, string[]> = {
  data_store: [
    "postgresql",
    "redis",
    "kafka",
    "qdrant",
    "neo4j",
    "clickhouse",
    "opensearch",
    "minio",
  ],
  satellite: [
    "runtime_controller",
    "reasoning_engine",
    "sandbox_manager",
    "simulation_controller",
  ],
};

export interface ActiveExecution {
  id: string;
  workflowName: string;
  agentFqn: string;
  currentStepLabel: string | null;
  status: ActiveExecutionStatus;
  startedAt: string;
  elapsedMs: number;
}

export interface ActiveExecutionsFilters {
  status: ActiveExecutionStatus | "all";
  sortBy: "started_at" | "elapsed";
}

export const DEFAULT_ACTIVE_EXECUTIONS_FILTERS: ActiveExecutionsFilters = {
  status: "all",
  sortBy: "started_at",
};

export interface OperatorAlert {
  id: string;
  severity: AlertSeverity;
  sourceService: string;
  timestamp: string;
  message: string;
  description: string | null;
  suggestedAction: string | null;
}

export interface AlertFeedState {
  alerts: OperatorAlert[];
  isConnected: boolean;
  severityFilter: AlertSeverity | "all";
  addAlert: (alert: OperatorAlert) => void;
  setConnected: (connected: boolean) => void;
  setSeverityFilter: (filter: AlertSeverity | "all") => void;
  clearAlerts: () => void;
}

export interface AttentionEvent {
  id: string;
  sourceAgentFqn: string;
  urgency: AttentionUrgency;
  contextSummary: string;
  targetType: AttentionTargetType | null;
  targetId: string | null;
  status: "pending" | "acknowledged" | "resolved" | "dismissed";
  createdAt: string;
}

export interface AttentionFeedState {
  events: AttentionEvent[];
  setEvents: (events: AttentionEvent[]) => void;
  addEvent: (event: AttentionEvent) => void;
  acknowledgeEvent: (id: string) => void;
}

export interface QueueTopicLag {
  topic: string;
  lag: number;
  warning: boolean;
}

export interface QueueLagSnapshot {
  topics: QueueTopicLag[];
  computedAt: string;
}

export interface ReasoningBudgetUtilization {
  totalCapacityTokens: number;
  usedTokens: number;
  utilizationPct: number;
  activeExecutionCount: number;
  criticalPressure: boolean;
  computedAt: string;
}

export interface SelfCorrectionIteration {
  iterationIndex: number;
  originalOutputSummary: string;
  correctionReason: string;
  correctedOutputSummary: string;
  tokenDelta: number;
}

export interface ReasoningTraceStep {
  id: string;
  mode: ReasoningMode;
  inputSummary: string;
  outputSummary: string;
  fullOutputRef: string | null;
  tokenCount: number;
  durationMs: number;
  selfCorrections: SelfCorrectionIteration[];
}

export interface ReasoningTrace {
  executionId: string;
  totalTokens: number;
  totalDurationMs: number;
  totalCorrectionIterations: number;
  steps: ReasoningTraceStep[];
}

export interface ContextSource {
  id: string;
  sourceType: ContextSourceType;
  qualityScore: number;
  contributionWeight: number;
  provenanceRef: string | null;
}

export interface ContextQualityView {
  overallQualityScore: number;
  sources: ContextSource[];
  assembledAt: string;
}

export interface BudgetDimensionUsage {
  dimension: BudgetDimension;
  label: string;
  used: number;
  limit: number;
  unit: string;
  utilizationPct: number;
  nearLimit: boolean;
}

export interface BudgetStatus {
  executionId: string;
  isActive: boolean;
  dimensions: BudgetDimensionUsage[];
  computedAt: string;
}

export const ACTIVE_EXECUTION_STATUS_LABELS: Record<
  ActiveExecutionStatus,
  string
> = {
  running: "Running",
  paused: "Paused",
  waiting_for_approval: "Waiting approval",
  compensating: "Compensating",
};

export const ALERT_SEVERITY_LABELS: Record<AlertSeverity, string> = {
  info: "Info",
  warning: "Warning",
  error: "Error",
  critical: "Critical",
};

export const ATTENTION_URGENCY_LABELS: Record<AttentionUrgency, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export const REASONING_MODE_LABELS: Record<ReasoningMode, string> = {
  chain_of_thought: "Chain of thought",
  tree_of_thought: "Tree of thought",
  react: "ReAct",
  reflection: "Reflection",
  direct: "Direct",
  code_as_reasoning: "Code as reasoning",
};

export const BUDGET_DIMENSION_LABELS: Record<BudgetDimension, string> = {
  tokens: "Tokens",
  tool_invocations: "Tool invocations",
  memory_writes: "Memory writes",
  elapsed_time: "Elapsed time",
};

export const CONTEXT_SOURCE_LABELS: Record<ContextSourceType, string> = {
  memory: "Memory",
  knowledge_graph: "Knowledge graph",
  evaluation: "Evaluation",
  workspace_context: "Workspace context",
  system_prompt: "System prompt",
};

export function getAttentionTargetHref(event: AttentionEvent): string | null {
  if (!event.targetType || !event.targetId) {
    return null;
  }

  if (event.targetType === "execution") {
    return `/operator/executions/${encodeURIComponent(event.targetId)}`;
  }
  if (event.targetType === "interaction") {
    return `/conversations/${encodeURIComponent(event.targetId)}`;
  }

  return `/workspaces/goals/${encodeURIComponent(event.targetId)}`;
}
