/**
 * TypeScript contract types for Workflow Editor and Execution Monitor (feature 036).
 *
 * These types define the exact shapes of API responses and WebSocket payloads
 * that the frontend expects. They are the source of truth for MSW mocks and
 * type-safe API hooks.
 *
 * Mirrors: specs/036-workflow-editor-monitor/data-model.md
 */

// ─── Workflow ────────────────────────────────────────────────────────────────

export interface WorkflowDefinitionResponse {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  current_version_id: string;
  current_version_number: number;
  status: 'active' | 'archived' | 'draft';
  created_at: string;
  updated_at: string;
}

export interface WorkflowVersionResponse {
  id: string;
  workflow_id: string;
  version_number: number;
  yaml_content: string;
  compiled_ir: WorkflowIRResponse;
  created_at: string;
  created_by: string;
}

export interface WorkflowIRResponse {
  metadata: {
    name: string;
    description: string | null;
    version: string;
    default_reasoning_mode?: string;
    default_context_budget?: ContextBudgetResponse;
  };
  steps: WorkflowIRStepResponse[];
  triggers: WorkflowTriggerResponse[];
}

export interface WorkflowIRStepResponse {
  id: string;
  name: string;
  type: string;
  agent_fqn?: string;
  reasoning_mode?: string;
  context_budget?: ContextBudgetResponse;
  timeout?: number;
  dependencies: string[];
  retry_config?: { max_attempts: number; backoff_seconds: number };
  approval_config?: { approver_role: string; timeout_seconds: number };
}

export interface ContextBudgetResponse {
  max_tokens: number;
  max_rounds: number;
  max_cost_usd: number;
}

export interface WorkflowTriggerResponse {
  type: string;
  config: Record<string, unknown>;
}

export interface WorkflowSchemaResponse {
  /** JSON Schema object for workflow YAML, loaded into monaco-yaml */
  $schema: string;
  [key: string]: unknown;
}

export interface WorkflowListResponse {
  items: WorkflowDefinitionResponse[];
  next_cursor: string | null;
}

// ─── Execution ───────────────────────────────────────────────────────────────

export type ExecutionStatus =
  | 'queued'
  | 'running'
  | 'paused'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'canceled'
  | 'compensating';

export type StepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'waiting_for_approval'
  | 'canceled';

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

export interface StepResultResponse {
  step_id: string;
  status: StepStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  error: StepErrorResponse | null;
  retry_count: number;
}

export interface StepErrorResponse {
  code: string;
  message: string;
  details: Record<string, unknown> | null;
}

export interface ExecutionJournalResponse {
  events: ExecutionEventResponse[];
  total: number;
}

export interface ExecutionEventResponse {
  id: string;
  execution_id: string;
  sequence: number;
  event_type: string;
  step_id: string | null;
  agent_fqn: string | null;
  payload: Record<string, unknown>;
  created_at: string;
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

export interface TokenUsageResponse {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

// ─── Task Plan ───────────────────────────────────────────────────────────────

export interface TaskPlanFullResponse {
  execution_id: string;
  step_id: string;
  selected_agent_fqn: string | null;
  selected_tool_fqn: string | null;
  rationale_summary: string;
  considered_agents: TaskPlanCandidateResponse[];
  considered_tools: TaskPlanCandidateResponse[];
  parameters: ParameterProvenanceResponse[];
  rejected_alternatives: RejectedAlternativeResponse[];
  storage_key: string;
  persisted_at: string;
}

export interface TaskPlanCandidateResponse {
  fqn: string;
  display_name: string;
  suitability_score: number;
  is_selected: boolean;
  tags: string[];
}

export interface ParameterProvenanceResponse {
  parameter_name: string;
  value: unknown;
  source: 'workflow_definition' | 'step_dependency_output' | 'operator_injection' | 'execution_context' | 'default_value';
  source_description: string;
}

export interface RejectedAlternativeResponse {
  fqn: string;
  rejection_reason: string;
}

// ─── WebSocket Events ─────────────────────────────────────────────────────────

export type ExecutionWsEventType =
  | 'step.state_changed'
  | 'execution.status_changed'
  | 'event.appended'
  | 'budget.threshold'
  | 'correction.iteration'
  | 'approval.requested'
  | 'hot_change.applied';

export interface ExecutionWsEvent {
  channel: string;
  event_type: ExecutionWsEventType;
  payload: StepStateChangedPayload | ExecutionStatusChangedPayload | EventAppendedPayload | BudgetThresholdPayload | CorrectionIterationPayload | ApprovalRequestedPayload | HotChangeAppliedPayload;
}

export interface StepStateChangedPayload {
  step_id: string;
  new_status: StepStatus;
  occurred_at: string;
}

export interface ExecutionStatusChangedPayload {
  new_status: ExecutionStatus;
  occurred_at: string;
}

export interface EventAppendedPayload {
  event: ExecutionEventResponse;
}

export interface BudgetThresholdPayload {
  step_id: string;
  dimension: 'tokens' | 'rounds' | 'cost' | 'time';
  current_value: number;
  max_value: number;
  threshold_pct: 80 | 90 | 100;
}

export interface CorrectionIterationPayload {
  step_id: string;
  loop_id: string;
  iteration_number: number;
  quality_score: number;
  delta: number;
  status: 'continue' | 'converged' | 'budget_exceeded' | 'escalated';
}

export interface ApprovalRequestedPayload {
  step_id: string;
  approver_role: string;
  requested_at: string;
}

export interface HotChangeAppliedPayload {
  variable_name: string;
  new_value: unknown;
  applied_at: string;
}

// ─── Analytics ───────────────────────────────────────────────────────────────

export interface UsageAggregateResponse {
  items: UsageAgentRow[];
}

export interface UsageAgentRow {
  agent_fqn: string;
  model_id: string;
  execution_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  avg_quality_score: number | null;
}

// ─── Control Actions (request bodies) ────────────────────────────────────────

export interface CancelExecutionRequest {
  reason?: string;
}

export interface SkipStepRequest {
  reason?: string;
}

export interface InjectVariableRequest {
  variable_name: string;
  value: unknown;
  reason?: string;
}

export interface ApprovalDecisionRequest {
  decision: 'approved' | 'rejected';
  comment?: string;
}
