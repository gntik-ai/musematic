import type { CursorPaginatedResponse } from "@/types/api";

export const EXECUTION_STATUSES = [
  "queued",
  "running",
  "paused",
  "waiting_for_approval",
  "completed",
  "failed",
  "canceled",
  "compensating",
] as const;
export const STEP_STATUSES = [
  "pending",
  "running",
  "completed",
  "failed",
  "skipped",
  "waiting_for_approval",
  "canceled",
] as const;
export const EXECUTION_EVENT_TYPES = [
  "EXECUTION_CREATED",
  "EXECUTION_STARTED",
  "EXECUTION_PAUSED",
  "EXECUTION_RESUMED",
  "EXECUTION_COMPLETED",
  "EXECUTION_FAILED",
  "EXECUTION_CANCELED",
  "STEP_DISPATCHED",
  "STEP_RUNTIME_STARTED",
  "STEP_COMPLETED",
  "STEP_FAILED",
  "STEP_SKIPPED",
  "STEP_RETRIED",
  "STEP_WAITING_FOR_APPROVAL",
  "STEP_APPROVED",
  "STEP_REJECTED",
  "HOT_CHANGED",
  "REASONING_TRACE_EMITTED",
  "SELF_CORRECTION_STARTED",
  "SELF_CORRECTION_ITERATION",
  "SELF_CORRECTION_CONVERGED",
  "SELF_CORRECTION_BUDGET_EXCEEDED",
  "BUDGET_THRESHOLD_80",
  "BUDGET_THRESHOLD_90",
  "BUDGET_THRESHOLD_100",
  "execution.status_changed",
  "step.state_changed",
  "event.appended",
  "budget.threshold",
  "correction.iteration",
  "approval.requested",
  "hot_change.applied",
] as const;

export type ExecutionStatus = (typeof EXECUTION_STATUSES)[number];
export type StepStatus = (typeof STEP_STATUSES)[number];
export type ExecutionEventType = (typeof EXECUTION_EVENT_TYPES)[number];

export interface CorrelationContext {
  workspaceId: string;
  executionId: string;
  workflowId: string;
  goalId?: string;
  conversationId?: string;
}

export interface Execution {
  id: string;
  workflowId: string;
  workflowVersionId: string;
  workflowVersionNumber: number;
  status: ExecutionStatus;
  triggeredBy: string;
  correlationContext: CorrelationContext;
  startedAt: string;
  completedAt: string | null;
  failureReason: string | null;
}

export interface StepError {
  code: string;
  message: string;
  details: Record<string, unknown> | null;
}

export interface StepResult {
  stepId: string;
  status: StepStatus;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  error: StepError | null;
  retryCount: number;
}

export interface ExecutionState {
  executionId: string;
  status: ExecutionStatus;
  completedStepIds: string[];
  activeStepIds: string[];
  pendingStepIds: string[];
  failedStepIds: string[];
  skippedStepIds: string[];
  waitingForApprovalStepIds: string[];
  stepResults: Record<string, StepResult>;
  lastEventSequence: number;
  updatedAt: string;
}

export interface ExecutionEvent {
  id: string;
  executionId: string;
  sequence: number;
  eventType: ExecutionEventType;
  stepId: string | null;
  agentFqn: string | null;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  estimatedCostUsd: number;
}

export interface StepDetail {
  stepId: string;
  executionId: string;
  status: StepStatus;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown> | null;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  contextQualityScore: number | null;
  error: StepError | null;
  tokenUsage: TokenUsage | null;
}

export interface ExecutionJournalPage {
  items: ExecutionEvent[];
  total: number;
  offset: number;
  limit: number;
  hasNext: boolean;
  nextOffset: number | null;
}

export interface ExecutionCostEntry {
  stepId: string;
  stepName: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  costUsd: number;
  percentageOfTotal: number;
}

export interface ExecutionCostSummary {
  executionId: string;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalTokens: number;
  totalCostUsd: number;
  stepBreakdown: ExecutionCostEntry[];
  lastUpdatedAt: string;
}

export interface ExecutionResponse {
  id: string;
  workflow_id: string;
  workflow_version_id: string;
  workflow_version_number: number;
  status: ExecutionStatus;
  triggered_by: string;
  correlation_context: {
    workspace_id: string;
    execution_id: string;
    workflow_id: string;
    goal_id?: string;
    conversation_id?: string;
  };
  started_at: string;
  completed_at: string | null;
  failure_reason: string | null;
}

export interface ExecutionListResponse {
  items: ExecutionResponse[];
  next_cursor: string | null;
  total?: number;
}

export interface StepErrorResponse {
  code: string;
  message: string;
  details: Record<string, unknown> | null;
}

export interface StepResultResponse {
  step_id: string;
  status: StepStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  error: StepErrorResponse | null;
  retry_count: number;
}

export interface ExecutionStateResponse {
  execution_id: string;
  status: ExecutionStatus;
  completed_step_ids: string[];
  active_step_ids: string[];
  pending_step_ids: string[];
  failed_step_ids: string[];
  skipped_step_ids: string[];
  waiting_for_approval_step_ids: string[];
  step_results: Record<string, StepResultResponse>;
  last_event_sequence: number;
  updated_at: string;
}

