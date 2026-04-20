import type {
  AgentDetail,
  AgentRoleType as ExistingAgentRoleType,
  VisibilityPattern,
} from "@/lib/types/agent-management";

export type FqnPattern = string;

export type RoleType =
  | "researcher"
  | "analyst"
  | "reviewer"
  | "operator"
  | "verdict_authority"
  | "tool_user"
  | "integrator";

export interface CertificationStatus {
  certifierId: string;
  certifierName: string;
  issuedAt: string;
  expiresAt: string;
  status: "valid" | "expiring_soon" | "expired" | "revoked";
  daysUntilExpiry: number;
}

export interface AgentIdentity {
  id: string;
  namespace: string | null;
  localName: string | null;
  fqn: string | null;
  purpose: string | null;
  approach: string | null;
  roleType: RoleType | ExistingAgentRoleType | null;
  visibilityPatterns: FqnPattern[];
  certification: CertificationStatus | null;
}

export function toAgentIdentity(
  agent: AgentDetail,
  certification: CertificationStatus | null = null,
): AgentIdentity {
  return {
    id: agent.fqn,
    namespace: agent.namespace ?? null,
    localName: agent.local_name ?? null,
    fqn: agent.fqn ?? null,
    purpose: agent.purpose ?? null,
    approach: agent.approach ?? null,
    roleType: agent.role_type ?? null,
    visibilityPatterns: agent.visibility_patterns.map(
      (pattern: VisibilityPattern) => pattern.pattern,
    ),
    certification,
  };
}
