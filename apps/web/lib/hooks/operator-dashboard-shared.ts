"use client";

import { createApiClient } from "@/lib/api";
import {
  ACTIVE_EXECUTION_STATUS_LABELS,
  BUDGET_DIMENSION_LABELS,
  CONTEXT_SOURCE_LABELS,
  SERVICE_DISPLAY_NAMES,
  type ActiveExecution,
  type ActiveExecutionStatus,
  type AlertSeverity,
  type AttentionEvent,
  type AttentionTargetType,
  type AttentionUrgency,
  type BudgetDimension,
  type BudgetDimensionUsage,
  type BudgetStatus,
  type ContextQualityView,
  type ContextSource,
  type ContextSourceType,
  type OperatorAlert,
  type OperatorMetrics,
  type QueueLagSnapshot,
  type QueueTopicLag,
  type ReasoningBudgetUtilization,
  type ReasoningMode,
  type ReasoningTrace,
  type ReasoningTraceStep,
  type SelfCorrectionIteration,
  type ServiceHealthEntry,
  type ServiceHealthSnapshot,
  type ServiceStatus,
  type ServiceType,
} from "@/lib/types/operator-dashboard";
import {
  normalizeExecution,
  type ExecutionResponse,
} from "@/types/execution";

export const operatorDashboardApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export const operatorDashboardQueryKeys = {
  metrics: ["operatorDashboard", "metrics"] as const,
  serviceHealth: ["operatorDashboard", "serviceHealth"] as const,
  activeExecutions: (
    workspaceId: string | null | undefined,
    filters: unknown,
  ) => ["operatorDashboard", "activeExecutions", workspaceId ?? "none", filters] as const,
  attentionInit: (userId: string | null | undefined) =>
    ["operatorDashboard", "attentionInit", userId ?? "none"] as const,
  queueLag: ["operatorDashboard", "queueLag"] as const,
  reasoningBudget: ["operatorDashboard", "reasoningBudget"] as const,
  executionDetail: (executionId: string | null | undefined) =>
    ["operatorDashboard", "executionDetail", executionId ?? "none"] as const,
  reasoningTrace: (executionId: string | null | undefined) =>
    ["operatorDashboard", "reasoningTrace", executionId ?? "none"] as const,
  budgetStatus: (executionId: string | null | undefined) =>
    ["operatorDashboard", "budgetStatus", executionId ?? "none"] as const,
  contextQuality: (executionId: string | null | undefined) =>
    ["operatorDashboard", "contextQuality", executionId ?? "none"] as const,
};

export function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

export function asNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))
      ? Number(value)
      : fallback;
}

export function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function parseServiceStatus(value: unknown): ServiceStatus {
  return value === "healthy" ||
    value === "degraded" ||
    value === "unhealthy" ||
    value === "unknown"
    ? value
    : "unknown";
}

function parseActiveExecutionStatus(value: unknown): ActiveExecutionStatus {
  return value === "running" ||
    value === "paused" ||
    value === "waiting_for_approval" ||
    value === "compensating"
    ? value
    : "running";
}

function parseAlertSeverity(value: unknown): AlertSeverity {
  return value === "info" ||
    value === "warning" ||
    value === "error" ||
    value === "critical"
    ? value
    : "info";
}

function parseAttentionUrgency(value: unknown): AttentionUrgency {
  return value === "low" ||
    value === "medium" ||
    value === "high" ||
    value === "critical"
    ? value
    : "medium";
}

function parseReasoningMode(value: unknown): ReasoningMode {
  return value === "chain_of_thought" ||
    value === "tree_of_thought" ||
    value === "react" ||
    value === "reflection" ||
    value === "direct" ||
    value === "code_as_reasoning"
    ? value
    : "direct";
}

function parseBudgetDimension(value: unknown): BudgetDimension {
  return value === "tokens" ||
    value === "tool_invocations" ||
    value === "memory_writes" ||
    value === "elapsed_time"
    ? value
    : "tokens";
}

function parseContextSourceType(value: unknown): ContextSourceType {
  return value === "memory" ||
    value === "knowledge_graph" ||
    value === "evaluation" ||
    value === "workspace_context" ||
    value === "system_prompt"
    ? value
    : "memory";
}

function parseAttentionTargetType(value: unknown): AttentionTargetType | null {
  return value === "execution" ||
    value === "interaction" ||
    value === "goal"
    ? value
    : null;
}

