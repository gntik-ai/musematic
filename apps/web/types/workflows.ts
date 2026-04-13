import type { CursorPaginatedResponse } from "@/types/api";

export const WORKFLOW_STATUSES = ["active", "archived", "draft"] as const;
export const WORKFLOW_STEP_TYPES = [
  "agent_task",
  "parallel_fan_out",
  "parallel_fan_in",
  "conditional",
  "approval_gate",
  "webhook_trigger",
  "delay",
  "compensation",
] as const;
export const REASONING_MODES = [
  "chain_of_thought",
  "tree_of_thought",
  "self_correction",
  "direct",
  "iterative",
  "exploratory",
] as const;
export const WORKFLOW_TRIGGER_TYPES = [
  "manual",
  "scheduled",
  "webhook",
  "kafka_event",
  "goal_created",
  "completion",
] as const;
export const VALIDATION_SEVERITIES = ["error", "warning"] as const;

export type WorkflowStatus = (typeof WORKFLOW_STATUSES)[number];
export type WorkflowStepType = (typeof WORKFLOW_STEP_TYPES)[number];
export type ReasoningMode = (typeof REASONING_MODES)[number];
export type WorkflowTriggerType = (typeof WORKFLOW_TRIGGER_TYPES)[number];
export type ValidationSeverity = (typeof VALIDATION_SEVERITIES)[number];

export interface ContextBudget {
  maxTokens: number;
  maxRounds: number;
  maxCostUsd: number;
}

export interface WorkflowTrigger {
  type: WorkflowTriggerType;
  config: Record<string, unknown>;
}

export interface WorkflowIRStep {
  id: string;
  name: string;
  type: WorkflowStepType;
  agentFqn?: string;
  reasoningMode?: ReasoningMode;
  contextBudget?: ContextBudget;
  timeout?: number;
  dependencies: string[];
  retryConfig?: {
    maxAttempts: number;
    backoffSeconds: number;
  };
  approvalConfig?: {
    approverRole: string;
    timeoutSeconds: number;
  };
}

export interface WorkflowIR {
  metadata: {
    name: string;
    description: string | null;
    version: string;
    defaultReasoningMode?: ReasoningMode;
    defaultContextBudget?: ContextBudget;
  };
  steps: WorkflowIRStep[];
  triggers: WorkflowTrigger[];
}

export interface WorkflowDefinition {
  id: string;
  workspaceId: string;
  name: string;
  description: string | null;
  currentVersionId: string;
  currentVersionNumber: number;
  status: WorkflowStatus;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowVersion {
  id: string;
  workflowId: string;
  versionNumber: number;
  yamlContent: string;
  compiledIr: WorkflowIR;
  createdAt: string;
  createdBy: string;
}

export interface ValidationError {
  line: number;
  column: number;
  message: string;
  severity: ValidationSeverity;
  path: string;
}

export interface WorkflowGraphNode {
  id: string;
  type: "step";
  position: { x: number; y: number };
  data: {
    stepId: string;
    label: string;
    stepType: WorkflowStepType;
    agentFqn?: string;
    hasValidationError: boolean;
  };
}

export interface WorkflowGraphEdge {
  id: string;
  source: string;
  target: string;
  type: "smoothstep";
}

export interface WorkflowSchema {
  $schema?: string;
  [key: string]: unknown;
}

export interface CreateWorkflowInput {
  workspaceId: string;
  name: string;
  description?: string | null;
  yamlContent: string;
}

export interface UpdateWorkflowInput {
  workflowId: string;
  yamlContent: string;
  description?: string | null;
}

export interface WorkflowDefinitionResponse {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  current_version_id: string;
  current_version_number: number;
  status: WorkflowStatus;
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
    default_reasoning_mode?: ReasoningMode;
    default_context_budget?: ContextBudgetResponse;
  };
  steps: WorkflowIRStepResponse[];
  triggers: WorkflowTriggerResponse[];
}

export interface WorkflowIRStepResponse {
  id: string;
  name: string;
  type: WorkflowStepType;
  agent_fqn?: string;
  reasoning_mode?: ReasoningMode;
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
  type: WorkflowTriggerType;
  config: Record<string, unknown>;
}

export interface WorkflowListResponse {
  items: WorkflowDefinitionResponse[];
  next_cursor: string | null;
  total?: number;
}

export function normalizeContextBudget(
  response: ContextBudgetResponse | undefined,
): ContextBudget | undefined {
  if (!response) {
    return undefined;
  }

  return {
    maxTokens: response.max_tokens,
    maxRounds: response.max_rounds,
    maxCostUsd: response.max_cost_usd,
  };
}

export function normalizeWorkflowIrStep(
  response: WorkflowIRStepResponse,
): WorkflowIRStep {
  const contextBudget = normalizeContextBudget(response.context_budget);
  const retryConfig = response.retry_config
    ? {
        maxAttempts: response.retry_config.max_attempts,
        backoffSeconds: response.retry_config.backoff_seconds,
      }
    : undefined;
  const approvalConfig = response.approval_config
    ? {
        approverRole: response.approval_config.approver_role,
        timeoutSeconds: response.approval_config.timeout_seconds,
      }
    : undefined;

  return {
    id: response.id,
    name: response.name,
    type: response.type,
    ...(response.agent_fqn !== undefined ? { agentFqn: response.agent_fqn } : {}),
    ...(response.reasoning_mode !== undefined
      ? { reasoningMode: response.reasoning_mode }
      : {}),
    ...(contextBudget !== undefined ? { contextBudget } : {}),
    ...(response.timeout !== undefined ? { timeout: response.timeout } : {}),
    dependencies: response.dependencies,
    ...(retryConfig !== undefined ? { retryConfig } : {}),
    ...(approvalConfig !== undefined ? { approvalConfig } : {}),
  };
}

export function normalizeWorkflowIr(response: WorkflowIRResponse): WorkflowIR {
  const defaultContextBudget = normalizeContextBudget(
    response.metadata.default_context_budget,
  );

  return {
    metadata: {
      name: response.metadata.name,
      description: response.metadata.description,
      version: response.metadata.version,
      ...(response.metadata.default_reasoning_mode !== undefined
        ? { defaultReasoningMode: response.metadata.default_reasoning_mode }
        : {}),
      ...(defaultContextBudget !== undefined
        ? { defaultContextBudget }
        : {}),
    },
    steps: response.steps.map(normalizeWorkflowIrStep),
    triggers: response.triggers.map((trigger) => ({
      type: trigger.type,
      config: trigger.config,
    })),
  };
}

export function normalizeWorkflowDefinition(
  response: WorkflowDefinitionResponse,
): WorkflowDefinition {
  return {
    id: response.id,
    workspaceId: response.workspace_id,
    name: response.name,
    description: response.description,
    currentVersionId: response.current_version_id,
    currentVersionNumber: response.current_version_number,
    status: response.status,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  };
}

export function normalizeWorkflowVersion(
  response: WorkflowVersionResponse,
): WorkflowVersion {
  return {
    id: response.id,
    workflowId: response.workflow_id,
    versionNumber: response.version_number,
    yamlContent: response.yaml_content,
    compiledIr: normalizeWorkflowIr(response.compiled_ir),
    createdAt: response.created_at,
    createdBy: response.created_by,
  };
}

export function normalizeWorkflowListResponse(
  response: WorkflowListResponse,
): CursorPaginatedResponse<WorkflowDefinition> {
  return {
    items: response.items.map(normalizeWorkflowDefinition),
    nextCursor: response.next_cursor,
    prevCursor: null,
    total: response.total ?? response.items.length,
  };
}
