export const AGENT_MATURITIES = [
  "experimental",
  "beta",
  "production",
  "deprecated",
] as const;

export const AGENT_STATUSES = [
  "draft",
  "active",
  "archived",
  "pending_review",
] as const;

export const AGENT_ROLE_TYPES = [
  "executor",
  "planner",
  "orchestrator",
  "observer",
  "judge",
  "enforcer",
  "custom",
] as const;

export const AGENT_SORT_FIELDS = ["name", "updated_at", "maturity"] as const;
export const AGENT_SORT_ORDERS = ["asc", "desc"] as const;

export type AgentMaturity = (typeof AGENT_MATURITIES)[number];
export type AgentStatus = (typeof AGENT_STATUSES)[number];
export type AgentRoleType = (typeof AGENT_ROLE_TYPES)[number];
export type AgentSortField = (typeof AGENT_SORT_FIELDS)[number];
export type AgentSortOrder = (typeof AGENT_SORT_ORDERS)[number];

export interface VisibilityPattern {
  pattern: string;
  description: string | null;
}

export interface AgentCatalogEntry {
  fqn: string;
  namespace: string;
  local_name: string;
  name: string;
  maturity_level: AgentMaturity;
  status: AgentStatus;
  revision_count: number;
  latest_revision_number: number;
  updated_at: string;
  workspace_id: string;
}

export interface AgentDetail extends AgentCatalogEntry {
  description: string;
  tags: string[];
  category: string;
  purpose: string;
  approach: string | null;
  role_type: AgentRoleType;
  custom_role: string | null;
  reasoning_modes: string[];
  visibility_patterns: VisibilityPattern[];
  model_config: Record<string, unknown>;
  tool_selections: string[];
  connector_suggestions: string[];
  policy_ids: string[];
  context_profile_id: string | null;
  source_revision_id: string | null;
  last_modified?: string | null;
}

export interface HealthScoreComponent {
  label: string;
  score: number;
  weight: number;
}

export interface AgentHealthScore {
  composite_score: number;
  components: HealthScoreComponent[];
  computed_at: string;
}

export interface AgentRevision {
  revision_id: string;
  revision_number: number;
  fqn: string;
  status: AgentStatus;
  created_at: string;
  created_by: string;
  change_summary: string;
  is_current: boolean;
}

export interface RevisionDiff {
  base_revision_number: number;
  compare_revision_number: number;
  base_content: string;
  compare_content: string;
  changed_fields: string[];
}

export interface ValidationCheck {
  name: string;
  passed: boolean;
  message: string | null;
}

export interface ValidationResult {
  passed: boolean;
  checks: ValidationCheck[];
}

export interface PublicationSummary {
  fqn: string;
  previous_status: AgentStatus;
  new_status: "active";
  affected_workspaces: string[];
  published_at: string;
}

export interface BlueprintItem<T> {
  value: T;
  reasoning: string;
  confidence: number;
}

export interface CompositionBlueprint {
  blueprint_id: string;
  description: string;
  low_confidence: boolean;
  follow_up_questions: string[];
  model_config: BlueprintItem<Record<string, unknown>>;
  tool_selections: BlueprintItem<string[]>;
  connector_suggestions: BlueprintItem<string[]>;
  policy_recommendations: BlueprintItem<string[]>;
  context_profile: BlueprintItem<Record<string, unknown>>;
}

export interface AgentCatalogFilters {
  search: string;
  namespace: string[];
  maturity: AgentMaturity[];
  status: AgentStatus[];
  sort_by: AgentSortField;
  sort_order: AgentSortOrder;
  limit: number;
  cursor: string | null;
}

export interface AgentNamespaceSummary {
  namespace: string;
  agent_count: number;
}

export interface AgentPolicySummary {
  policy_id: string;
  name: string;
  type: string;
  enforcement_status: string;
}

export interface AgentUploadResult {
  agent_fqn: string;
  status: "draft";
  validation_errors: string[];
}

export interface AgentMetadataUpdateRequest {
  namespace: string;
  local_name: string;
  name: string;
  description: string;
  purpose: string;
  approach: string | null;
  tags: string[];
  category: string;
  maturity_level: AgentMaturity;
  role_type: AgentRoleType;
  custom_role: string | null;
  reasoning_modes: string[];
  visibility_patterns: VisibilityPattern[];
}

export interface CreateAgentFromBlueprintRequest {
  blueprint_id: string;
  workspace_id: string;
  metadata: AgentMetadataUpdateRequest;
}

export interface CompositionWizardCustomizations {
  model_config: Record<string, unknown>;
  tool_selections: string[];
  connector_suggestions: string[];
  policy_recommendations: string[];
}

export interface CompositionValidationCheckResponse {
  passed: boolean | null;
  details: Record<string, unknown> | Array<Record<string, unknown>>;
  remediation: string | null;
  status: string;
}

export interface AgentBlueprintResponse {
  request_id: string;
  blueprint_id: string;
  version: number;
  workspace_id: string;
  description: string;
  model_config: Record<string, unknown>;
  tool_selections: Array<Record<string, unknown>>;
  connector_suggestions: Array<Record<string, unknown>>;
  policy_recommendations: Array<Record<string, unknown>>;
  context_profile: Record<string, unknown>;
  maturity_estimate: string;
  maturity_reasoning: string;
  confidence_score: number;
  low_confidence: boolean;
  follow_up_questions: Array<Record<string, unknown>>;
  llm_reasoning_summary: string;
  alternatives_considered: Array<Record<string, unknown>>;
  generation_time_ms: number | null;
  created_at: string;
}

export interface CompositionValidationResponse {
  validation_id: string;
  blueprint_id: string;
  overall_valid: boolean;
  tools_check: CompositionValidationCheckResponse;
  model_check: CompositionValidationCheckResponse;
  connectors_check: CompositionValidationCheckResponse;
  policy_check: CompositionValidationCheckResponse;
  cycle_check: CompositionValidationCheckResponse | null;
  validated_at: string;
}

export const DEFAULT_AGENT_CATALOG_FILTERS: AgentCatalogFilters = {
  search: "",
  namespace: [],
  maturity: [],
  status: [],
  sort_by: "updated_at",
  sort_order: "desc",
  limit: 20,
  cursor: null,
};

export function splitAgentFqn(fqn: string): {
  namespace: string;
  localName: string;
} {
  const [namespace, ...localNameParts] = fqn.split(":");

  return {
    namespace: namespace ?? "",
    localName: localNameParts.join(":"),
  };
}

export function buildAgentFqn(namespace: string, localName: string): string {
  return `${namespace}:${localName}`;
}

export function buildAgentManagementHref(fqn: string): string {
  return `/agent-management/${encodeURIComponent(fqn)}`;
}