function deriveAttentionTarget(raw: Record<string, unknown>): {
  targetType: AttentionTargetType | null;
  targetId: string | null;
} {
  const explicitType = parseAttentionTargetType(
    raw.targetType ?? raw.target_type,
  );
  const explicitId = asNullableString(raw.targetId ?? raw.target_id);
  if (explicitType && explicitId) {
    return { targetType: explicitType, targetId: explicitId };
  }

  const executionId = asNullableString(
    raw.relatedExecutionId ?? raw.related_execution_id,
  );
  if (executionId) {
    return { targetType: "execution", targetId: executionId };
  }

  const interactionId = asNullableString(
    raw.relatedInteractionId ?? raw.related_interaction_id,
  );
  if (interactionId) {
    return { targetType: "interaction", targetId: interactionId };
  }

  const goalId = asNullableString(raw.relatedGoalId ?? raw.related_goal_id);
  if (goalId) {
    return { targetType: "goal", targetId: goalId };
  }

  return { targetType: null, targetId: null };
}

export function getElapsedMs(startedAt: string): number {
  const started = new Date(startedAt).getTime();
  if (Number.isNaN(started)) {
    return 0;
  }

  return Math.max(0, Date.now() - started);
}

export function normalizeOperatorMetrics(raw: unknown): OperatorMetrics {
  const value = asRecord(raw);

  return {
    activeExecutions: asNumber(
      value.activeExecutions ?? value.active_executions,
    ),
    queuedSteps: asNumber(value.queuedSteps ?? value.queued_steps),
    pendingApprovals: asNumber(
      value.pendingApprovals ?? value.pending_approvals,
    ),
    recentFailures: asNumber(value.recentFailures ?? value.recent_failures),
    avgLatencyMs: asNumber(value.avgLatencyMs ?? value.avg_latency_ms),
    fleetHealthScore: asNumber(
      value.fleetHealthScore ?? value.fleet_health_score,
    ),
    computedAt: asString(
      value.computedAt ?? value.computed_at,
      new Date(0).toISOString(),
    ),
  };
}

function createUnknownServiceEntry(
  serviceKey: string,
  checkedAt: string,
): ServiceHealthEntry {
  const metadata = SERVICE_DISPLAY_NAMES[serviceKey];

  return {
    serviceKey,
    displayName: metadata?.label ?? serviceKey,
    serviceType: metadata?.type ?? "satellite",
    status: "unknown",
    latencyMs: null,
    checkedAt,
  };
}

export function normalizeServiceHealthSnapshot(raw: unknown): ServiceHealthSnapshot {
  const value = asRecord(raw);
  const dependencies = asRecord(value.dependencies);
  const checkedAt = new Date().toISOString();
  const services: ServiceHealthEntry[] = Object.keys(SERVICE_DISPLAY_NAMES).map(
    (serviceKey) => {
      const metadata = SERVICE_DISPLAY_NAMES[serviceKey] ?? {
        label: serviceKey,
        type: "satellite" as ServiceType,
      };
      const entry = asRecord(dependencies[serviceKey]);
      if (Object.keys(entry).length === 0) {
        return createUnknownServiceEntry(serviceKey, checkedAt);
      }

      return {
        serviceKey,
        displayName: metadata.label,
        serviceType: metadata.type,
        status: parseServiceStatus(entry.status),
        latencyMs:
          entry.latency_ms === null || entry.latencyMs === null
            ? null
            : asNumber(entry.latency_ms ?? entry.latencyMs),
        checkedAt,
      };
    },
  );

  return {
    overallStatus: parseServiceStatus(value.status),
    uptimeSeconds: asNumber(value.uptime_seconds ?? value.uptimeSeconds),
    services,
    checkedAt,
  };
}

function resolveWorkflowName(raw: Record<string, unknown>): string {
  return asString(
    raw.workflowName ??
      raw.workflow_name ??
      raw.workflowDefinitionName ??
      raw.workflow_definition_name ??
      raw.workflow_definition_id ??
      raw.workflowId ??
      raw.workflow_id,
    "Unknown workflow",
  );
}

function resolveAgentFqn(raw: Record<string, unknown>): string {
  const correlationContext = asRecord(
    raw.correlation_context ?? raw.correlationContext,
  );

  return asString(
    raw.agentFqn ??
      raw.agent_fqn ??
      correlationContext.agent_fqn ??
      correlationContext.agentFqn,
    "unknown:agent",
  );
}

