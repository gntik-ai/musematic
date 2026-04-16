import type {
  AgentDetail,
  AgentRevision,
  CompositionBlueprint,
  ValidationResult,
} from "@/lib/types/agent-management";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export const sampleAgent: AgentDetail = {
  fqn: "risk:kyc-monitor",
  namespace: "risk",
  local_name: "kyc-monitor",
  name: "KYC Monitor",
  maturity_level: "production",
  status: "draft",
  revision_count: 4,
  latest_revision_number: 4,
  updated_at: "2026-04-16T10:00:00.000Z",
  workspace_id: "workspace-1",
  description: "Monitors KYC workflows and flags suspicious activity.",
  tags: ["kyc", "risk"],
  category: "fraud",
  purpose: "Monitor KYC workflows, identify suspicious patterns, and escalate them for review.",
  approach: "Pairs deterministic checks with curated workflow tooling.",
  role_type: "executor",
  custom_role: null,
  reasoning_modes: ["deterministic"],
  visibility_patterns: [
    {
      pattern: "risk:*",
      description: "Visible to the risk namespace.",
    },
  ],
  model_config: {
    model_id: "gpt-5.4-mini",
    temperature: 0.2,
  },
  tool_selections: ["transactions", "case-management"],
  connector_suggestions: ["slack"],
  policy_ids: ["policy-1"],
  context_profile_id: "ctx-1",
  source_revision_id: "rev-4",
  last_modified: "2026-04-16T10:00:00.000Z",
};

export const sampleValidationResult: ValidationResult = {
  passed: true,
  checks: [
    { name: "Schema", passed: true, message: "Schema is valid." },
    { name: "Policies", passed: true, message: "Policies are attached." },
  ],
};

export const sampleBlueprint: CompositionBlueprint = {
  blueprint_id: "bp-1",
  description: "Create a fraud monitoring agent for financial transactions.",
  low_confidence: true,
  follow_up_questions: ["Should the agent escalate to Slack or email?"],
  model_config: {
    value: { model_id: "gpt-5.4-mini", reasoning_mode: "standard" },
    reasoning: "Small frontier model is sufficient for structured review.",
    confidence: 0.42,
  },
  tool_selections: {
    value: ["transactions-api", "case-management"],
    reasoning: "Needs transaction data and case management to escalate findings.",
    confidence: 0.42,
  },
  connector_suggestions: {
    value: ["slack", "email"],
    reasoning: "Notifications are useful for fraud escalations.",
    confidence: 0.42,
  },
  policy_recommendations: {
    value: ["policy-fraud-review"],
    reasoning: "Fraud review policy should gate any final escalation.",
    confidence: 0.42,
  },
  context_profile: {
    value: { assembly_strategy: "standard" },
    reasoning: "Standard assembly provides enough context for this workflow.",
    confidence: 0.42,
  },
};

export const sampleRevisions: AgentRevision[] = [
  {
    revision_id: "rev-1",
    revision_number: 1,
    fqn: sampleAgent.fqn,
    status: "draft",
    created_at: "2026-04-10T09:00:00.000Z",
    created_by: "Pat",
    change_summary: "Initial draft",
    is_current: false,
  },
  {
    revision_id: "rev-2",
    revision_number: 2,
    fqn: sampleAgent.fqn,
    status: "draft",
    created_at: "2026-04-11T09:00:00.000Z",
    created_by: "Pat",
    change_summary: "Added policies",
    is_current: false,
  },
  {
    revision_id: "rev-3",
    revision_number: 3,
    fqn: sampleAgent.fqn,
    status: "active",
    created_at: "2026-04-12T09:00:00.000Z",
    created_by: "Pat",
    change_summary: "Published",
    is_current: true,
  },
];

export function seedAgentManagementStores() {
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
      roles: ["agent_operator"],
      workspaceId: "workspace-1",
    },
  } as never);

  useWorkspaceStore.setState({
    currentWorkspace: {
      id: "workspace-1",
      name: "Risk Ops",
      slug: "risk-ops",
      description: "Risk workspace",
      memberCount: 8,
      createdAt: "2026-04-10T09:00:00.000Z",
    },
    isLoading: false,
    sidebarCollapsed: false,
    workspaceList: [],
  } as never);
}
