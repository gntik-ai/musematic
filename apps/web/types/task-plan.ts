export const PARAMETER_SOURCES = [
  "workflow_definition",
  "step_dependency_output",
  "operator_injection",
  "execution_context",
  "default_value",
] as const;

export type ParameterSource = (typeof PARAMETER_SOURCES)[number];

export interface TaskPlanCandidate {
  fqn: string;
  displayName: string;
  suitabilityScore: number;
  isSelected: boolean;
  tags: string[];
}

export interface ParameterProvenance {
  parameterName: string;
  value: unknown;
  source: ParameterSource;
  sourceDescription: string;
}

export interface RejectedAlternative {
  fqn: string;
  rejectionReason: string;
}

export interface TaskPlanRecord {
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
  source: ParameterSource;
  source_description: string;
}

export interface RejectedAlternativeResponse {
  fqn: string;
  rejection_reason: string;
}

export function normalizeTaskPlanCandidate(
  response: TaskPlanCandidateResponse,
): TaskPlanCandidate {
  return {
    fqn: response.fqn,
    displayName: response.display_name,
    suitabilityScore: response.suitability_score,
    isSelected: response.is_selected,
    tags: response.tags,
  };
}

export function normalizeTaskPlanRecord(
  response: TaskPlanFullResponse,
): TaskPlanRecord {
  return {
    executionId: response.execution_id,
    stepId: response.step_id,
    selectedAgentFqn: response.selected_agent_fqn,
    selectedToolFqn: response.selected_tool_fqn,
    rationaleText: response.rationale_summary,
    candidateAgents: response.considered_agents.map(normalizeTaskPlanCandidate),
    candidateTools: response.considered_tools.map(normalizeTaskPlanCandidate),
    parameters: response.parameters.map((parameter) => ({
      parameterName: parameter.parameter_name,
      value: parameter.value,
      source: parameter.source,
      sourceDescription: parameter.source_description,
    })),
    rejectedAlternatives: response.rejected_alternatives.map((alternative) => ({
      fqn: alternative.fqn,
      rejectionReason: alternative.rejection_reason,
    })),
    persistedAt: response.persisted_at,
  };
}
