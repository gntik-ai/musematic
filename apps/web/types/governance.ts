import type { FqnPattern } from "@/types/fqn";

export interface GovernanceChain {
  workspaceId: string;
  observerAgentFqn: string | null;
  judgeAgentFqn: string | null;
  enforcerAgentFqn: string | null;
  updatedAt: string;
  updatedBy: string;
}

export interface VisibilityGrant {
  id: string;
  workspaceId: string;
  pattern: FqnPattern;
  createdBy: string;
  createdAt: string;
}

export interface GovernanceVerdict {
  id: string;
  offendingAgentFqn: string;
  verdictType: "policy_violation" | "safety_violation" | "certification_invalid";
  enforcerAgentFqn: string;
  actionTaken: "quarantine" | "warn" | "block";
  issuedAt: string;
  rationaleExcerpt: string;
}
