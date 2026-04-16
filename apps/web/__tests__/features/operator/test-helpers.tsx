import type {
  ActiveExecution,
  AttentionEvent,
  BudgetStatus,
  ContextQualityView,
  OperatorAlert,
  OperatorMetrics,
  QueueTopicLag,
  ReasoningBudgetUtilization,
  ReasoningTrace,
  ServiceHealthSnapshot,
} from "@/lib/types/operator-dashboard";
import { useAlertFeedStore } from "@/lib/stores/use-alert-feed-store";
import { useAttentionFeedStore } from "@/lib/stores/use-attention-feed-store";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export const sampleOperatorMetrics: OperatorMetrics = {
  activeExecutions: 12,
  queuedSteps: 41,
  pendingApprovals: 3,
  recentFailures: 2,
  avgLatencyMs: 842,
  fleetHealthScore: 91,
  computedAt: "2026-04-16T11:59:45.000Z",
};

export const sampleServiceHealthSnapshot: ServiceHealthSnapshot = {
  overallStatus: "degraded",
  uptimeSeconds: 86400,
  checkedAt: "2026-04-16T12:00:00.000Z",
  services: [
    {
      serviceKey: "postgresql",
      displayName: "PostgreSQL",
      serviceType: "data_store",
      status: "healthy",
      latencyMs: 14,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "redis",
      displayName: "Redis",
      serviceType: "data_store",
      status: "healthy",
      latencyMs: 4,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "kafka",
      displayName: "Kafka",
      serviceType: "data_store",
      status: "degraded",
      latencyMs: 88,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "qdrant",
      displayName: "Qdrant",
      serviceType: "data_store",
      status: "healthy",
      latencyMs: 22,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "neo4j",
      displayName: "Neo4j",
      serviceType: "data_store",
      status: "unhealthy",
      latencyMs: 140,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "clickhouse",
      displayName: "ClickHouse",
      serviceType: "data_store",
      status: "healthy",
      latencyMs: 36,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "opensearch",
      displayName: "OpenSearch",
      serviceType: "data_store",
      status: "unknown",
      latencyMs: null,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "minio",
      displayName: "MinIO",
      serviceType: "data_store",
      status: "healthy",
      latencyMs: 19,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "runtime_controller",
      displayName: "Runtime Controller",
      serviceType: "satellite",
      status: "healthy",
      latencyMs: 29,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "reasoning_engine",
      displayName: "Reasoning Engine",
      serviceType: "satellite",
      status: "degraded",
      latencyMs: 130,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "sandbox_manager",
      displayName: "Sandbox Manager",
      serviceType: "satellite",
      status: "healthy",
      latencyMs: 31,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
    {
      serviceKey: "simulation_controller",
      displayName: "Simulation Controller",
      serviceType: "satellite",
      status: "healthy",
      latencyMs: 27,
      checkedAt: "2026-04-16T12:00:00.000Z",
    },
  ],
};

export const sampleActiveExecutions: ActiveExecution[] = [
  {
    id: "exec-run-0001",
    workflowName: "Fraud triage",
    agentFqn: "risk:triage-lead",
    currentStepLabel: "Assess evidence",
    status: "running",
    startedAt: "2026-04-16T11:58:00.000Z",
    elapsedMs: 120000,
  },
  {
    id: "exec-pause-0002",
    workflowName: "Identity review",
    agentFqn: "risk:identity-analyst",
    currentStepLabel: null,
    status: "paused",
    startedAt: "2026-04-16T11:55:00.000Z",
    elapsedMs: 300000,
  },
  {
    id: "exec-approval-0003",
    workflowName: "Chargeback recovery",
    agentFqn: "risk:chargeback-bot",
    currentStepLabel: "Await legal review",
    status: "waiting_for_approval",
    startedAt: "2026-04-16T11:59:00.000Z",
    elapsedMs: 60000,
  },
];

export const sampleAlerts: OperatorAlert[] = [
  {
    id: "alert-1",
    severity: "warning",
    sourceService: "kafka",
    timestamp: "2026-04-16T11:58:00.000Z",
    message: "Consumer lag rising on orchestration topic.",
    description: "Lag crossed the warning threshold for orchestration.primary.",
    suggestedAction: "Inspect consumers and rebalance partitions.",
  },
  {
    id: "alert-2",
    severity: "error",
    sourceService: "neo4j",
    timestamp: "2026-04-16T11:59:00.000Z",
    message: "Query latency breached SLO.",
    description: "Graph traversals exceeded 2 seconds for fraud case lookups.",
    suggestedAction: "Throttle heavy traversals and inspect index health.",
  },
  {
    id: "alert-3",
    severity: "critical",
    sourceService: "runtime-controller",
    timestamp: "2026-04-16T12:00:00.000Z",
    message: "Execution admission paused.",
    description: "The runtime controller rejected new workloads after repeated faults.",
    suggestedAction: "Review the most recent deployment and drain the queue.",
  },
];

export const sampleAttentionEvents: AttentionEvent[] = [
  {
    id: "attention-1",
    sourceAgentFqn: "risk:fraud-monitor",
    urgency: "critical",
    contextSummary: "Manual adjudication required for high-value fraud cluster.",
    targetType: "execution",
    targetId: "exec-run-0001",
    status: "pending",
    createdAt: "2026-04-16T12:00:00.000Z",
  },
  {
    id: "attention-2",
    sourceAgentFqn: "risk:conversation-bot",
    urgency: "medium",
    contextSummary: "Customer conversation needs escalation to a human reviewer.",
    targetType: "interaction",
    targetId: "conv-22",
    status: "pending",
    createdAt: "2026-04-16T11:59:00.000Z",
  },
  {
    id: "attention-3",
    sourceAgentFqn: "risk:goal-planner",
    urgency: "low",
    contextSummary: "Goal dependency graph changed and needs confirmation.",
    targetType: "goal",
    targetId: "goal-7",
    status: "pending",
    createdAt: "2026-04-16T11:58:00.000Z",
  },
  {
    id: "attention-4",
    sourceAgentFqn: "risk:history-bot",
    urgency: "high",
    contextSummary: "Previously acknowledged follow-up event.",
    targetType: "execution",
    targetId: "exec-history-004",
    status: "acknowledged",
    createdAt: "2026-04-16T11:57:00.000Z",
  },
];

export const sampleQueueLagTopics: QueueTopicLag[] = [
  {
    topic: "orchestration.primary",
    lag: 14872,
    warning: true,
  },
  {
    topic: "attention.requests",
    lag: 220,
    warning: false,
  },
  {
    topic: "reasoning.telemetry",
    lag: 840,
    warning: false,
  },
];

export const sampleReasoningBudgetUtilization: ReasoningBudgetUtilization = {
  totalCapacityTokens: 1000000,
  usedTokens: 950000,
  utilizationPct: 95,
  activeExecutionCount: 12,
  criticalPressure: true,
  computedAt: "2026-04-16T12:00:00.000Z",
};

export const sampleReasoningTrace: ReasoningTrace = {
  executionId: "exec-run-0001",
  totalTokens: 3820,
  totalDurationMs: 1820,
  totalCorrectionIterations: 2,
  steps: [
    {
      id: "step-1",
      mode: "reflection",
      inputSummary: "Review the latest fraud signals and supporting evidence.",
      outputSummary: "Initial adjudication identified a high-confidence fraud cluster.",
      fullOutputRef:
        "Full output trace for step 1: confidence 0.92 with a two-hop entity match.",
      tokenCount: 1400,
      durationMs: 620,
      selfCorrections: [
        {
          iterationIndex: 1,
          originalOutputSummary: "Original output over-weighted a stale device fingerprint.",
          correctionReason: "Device graph data was older than the freshness threshold.",
          correctedOutputSummary: "Recomputed score after removing stale device evidence.",
          tokenDelta: 84,
        },
        {
          iterationIndex: 2,
          originalOutputSummary: "Manual review recommendation lacked recent case context.",
          correctionReason: "Recent chargeback evidence was absent from the first pass.",
          correctedOutputSummary: "Added recent chargeback references to the recommendation.",
          tokenDelta: 55,
        },
      ],
    },
    {
      id: "step-2",
      mode: "react",
      inputSummary: "Cross-check the recommendation against policy constraints.",
      outputSummary: "Policy alignment confirmed and escalation prepared.",
      fullOutputRef: null,
      tokenCount: 1120,
      durationMs: 540,
      selfCorrections: [],
    },
  ],
};

export const sampleBudgetStatus: BudgetStatus = {
  executionId: "exec-run-0001",
  isActive: false,
  computedAt: "2026-04-16T12:00:00.000Z",
  dimensions: [
    {
      dimension: "tokens",
      label: "Tokens",
      used: 4200,
      limit: 10000,
      unit: "tokens",
      utilizationPct: 42,
      nearLimit: false,
    },
    {
      dimension: "tool_invocations",
      label: "Tool invocations",
      used: 14,
      limit: 20,
      unit: "calls",
      utilizationPct: 70,
      nearLimit: true,
    },
    {
      dimension: "memory_writes",
      label: "Memory writes",
      used: 19,
      limit: 20,
      unit: "writes",
      utilizationPct: 95,
      nearLimit: true,
    },
    {
      dimension: "elapsed_time",
      label: "Elapsed time",
      used: 1820,
      limit: 5000,
      unit: "ms",
      utilizationPct: 36.4,
      nearLimit: false,
    },
  ],
};

export const sampleContextQuality: ContextQualityView = {
  overallQualityScore: 84,
  assembledAt: "2026-04-16T12:00:00.000Z",
  sources: [
    {
      id: "source-1",
      sourceType: "memory",
      qualityScore: 92,
      contributionWeight: 0.45,
      provenanceRef: "https://musematic.dev/memory/123",
    },
    {
      id: "source-2",
      sourceType: "knowledge_graph",
      qualityScore: 78,
      contributionWeight: 0.35,
      provenanceRef: "https://musematic.dev/kg/456",
    },
    {
      id: "source-3",
      sourceType: "evaluation",
      qualityScore: 70,
      contributionWeight: 0.2,
      provenanceRef: null,
    },
  ],
};

export function seedOperatorStores() {
  useAuthStore.setState({
    accessToken: "access-token",
    isAuthenticated: true,
    refreshToken: "refresh-token",
    user: {
      id: "user-1",
      email: "operator@musematic.dev",
      displayName: "Operator",
      avatarUrl: null,
      mfaEnrolled: true,
      roles: ["platform_admin", "workspace_admin"],
      workspaceId: "workspace-1",
    },
  } as never);

  useWorkspaceStore.setState({
    currentWorkspace: {
      id: "workspace-1",
      name: "Risk Ops",
      slug: "risk-ops",
      description: "Risk operations workspace",
      memberCount: 8,
      createdAt: "2026-04-10T09:00:00.000Z",
    },
    isLoading: false,
    sidebarCollapsed: false,
    workspaceList: [],
  } as never);

  useAlertFeedStore.setState({
    alerts: [],
    isConnected: true,
    severityFilter: "all",
  });

  useAttentionFeedStore.setState({
    events: [],
  });
}