export function normalizeActiveExecution(raw: unknown): ActiveExecution {
  const value = asRecord(raw);
  const executionResponse = value as Partial<ExecutionResponse>;
  const normalizedExecution =
    executionResponse.id &&
    executionResponse.workflow_id &&
    executionResponse.workflow_version_id &&
    executionResponse.workflow_version_number !== undefined &&
    executionResponse.triggered_by &&
    executionResponse.correlation_context &&
    executionResponse.started_at &&
    executionResponse.status
      ? normalizeExecution(executionResponse as ExecutionResponse)
      : null;
  const startedAt = asString(
    value.startedAt ??
      value.started_at ??
      value.createdAt ??
      value.created_at ??
      normalizedExecution?.startedAt,
    new Date(0).toISOString(),
  );

  return {
    id: asString(value.id, normalizedExecution?.id ?? ""),
    workflowName: resolveWorkflowName(value),
    agentFqn: resolveAgentFqn(value),
    currentStepLabel: asNullableString(
      value.currentStepLabel ?? value.current_step_label,
    ),
    status: parseActiveExecutionStatus(
      value.status ?? normalizedExecution?.status,
    ),
    startedAt,
    elapsedMs: getElapsedMs(startedAt),
  };
}

export function normalizeOperatorAlert(
  raw: unknown,
  fallbackTimestamp?: string,
): OperatorAlert {
  const value = asRecord(raw);

  return {
    id: asString(
      value.id,
      `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    ),
    severity: parseAlertSeverity(value.severity),
    sourceService: asString(
      value.sourceService ?? value.source_service,
      "unknown-service",
    ),
    timestamp: asString(
      value.timestamp ?? value.created_at ?? value.createdAt,
      fallbackTimestamp ?? new Date().toISOString(),
    ),
    message: asString(value.message, "Alert received"),
    description: asNullableString(value.description),
    suggestedAction: asNullableString(
      value.suggestedAction ?? value.suggested_action,
    ),
  };
}

export function normalizeAttentionEvent(raw: unknown): AttentionEvent {
  const value = asRecord(raw);
  const target = deriveAttentionTarget(value);

  return {
    id: asString(value.id),
    sourceAgentFqn: asString(
      value.sourceAgentFqn ?? value.source_agent_fqn,
      "unknown:agent",
    ),
    urgency: parseAttentionUrgency(value.urgency),
    contextSummary: asString(
      value.contextSummary ?? value.context_summary,
      "Attention requested",
    ),
    targetType: target.targetType,
    targetId: target.targetId,
    status:
      value.status === "pending" ||
      value.status === "acknowledged" ||
      value.status === "resolved" ||
      value.status === "dismissed"
        ? value.status
        : "pending",
    createdAt: asString(
      value.createdAt ?? value.created_at,
      new Date(0).toISOString(),
    ),
  };
}

export function normalizeQueueLagTopic(raw: unknown): QueueTopicLag {
  const value = asRecord(raw);

  return {
    topic: asString(value.topic, "unknown-topic"),
    lag: asNumber(value.lag),
    warning: asBoolean(value.warning),
  };
}

export function normalizeQueueLagSnapshot(raw: unknown): QueueLagSnapshot {
  const value = asRecord(raw);
  const topics = Array.isArray(value.topics)
    ? value.topics.map(normalizeQueueLagTopic)
    : [];

  return {
    topics,
    computedAt: asString(
      value.computedAt ?? value.computed_at,
      new Date(0).toISOString(),
    ),
  };
}

export function normalizeReasoningBudgetUtilization(
  raw: unknown,
): ReasoningBudgetUtilization {
  const value = asRecord(raw);

  return {
    totalCapacityTokens: asNumber(
      value.totalCapacityTokens ?? value.total_capacity_tokens,
    ),
    usedTokens: asNumber(value.usedTokens ?? value.used_tokens),
    utilizationPct: asNumber(
      value.utilizationPct ?? value.utilization_pct,
    ),
    activeExecutionCount: asNumber(
      value.activeExecutionCount ?? value.active_execution_count,
    ),
    criticalPressure: asBoolean(
      value.criticalPressure ?? value.critical_pressure,
    ),
    computedAt: asString(
      value.computedAt ?? value.computed_at,
      new Date(0).toISOString(),
    ),
  };
}

function normalizeSelfCorrectionIteration(raw: unknown): SelfCorrectionIteration {
  const value = asRecord(raw);

  return {
    iterationIndex: asNumber(
      value.iterationIndex ?? value.iteration_index,
    ),
    originalOutputSummary: asString(
      value.originalOutputSummary ?? value.original_output_summary,
    ),
    correctionReason: asString(
      value.correctionReason ?? value.correction_reason,
    ),
    correctedOutputSummary: asString(
      value.correctedOutputSummary ?? value.corrected_output_summary,
    ),
    tokenDelta: asNumber(value.tokenDelta ?? value.token_delta),
  };
}

function normalizeReasoningTraceStep(raw: unknown, index: number): ReasoningTraceStep {
  const value = asRecord(raw);
  const selfCorrectionsRaw = Array.isArray(
    value.selfCorrections ?? value.self_corrections,
  )
    ? ((value.selfCorrections ?? value.self_corrections) as unknown[])
    : [];

  return {
    id: asString(value.id, `step-${index + 1}`),
    mode: parseReasoningMode(value.mode),
    inputSummary: asString(
      value.inputSummary ?? value.input_summary,
      "No input summary available.",
    ),
    outputSummary: asString(
      value.outputSummary ?? value.output_summary,
      "No output summary available.",
    ),
    fullOutputRef: asNullableString(
      value.fullOutputRef ?? value.full_output_ref,
    ),
    tokenCount: asNumber(value.tokenCount ?? value.token_count),
    durationMs: asNumber(value.durationMs ?? value.duration_ms),
    selfCorrections: selfCorrectionsRaw.map(normalizeSelfCorrectionIteration),
  };
}

export function normalizeReasoningTrace(raw: unknown): ReasoningTrace {
  const value = asRecord(raw);
  const stepsRaw = Array.isArray(value.steps) ? value.steps : [];
  const steps = stepsRaw.map(normalizeReasoningTraceStep);
  const totalCorrectionIterations = steps.reduce(
    (sum, step) => sum + step.selfCorrections.length,
    0,
  );

  return {
    executionId: asString(value.executionId ?? value.execution_id),
    totalTokens: asNumber(value.totalTokens ?? value.total_tokens),
    totalDurationMs: asNumber(value.totalDurationMs ?? value.total_duration_ms),
    totalCorrectionIterations,
    steps,
  };
}

function normalizeContextSource(raw: unknown, index: number): ContextSource {
  const value = asRecord(raw);

  return {
    id: asString(value.id, `source-${index + 1}`),
    sourceType: parseContextSourceType(
      value.sourceType ?? value.source_type,
    ),
    qualityScore: asNumber(value.qualityScore ?? value.quality_score),
    contributionWeight: asNumber(
      value.contributionWeight ?? value.contribution_weight,
    ),
    provenanceRef: asNullableString(
      value.provenanceRef ?? value.provenance_ref,
    ),
  };
}

export function normalizeContextQuality(raw: unknown): ContextQualityView {
  const value = asRecord(raw);
  const sourcesRaw = Array.isArray(value.sources) ? value.sources : [];

  return {
    overallQualityScore: asNumber(
      value.overallQualityScore ?? value.overall_quality_score,
    ),
    sources: sourcesRaw.map(normalizeContextSource),
    assembledAt: asString(
      value.assembledAt ?? value.assembled_at,
      new Date(0).toISOString(),
    ),
  };
}

function normalizeBudgetDimensionUsage(raw: unknown): BudgetDimensionUsage {
  const value = asRecord(raw);
  const dimension = parseBudgetDimension(value.dimension);

  return {
    dimension,
    label: asString(
      value.label,
      BUDGET_DIMENSION_LABELS[dimension],
    ),
    used: asNumber(value.used),
    limit: asNumber(value.limit),
    unit: asString(value.unit, dimension === "elapsed_time" ? "ms" : ""),
    utilizationPct: asNumber(
      value.utilizationPct ?? value.utilization_pct,
    ),
    nearLimit: asBoolean(value.nearLimit ?? value.near_limit),
  };
}

export function normalizeBudgetStatus(raw: unknown): BudgetStatus {
  const value = asRecord(raw);
  const dimensionsRaw = Array.isArray(value.dimensions) ? value.dimensions : [];

  return {
    executionId: asString(value.executionId ?? value.execution_id),
    isActive: asBoolean(value.isActive ?? value.is_active, true),
    dimensions: dimensionsRaw.map(normalizeBudgetDimensionUsage),
    computedAt: asString(
      value.computedAt ?? value.computed_at,
      new Date(0).toISOString(),
    ),
  };
}

export const operatorDisplayLabels = {
  activeExecution: ACTIVE_EXECUTION_STATUS_LABELS,
  contextSource: CONTEXT_SOURCE_LABELS,
};