export interface ExecutionEventResponse {
  id: string;
  execution_id: string;
  sequence: number;
  event_type: ExecutionEventType;
  step_id: string | null;
  agent_fqn: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ExecutionJournalResponse {
  events: ExecutionEventResponse[];
  total: number;
}

export interface TokenUsageResponse {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

export interface StepDetailResponse {
  step_id: string;
  execution_id: string;
  status: StepStatus;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  context_quality_score: number | null;
  error: StepErrorResponse | null;
  token_usage: TokenUsageResponse | null;
}

export function normalizeStepError(
  response: StepErrorResponse | null,
): StepError | null {
  if (!response) {
    return null;
  }

  return {
    code: response.code,
    message: response.message,
    details: response.details,
  };
}

export function normalizeTokenUsage(
  response: TokenUsageResponse | null,
): TokenUsage | null {
  if (!response) {
    return null;
  }

  return {
    inputTokens: response.input_tokens,
    outputTokens: response.output_tokens,
    totalTokens: response.total_tokens,
    estimatedCostUsd: response.estimated_cost_usd,
  };
}

export function normalizeStepResult(response: StepResultResponse): StepResult {
  return {
    stepId: response.step_id,
    status: response.status,
    startedAt: response.started_at,
    completedAt: response.completed_at,
    durationMs: response.duration_ms,
    error: normalizeStepError(response.error),
    retryCount: response.retry_count,
  };
}

export function normalizeExecution(response: ExecutionResponse): Execution {
  return {
    id: response.id,
    workflowId: response.workflow_id,
    workflowVersionId: response.workflow_version_id,
    workflowVersionNumber: response.workflow_version_number,
    status: response.status,
    triggeredBy: response.triggered_by,
    correlationContext: {
      workspaceId: response.correlation_context.workspace_id,
      executionId: response.correlation_context.execution_id,
      workflowId: response.correlation_context.workflow_id,
      ...(response.correlation_context.goal_id !== undefined
        ? { goalId: response.correlation_context.goal_id }
        : {}),
      ...(response.correlation_context.conversation_id !== undefined
        ? { conversationId: response.correlation_context.conversation_id }
        : {}),
    },
    startedAt: response.started_at,
    completedAt: response.completed_at,
    failureReason: response.failure_reason,
  };
}

export function normalizeExecutionListResponse(
  response: ExecutionListResponse,
): CursorPaginatedResponse<Execution> {
  return {
    items: response.items.map(normalizeExecution),
    nextCursor: response.next_cursor,
    prevCursor: null,
    total: response.total ?? response.items.length,
  };
}

export function normalizeExecutionState(
  response: ExecutionStateResponse,
): ExecutionState {
  const stepResults = Object.fromEntries(
    Object.entries(response.step_results).map(([key, value]) => [
      key,
      normalizeStepResult(value),
    ]),
  );

  return {
    executionId: response.execution_id,
    status: response.status,
    completedStepIds: response.completed_step_ids,
    activeStepIds: response.active_step_ids,
    pendingStepIds: response.pending_step_ids,
    failedStepIds: response.failed_step_ids,
    skippedStepIds: response.skipped_step_ids,
    waitingForApprovalStepIds: response.waiting_for_approval_step_ids,
    stepResults,
    lastEventSequence: response.last_event_sequence,
    updatedAt: response.updated_at,
  };
}

export function normalizeExecutionEvent(
  response: ExecutionEventResponse,
): ExecutionEvent {
  return {
    id: response.id,
    executionId: response.execution_id,
    sequence: response.sequence,
    eventType: response.event_type,
    stepId: response.step_id,
    agentFqn: response.agent_fqn,
    payload: response.payload,
    createdAt: response.created_at,
  };
}

export function normalizeExecutionJournalPage(
  response: ExecutionJournalResponse,
  offset: number,
  limit: number,
): ExecutionJournalPage {
  const items = response.events.map(normalizeExecutionEvent);
  const nextOffset = offset + items.length;

  return {
    items,
    total: response.total,
    offset,
    limit,
    hasNext: nextOffset < response.total,
    nextOffset: nextOffset < response.total ? nextOffset : null,
  };
}

export function normalizeStepDetail(response: StepDetailResponse): StepDetail {
  return {
    stepId: response.step_id,
    executionId: response.execution_id,
    status: response.status,
    inputs: response.inputs,
    outputs: response.outputs,
    startedAt: response.started_at,
    completedAt: response.completed_at,
    durationMs: response.duration_ms,
    contextQualityScore: response.context_quality_score,
    error: normalizeStepError(response.error),
    tokenUsage: normalizeTokenUsage(response.token_usage),
  };
}

export function deriveStepStatuses(
  state: ExecutionState,
): Record<string, StepStatus> {
  const derived = Object.fromEntries(
    Object.values(state.stepResults).map((result) => [result.stepId, result.status]),
  ) as Record<string, StepStatus>;

  state.completedStepIds.forEach((stepId) => {
    derived[stepId] = "completed";
  });
  state.activeStepIds.forEach((stepId) => {
    derived[stepId] = "running";
  });
  state.pendingStepIds.forEach((stepId) => {
    derived[stepId] = "pending";
  });
  state.failedStepIds.forEach((stepId) => {
    derived[stepId] = "failed";
  });
  state.skippedStepIds.forEach((stepId) => {
    derived[stepId] = "skipped";
  });
  state.waitingForApprovalStepIds.forEach((stepId) => {
    derived[stepId] = "waiting_for_approval";
  });

  return derived;
}

export function isTerminalExecutionStatus(status: ExecutionStatus): boolean {
  return ["completed", "failed", "canceled"].includes(status);
}
