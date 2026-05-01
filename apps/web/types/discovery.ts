export type DiscoverySessionStatus = "active" | "converged" | "halted" | "iteration_limit_reached";
export type DiscoveryHypothesisStatus = "active" | "merged" | "retired";
export type DiscoveryExperimentStatus = "not_started" | "running" | "completed" | "failed" | "timeout";

export interface DiscoverySession {
  session_id: string;
  workspace_id: string;
  research_question: string;
  corpus_refs: Array<Record<string, unknown>>;
  config: Record<string, unknown>;
  status: DiscoverySessionStatus;
  current_cycle: number;
  convergence_metrics: Record<string, unknown> | null;
  initiated_by: string;
  created_at: string;
  updated_at: string;
}

export interface DiscoveryHypothesis {
  hypothesis_id: string;
  session_id: string;
  title: string;
  description: string;
  reasoning: string;
  confidence: number;
  generating_agent_fqn: string;
  status: DiscoveryHypothesisStatus;
  elo_score: number | null;
  rank: number | null;
  wins: number;
  losses: number;
  draws: number;
  cluster_id: string | null;
  embedding_status: "pending" | "indexed" | "failed";
  rationale_metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface DiscoveryHypothesisListResponse {
  items: DiscoveryHypothesis[];
  next_cursor: string | null;
}

export interface DiscoverySessionListResponse {
  items: DiscoverySession[];
  next_cursor: string | null;
}

export interface DiscoveryCritique {
  critique_id: string;
  hypothesis_id: string;
  reviewer_agent_fqn: string;
  is_aggregated: boolean;
  scores: Record<string, { score: number; confidence: number; reasoning: string }>;
  composite_summary: Record<string, unknown> | null;
  created_at: string;
}

export interface DiscoveryCritiqueListResponse {
  items: DiscoveryCritique[];
  aggregated: DiscoveryCritique | null;
}

export interface DiscoveryExperiment {
  experiment_id: string;
  hypothesis_id: string;
  session_id: string;
  plan: Record<string, unknown>;
  governance_status: "pending" | "approved" | "rejected";
  governance_violations: Array<Record<string, unknown>>;
  execution_status: DiscoveryExperimentStatus;
  sandbox_execution_id: string | null;
  results: Record<string, unknown> | null;
  designed_by_agent_fqn: string;
  created_at: string;
  updated_at: string;
}

export interface ExperimentDesignInput {
  workspace_id: string;
}

export const discoveryQueryKeys = {
  session: (sessionId: string | null | undefined, workspaceId?: string | null) =>
    ["discovery", "session", sessionId ?? "none", workspaceId ?? "none"] as const,
  hypotheses: (
    sessionId: string | null | undefined,
    workspaceId?: string | null,
    status?: string | null,
    orderBy?: string | null,
  ) =>
    [
      "discovery",
      "hypotheses",
      sessionId ?? "none",
      workspaceId ?? "none",
      status ?? "all",
      orderBy ?? "elo_desc",
    ] as const,
  hypothesis: (hypothesisId: string | null | undefined, workspaceId?: string | null) =>
    ["discovery", "hypothesis", hypothesisId ?? "none", workspaceId ?? "none"] as const,
  critiques: (hypothesisId: string | null | undefined, workspaceId?: string | null) =>
    ["discovery", "critiques", hypothesisId ?? "none", workspaceId ?? "none"] as const,
  experiments: (sessionId: string | null | undefined, workspaceId?: string | null) =>
    ["discovery", "experiments", sessionId ?? "none", workspaceId ?? "none"] as const,
};
