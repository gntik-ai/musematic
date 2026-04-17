"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import { trustWorkbenchApi } from "@/lib/hooks/use-certifications";
import { useWorkspaceStore } from "@/store/workspace-store";
import type {
  AttachmentTargetType,
  PolicyBinding,
  PolicyConflict,
  PolicyRuleProvenance,
  PolicyScopeType,
} from "@/lib/types/trust-workbench";

interface EffectivePolicyResolutionResponse {
  agentId?: string;
  agent_id?: string;
  resolvedRules?: Array<{
    rule?: Record<string, unknown>;
    provenance?: Record<string, unknown>;
  }>;
  resolved_rules?: Array<{
    rule?: Record<string, unknown>;
    provenance?: Record<string, unknown>;
  }>;
  conflicts?: PolicyConflict[];
  sourcePolicies?: string[];
  source_policies?: string[];
}

interface FleetListResponse {
  items?: Array<{
    id: string;
    name: string;
  }>;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asPolicyScopeType(value: unknown): PolicyScopeType {
  const allowed: PolicyScopeType[] = [
    "global",
    "deployment",
    "workspace",
    "agent",
    "fleet",
    "execution",
  ];

  return allowed.includes(value as PolicyScopeType)
    ? (value as PolicyScopeType)
    : "workspace";
}

function asAttachmentTargetType(
  scopeType: PolicyScopeType,
  value: unknown,
): AttachmentTargetType {
  const allowed: AttachmentTargetType[] = [
    "global",
    "deployment",
    "workspace",
    "agent_revision",
    "fleet",
    "execution",
  ];
  if (allowed.includes(value as AttachmentTargetType)) {
    return value as AttachmentTargetType;
  }

  switch (scopeType) {
    case "agent":
      return "agent_revision";
    case "fleet":
      return "fleet";
    case "global":
      return "global";
    case "deployment":
      return "deployment";
    case "execution":
      return "execution";
    default:
      return "workspace";
  }
}

function asBoolean(value: unknown, fallback = true): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function normalizeProvenance(raw: Record<string, unknown>): PolicyRuleProvenance {
  return {
    ruleId: asString(raw.ruleId ?? raw.rule_id),
    policyId: asString(raw.policyId ?? raw.policy_id),
    versionId: asString(raw.versionId ?? raw.version_id),
    scopeLevel:
      typeof (raw.scopeLevel ?? raw.scope_level) === "number"
        ? ((raw.scopeLevel ?? raw.scope_level) as number)
        : 0,
    scopeType: asPolicyScopeType(raw.scopeType ?? raw.scope_type),
    scopeTargetId:
      typeof (raw.scopeTargetId ?? raw.scope_target_id) === "string"
        ? ((raw.scopeTargetId ?? raw.scope_target_id) as string)
        : null,
  };
}

function deriveBindingSource(scopeType: PolicyScopeType): PolicyBinding["source"] {
  switch (scopeType) {
    case "agent":
      return "direct";
    case "fleet":
      return "fleet";
    case "global":
      return "global";
    case "deployment":
      return "deployment";
    default:
      return "workspace";
  }
}

function buildSourceMetadata(
  scopeType: PolicyScopeType,
  scopeTargetId: string | null,
  workspaceName: string | null,
  fleetNames: Map<string, string>,
): Pick<PolicyBinding, "sourceLabel" | "sourceEntityUrl"> {
  switch (scopeType) {
    case "agent":
      return { sourceLabel: "direct", sourceEntityUrl: null };
    case "workspace":
      return {
        sourceLabel: workspaceName ? `workspace: ${workspaceName}` : "workspace",
        sourceEntityUrl: "/settings",
      };
    case "fleet":
      return {
        sourceLabel: scopeTargetId
          ? `fleet: ${fleetNames.get(scopeTargetId) ?? scopeTargetId}`
          : "fleet",
        sourceEntityUrl: scopeTargetId
          ? `/fleet/${encodeURIComponent(scopeTargetId)}`
          : null,
      };
    case "global":
      return {
        sourceLabel: "platform default",
        sourceEntityUrl: "/policies",
      };
    case "deployment":
      return {
        sourceLabel: "deployment",
        sourceEntityUrl: "/policies",
      };
    default:
      return { sourceLabel: "execution", sourceEntityUrl: null };
  }
}

export const effectivePolicyQueryKeys = {
  detail: (
    agentId: string | null | undefined,
    workspaceId: string | null | undefined,
  ) => ["effectivePolicies", agentId ?? "none", workspaceId ?? "none"] as const,
};

export function useEffectivePolicies(
  agentId: string | null | undefined,
  workspaceId: string | null | undefined,
) {
  const workspaceName = useWorkspaceStore(
    (state) => state.currentWorkspace?.name ?? null,
  );

  return useAppQuery<PolicyBinding[]>(
    effectivePolicyQueryKeys.detail(agentId, workspaceId),
    async () => {
      const [resolution, fleets] = await Promise.all([
        trustWorkbenchApi.get<EffectivePolicyResolutionResponse>(
          `/api/v1/policies/effective/${encodeURIComponent(agentId ?? "")}?workspace_id=${encodeURIComponent(workspaceId ?? "")}`,
        ),
        trustWorkbenchApi
          .get<FleetListResponse>(
            `/api/v1/fleets?workspace_id=${encodeURIComponent(workspaceId ?? "")}&page=1&size=100`,
          )
          .catch(() => ({ items: [] })),
      ]);

      const fleetNames = new Map(
        (fleets.items ?? []).map((fleet) => [fleet.id, fleet.name]),
      );
      const seen = new Set<string>();
      const resolvedRules = resolution.resolvedRules ?? resolution.resolved_rules ?? [];

      return resolvedRules
        .map((item) => {
          const rule =
            typeof item.rule === "object" && item.rule !== null
              ? item.rule
              : {};
          const provenance = normalizeProvenance(
            typeof item.provenance === "object" && item.provenance !== null
              ? item.provenance
              : {},
          );
          const source = deriveBindingSource(provenance.scopeType);
          const sourceMetadata = buildSourceMetadata(
            provenance.scopeType,
            provenance.scopeTargetId,
            workspaceName,
            fleetNames,
          );
          const attachmentId = asString(
            rule.attachmentId ?? rule.attachment_id,
            `${provenance.policyId}:${provenance.versionId}:${provenance.scopeType}:${provenance.scopeTargetId ?? "none"}`,
          );
          const uniqueKey = `${attachmentId}:${provenance.policyId}`;

          if (seen.has(uniqueKey)) {
            return null;
          }
          seen.add(uniqueKey);

          return {
            attachmentId,
            policyId: provenance.policyId,
            policyVersionId: provenance.versionId,
            policyName: asString(
              rule.policyName ?? rule.policy_name ?? rule.name,
              provenance.policyId,
            ),
            policyDescription:
              typeof (rule.policyDescription ?? rule.policy_description ?? rule.description) ===
              "string"
                ? ((rule.policyDescription ??
                    rule.policy_description ??
                    rule.description) as string)
                : null,
            scopeType: provenance.scopeType,
            targetType: asAttachmentTargetType(
              provenance.scopeType,
              rule.targetType ?? rule.target_type,
            ),
            targetId:
              typeof (rule.targetId ?? rule.target_id) === "string"
                ? ((rule.targetId ?? rule.target_id) as string)
                : provenance.scopeTargetId,
            isActive: asBoolean(rule.isActive ?? rule.is_active, true),
            createdAt: asString(
              rule.createdAt ?? rule.created_at,
              new Date(0).toISOString(),
            ),
            source,
            sourceLabel: sourceMetadata.sourceLabel,
            sourceEntityUrl: sourceMetadata.sourceEntityUrl,
            canRemove: source === "direct",
          } satisfies PolicyBinding;
        })
        .filter((binding): binding is PolicyBinding => binding !== null);
    },
    {
      enabled: Boolean(agentId && workspaceId),
      staleTime: Infinity,
    },
  );
}
